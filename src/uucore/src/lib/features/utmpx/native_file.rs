// This file is part of the uutils coreutils package.
// For license information, please view the LICENSE file.

//! File-backed records for SDKs without the utmpx database functions.
//! Records use the target libc's native utmpx ABI, rather than a system account list.

use super::{Utmpx, UtmpxRecord};
use libc::utmpx;
use std::io::{self, Read};
use std::path::Path;
#[cfg(target_env = "ohos")]
use std::path::PathBuf;

pub(super) fn read_record(reader: &mut impl Read) -> io::Result<Option<UtmpxRecord>> {
    let mut bytes = [0u8; size_of::<utmpx>()];
    match reader.read_exact(&mut bytes[..1]) {
        Err(error) if error.kind() == io::ErrorKind::UnexpectedEof => return Ok(None),
        result => result?,
    }
    reader.read_exact(&mut bytes[1..])?;
    // SAFETY: libc::utmpx consists of integer fields and fixed-size arrays.
    // All bit patterns are valid; read_unaligned does not require byte alignment.
    let inner = unsafe { std::ptr::read_unaligned(bytes.as_ptr().cast::<utmpx>()) };
    Ok(Some(UtmpxRecord::Traditional(Box::new(Utmpx { inner }))))
}

pub(super) fn read_file(path: &Path) -> io::Result<Vec<UtmpxRecord>> {
    let mut file = std::fs::File::open(path)?;
    let mut records = Vec::new();
    while let Some(record) = read_record(&mut file)? {
        records.push(record);
    }
    Ok(records)
}

#[cfg(target_env = "ohos")]
pub(super) fn default_path() -> PathBuf {
    std::env::var_os("UUTILS_OHOS_SESSION_DIR")
        .map_or_else(|| PathBuf::from(super::DEFAULT_FILE), PathBuf::from)
}

pub(super) fn read_path(path: &Path) -> io::Result<Vec<UtmpxRecord>> {
    if !path.is_dir() {
        return read_file(path);
    }
    let mut records = Vec::new();
    for entry in std::fs::read_dir(path)? {
        let entry = entry?;
        if entry.path().extension() != Some(std::ffi::OsStr::new("utmpx")) {
            continue;
        }
        let metadata = entry.metadata()?;
        if !metadata.is_file() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "session record is not a file",
            ));
        }
        #[cfg(target_env = "ohos")]
        {
            use std::os::unix::fs::MetadataExt;
            // SAFETY: getuid has no pointer arguments or preconditions.
            if metadata.uid() != unsafe { libc::getuid() } || metadata.mode() & 0o077 != 0 {
                return Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "application PTY records must be owned by this UID with mode 0600",
                ));
            }
        }
        let file_records = read_file(&entry.path())?;
        let mut live = Vec::new();
        let mut boot = None;
        for record in file_records {
            if record.is_user_process() && record.pid() > 0 {
                // SAFETY: signal zero only checks this recorded process's existence.
                if unsafe { libc::kill(record.pid(), 0) } == 0 {
                    live.push(record);
                }
            } else if record.record_type() == super::BOOT_TIME {
                boot = Some(record);
            }
        }
        if !live.is_empty() {
            if !records
                .iter()
                .any(|record: &UtmpxRecord| record.record_type() == super::BOOT_TIME)
                && let Some(boot) = boot
            {
                records.push(boot);
            }
            records.extend(live);
        }
    }
    records.sort_by_key(UtmpxRecord::tty_device);
    Ok(records)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[cfg(target_env = "ohos")]
    #[test]
    fn native_record_matches_the_ohos_sdk_time64_abi() {
        assert_eq!(size_of::<libc::time_t>(), 8);
        assert_eq!(size_of::<libc::timeval>(), 16);
        assert_eq!(size_of::<utmpx>(), 400);
        assert_eq!(std::mem::offset_of!(utmpx, ut_user), 44);
        assert_eq!(std::mem::offset_of!(utmpx, ut_tv), 344);
    }

    fn record_bytes(pid: i32) -> Vec<u8> {
        let mut record = std::mem::MaybeUninit::<utmpx>::zeroed();
        // SAFETY: the allocation is initialized byte-for-byte, including padding.
        // Write fields in place so no structure move can discard padding bytes.
        unsafe {
            let ptr = record.as_mut_ptr();
            (*ptr).ut_type = libc::USER_PROCESS;
            (*ptr).ut_pid = pid;
            (*ptr).ut_user[0] = b'a' as _;
            std::slice::from_raw_parts(ptr.cast::<u8>(), size_of::<utmpx>()).to_vec()
        }
    }

    #[test]
    fn decodes_native_records_without_database_functions() {
        let bytes = record_bytes(123);
        let mut input = Cursor::new([bytes.clone(), bytes].concat());
        for _ in 0..2 {
            let record = read_record(&mut input).unwrap().unwrap();
            assert!(record.is_user_process());
            assert_eq!(record.user(), "a");
            assert_eq!(record.pid(), 123);
        }
        assert!(read_record(&mut input).unwrap().is_none());
    }

    #[test]
    fn reports_partial_records_instead_of_silently_dropping_them() {
        for length in [1, size_of::<utmpx>() - 1] {
            let error = read_record(&mut Cursor::new(vec![0; length]))
                .err()
                .unwrap();
            assert_eq!(error.kind(), io::ErrorKind::UnexpectedEof);
        }
    }

    #[cfg(target_env = "ohos")]
    #[test]
    fn file_iterators_can_be_active_at_the_same_time() {
        let path = std::env::temp_dir().join(format!(
            "uucore-independent-records-{}.utmpx",
            std::process::id()
        ));
        std::fs::write(&path, record_bytes(std::process::id() as i32)).unwrap();
        let mut first = Utmpx::iter_all_records_from(&path);
        let mut second = Utmpx::iter_all_records_from(&path);
        assert_eq!(first.next().unwrap().user(), "a");
        assert_eq!(second.next().unwrap().user(), "a");
        assert!(first.next().is_none());
        assert!(second.next().is_none());
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn directory_source_ignores_dead_sessions_and_rejects_truncated_records() {
        use std::os::unix::fs::PermissionsExt;
        let directory =
            std::env::temp_dir().join(format!("uucore-pty-records-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        for (name, pid) in [
            ("live.utmpx", std::process::id() as i32),
            ("dead.utmpx", i32::MAX),
        ] {
            let path = directory.join(name);
            let mut bytes = record_bytes(pid);
            if name == "live.utmpx" {
                bytes.extend(record_bytes(i32::MAX));
            }
            std::fs::write(&path, bytes).unwrap();
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        std::fs::write(directory.join(".atomic-write.tmp"), [0]).unwrap();
        let records = read_path(&directory).unwrap();
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].pid(), std::process::id() as i32);
        let malformed = directory.join("malformed.utmpx");
        std::fs::write(&malformed, [0]).unwrap();
        std::fs::set_permissions(malformed, std::fs::Permissions::from_mode(0o600)).unwrap();
        assert_eq!(
            read_path(&directory).err().unwrap().kind(),
            io::ErrorKind::UnexpectedEof
        );
        std::fs::remove_dir_all(directory).unwrap();
    }
}
