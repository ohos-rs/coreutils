// This file is part of the uutils coreutils package.
// For license information, please view the LICENSE file.

//! Resolve the OHOS system timezone without changing the process environment.

use jiff::tz::TimeZone;
use std::ffi::CStr;

#[cfg(target_env = "ohos")]
pub(super) fn time_zone() -> TimeZone {
    #[link(name = "time_service_ndk")]
    unsafe extern "C" {
        fn OH_TimeService_GetTimeZone(tz: *mut libc::c_char, len: u32) -> i32;
    }

    // Let Jiff handle IANA names, POSIX rules and empty TZ overrides. Without
    // an override, OHOS needs TimeService instead of the usual zoneinfo files.
    if std::env::var_os("TZ").is_some()
        && let Ok(zone) = TimeZone::try_system()
    {
        return zone;
    }

    let mut buffer = [0u8; 64];
    // SAFETY: buffer is writable for the length passed to the SDK function.
    let result = unsafe { OH_TimeService_GetTimeZone(buffer.as_mut_ptr().cast(), 64) };
    if result != 0 {
        return TimeZone::UTC;
    }
    zone_from_buffer(&buffer)
}

fn zone_from_buffer(buffer: &[u8]) -> TimeZone {
    CStr::from_bytes_until_nul(buffer)
        .ok()
        .and_then(|name| name.to_str().ok())
        .and_then(|name| TimeZone::get(name).ok())
        .unwrap_or(TimeZone::UTC)
}

#[cfg(test)]
mod tests {
    use super::*;
    use jiff::Timestamp;

    #[test]
    fn system_zone_retains_historical_daylight_saving_rules() {
        let zone = zone_from_buffer(b"Asia/Shanghai\0");
        for (instant, expected_offset) in [
            ("1991-01-01T00:00:00Z", 8 * 3600),
            ("1991-07-01T00:00:00Z", 9 * 3600),
        ] {
            let timestamp: Timestamp = instant.parse().unwrap();
            assert_eq!(zone.to_offset(timestamp).seconds(), expected_offset);
        }
    }

    #[test]
    fn invalid_sdk_zone_buffers_fall_back_to_utc() {
        for buffer in [
            b"Asia/Shanghai".as_slice(),
            b"\xff\0",
            b"Unknown/Zone\0",
            b"\0",
        ] {
            assert_eq!(zone_from_buffer(buffer), TimeZone::UTC);
        }
    }
}
