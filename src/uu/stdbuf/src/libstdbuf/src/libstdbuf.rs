// This file is part of the uutils coreutils package.
//
// For the full copyright and license information, please view the LICENSE
// file that was distributed with this source code.

// spell-checker:ignore (ToDO) getreent reent IOFBF IOLBF IONBF setvbuf stderrp stdinp stdoutp fdopen

use core::ffi::{c_char, c_int};
use ctor::ctor;
use libc::{_IOFBF, _IOLBF, _IONBF, FILE, fileno, size_t};
use std::io::{Write, stderr};
use std::{env, ptr};

// This runs automatically when the library is loaded via LD_PRELOAD
#[ctor(unsafe)]
fn init() {
    unsafe { __stdbuf() };
}

/// # Safety
/// This function is unsafe because it calls a C API
#[unsafe(no_mangle)]
pub unsafe extern "C" fn __stdbuf_get_stdin() -> *mut FILE {
    #[cfg(any(target_vendor = "apple", target_os = "freebsd"))]
    {
        unsafe extern "C" {
            fn __stdinp() -> *mut FILE;
        }
        unsafe { __stdinp() }
    }

    #[cfg(target_os = "openbsd")]
    {
        unsafe extern "C" {
            static mut __stdin: *mut FILE;
        }
        unsafe { __stdin }
    }

    #[cfg(target_os = "netbsd")]
    {
        unsafe { libc::fdopen(0, c"r".as_ptr()) }
    }

    #[cfg(target_os = "cygwin")]
    {
        // _getreent()->_std{in,out,err}
        // see:
        // echo '#include <stdio.h>\nstd{in,out,err}' | gcc -E -xc - -std=c23 | tail -n1
        // echo '#include <stdio.h>' | grep -E -xc - -std=c23 | grep 'struct _reent' -A91 | grep 580 -A91 | tail -n+2

        #[repr(C)]
        struct _reent {
            _errno: c_int,
            _stdin: *mut FILE,
            _stdout: *mut FILE,
            _stderr: *mut FILE,
            // other stuff
        }

        unsafe extern "C" {
            fn __getreent() -> *mut _reent;
        }

        unsafe { (*__getreent())._stdin }
    }

    #[cfg(not(any(
        target_vendor = "apple",
        target_os = "freebsd",
        target_os = "netbsd",
        target_os = "openbsd",
        target_os = "cygwin"
    )))]
    {
        unsafe extern "C" {
            static mut stdin: *mut FILE;
        }
        unsafe { stdin }
    }
}

/// # Safety
/// This function is unsafe because it calls a C API
#[unsafe(no_mangle)]
pub unsafe extern "C" fn __stdbuf_get_stdout() -> *mut FILE {
    #[cfg(any(target_vendor = "apple", target_os = "freebsd"))]
    {
        unsafe extern "C" {
            fn __stdoutp() -> *mut FILE;
        }
        unsafe { __stdoutp() }
    }

    #[cfg(target_os = "openbsd")]
    {
        unsafe extern "C" {
            static mut __stdout: *mut FILE;
        }
        unsafe { __stdout }
    }

    #[cfg(target_os = "netbsd")]
    {
        unsafe { libc::fdopen(1, c"w".as_ptr()) }
    }

    #[cfg(target_os = "cygwin")]
    {
        // _getreent()->_std{in,out,err}
        // see:
        // echo '#include <stdio.h>\nstd{in,out,err}' | gcc -E -xc - -std=c23 | tail -n1
        // echo '#include <stdio.h>' | grep -E -xc - -std=c23 | grep 'struct _reent' -A91 | grep 580 -A91 | tail -n+2

        #[repr(C)]
        struct _reent {
            _errno: c_int,
            _stdin: *mut FILE,
            _stdout: *mut FILE,
            _stderr: *mut FILE,
            // other stuff
        }

        unsafe extern "C" {
            fn __getreent() -> *mut _reent;
        }

        unsafe { (*__getreent())._stdout }
    }

    #[cfg(not(any(
        target_vendor = "apple",
        target_os = "freebsd",
        target_os = "netbsd",
        target_os = "openbsd",
        target_os = "cygwin"
    )))]
    {
        unsafe extern "C" {
            static mut stdout: *mut FILE;
        }
        unsafe { stdout }
    }
}

/// # Safety
/// This function is unsafe because it calls a C API
#[unsafe(no_mangle)]
pub unsafe extern "C" fn __stdbuf_get_stderr() -> *mut FILE {
    #[cfg(any(target_vendor = "apple", target_os = "freebsd"))]
    {
        unsafe extern "C" {
            fn __stderrp() -> *mut FILE;
        }
        unsafe { __stderrp() }
    }

    #[cfg(target_os = "openbsd")]
    {
        unsafe extern "C" {
            static mut __stderr: *mut FILE;
        }
        unsafe { __stderr }
    }

    #[cfg(target_os = "netbsd")]
    {
        unsafe { libc::fdopen(2, c"w".as_ptr()) }
    }

    #[cfg(target_os = "cygwin")]
    {
        // _getreent()->_std{in,out,err}
        // see:
        // echo '#include <stdio.h>\nstd{in,out,err}' | gcc -E -xc - -std=c23 | tail -n1
        // echo '#include <stdio.h>' | grep -E -xc - -std=c23 | grep 'struct _reent' -A91 | grep 580 -A91 | tail -n+2

        #[repr(C)]
        struct _reent {
            _errno: c_int,
            _stdin: *mut FILE,
            _stdout: *mut FILE,
            _stderr: *mut FILE,
            // other stuff
        }

        unsafe extern "C" {
            fn __getreent() -> *mut _reent;
        }

        unsafe { (*__getreent())._stdin }
    }

    #[cfg(not(any(
        target_vendor = "apple",
        target_os = "freebsd",
        target_os = "netbsd",
        target_os = "openbsd",
        target_os = "cygwin"
    )))]
    {
        unsafe extern "C" {
            static mut stderr: *mut FILE;
        }
        unsafe { stderr }
    }
}

#[cfg(any(target_env = "ohos", test))]
fn ohos_allocation_size(mode: c_int, size: size_t) -> Option<size_t> {
    if mode == _IONBF {
        return Some(0);
    }
    // OHOS musl reserves eight bytes of caller-provided storage for ungetc.
    // Its setvbuf does not allocate storage or resize an existing buffer.
    // https://github.com/openharmony/third_party_musl/blob/master/src/stdio/setvbuf.c
    // https://github.com/openharmony/third_party_musl/blob/master/src/internal/stdio_impl.h
    let capacity = if size == 0 {
        libc::BUFSIZ as size_t
    } else {
        size
    };
    capacity.checked_add(8)
}

fn set_buffer(stream: *mut FILE, value: &str) {
    let (mode, size): (c_int, size_t) = match value {
        "0" => (_IONBF, 0_usize),
        "L" => (_IOLBF, 0_usize),
        input => {
            let Ok(buff_size) = input.parse::<usize>() else {
                let _ = writeln!(stderr(), "failed to allocate a {value} byte stdio buffer");
                std::process::exit(1);
            };
            (_IOFBF, buff_size as size_t)
        }
    };
    #[cfg(target_env = "ohos")]
    let (buffer, size) = {
        let allocation = ohos_allocation_size(mode, size).unwrap_or_else(|| {
            let _ = writeln!(stderr(), "failed to allocate a {value} byte stdio buffer");
            std::process::exit(1);
        });
        let buffer = if allocation == 0 {
            ptr::null_mut()
        } else {
            // SAFETY: malloc accepts the checked byte count. Successful storage
            // must outlive the FILE, so it stays allocated for the process lifetime.
            let buffer = unsafe { libc::malloc(allocation) }.cast::<c_char>();
            if buffer.is_null() {
                let _ = writeln!(stderr(), "failed to allocate a {value} byte stdio buffer");
                std::process::exit(1);
            }
            buffer
        };
        (buffer, allocation)
    };
    #[cfg(not(target_env = "ohos"))]
    let buffer: *mut c_char = ptr::null_mut();
    // SAFETY: stream is a standard FILE obtained from libc. The optional
    // buffer is writable for size bytes and remains allocated after success.
    let res = unsafe { libc::setvbuf(stream, buffer, mode, size) };
    if res != 0 {
        #[cfg(target_env = "ohos")]
        // SAFETY: rejected storage is not attached to the FILE; free accepts NULL.
        unsafe {
            libc::free(buffer.cast());
        };
        let _ = writeln!(
            stderr(),
            "could not set buffering of {} to mode {mode}",
            unsafe { fileno(stream) }
        );
    }
}

/// # Safety
/// This function is intended to be called automatically when the library is loaded via LD_PRELOAD.
/// It assumes that the standard streams are valid and that calling setvbuf on them is safe.
/// The caller must ensure this function is only called in a compatible runtime environment.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn __stdbuf() {
    if let Ok(val) = env::var("_STDBUF_E") {
        set_buffer(unsafe { __stdbuf_get_stderr() }, &val);
    }
    if let Ok(val) = env::var("_STDBUF_I") {
        set_buffer(unsafe { __stdbuf_get_stdin() }, &val);
    }
    if let Ok(val) = env::var("_STDBUF_O") {
        set_buffer(unsafe { __stdbuf_get_stdout() }, &val);
    }
}

#[cfg(test)]
mod ohos_tests {
    use super::*;

    #[test]
    fn explicit_capacity_includes_musl_pushback_storage() {
        assert_eq!(ohos_allocation_size(_IOFBF, 1), Some(9));
        assert_eq!(ohos_allocation_size(_IOFBF, 4096), Some(4104));
        assert_eq!(
            ohos_allocation_size(_IOLBF, 0),
            Some(libc::BUFSIZ as usize + 8)
        );
        assert_eq!(ohos_allocation_size(_IONBF, 0), Some(0));
    }

    #[test]
    fn buffer_capacity_overflow_is_rejected() {
        assert_eq!(ohos_allocation_size(_IOFBF, usize::MAX), None);
    }
}
