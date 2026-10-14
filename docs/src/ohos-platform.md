<!-- spell-checker:ignore OHOS libstdbuf utmpx TimeService BOOTTIME -->

# OHOS platform support

The `ohos` feature selects the Unix utilities, with OHOS implementations for
system timezones, native session records and stdio buffering. The current
selection contains 107 multicall applets, including `[` and `dir`/`vdir`.
The platform feature shares the existing Unix feature sets instead of
maintaining a separate command list.

## Cross compilation

Install the official OHOS SDK and the Rust target. Set `OHOS_NDK_HOME` to the
SDK directory containing `native/`. For arm64:

```sh
rustup target add aarch64-unknown-linux-ohos
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER="$OHOS_NDK_HOME/native/llvm/bin/aarch64-unknown-linux-ohos-clang"
export CC_aarch64_unknown_linux_ohos="$CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER"
export CXX_aarch64_unknown_linux_ohos="$OHOS_NDK_HOME/native/llvm/bin/aarch64-unknown-linux-ohos-clang++"
export AR_aarch64_unknown_linux_ohos="$OHOS_NDK_HOME/native/llvm/bin/llvm-ar"
export CFLAGS_aarch64_unknown_linux_ohos=-D__MUSL__
export CXXFLAGS_aarch64_unknown_linux_ohos=-D__MUSL__
export LIBSTDBUF_DIR=/absolute/device/path/to/the/installed/library
cargo build --target aarch64-unknown-linux-ohos --no-default-features --features ohos
```

`LIBSTDBUF_DIR` is the target installation directory, not the host build
directory. `stdbuf` uses the existing external-library feature; the loader
must accept the separately installed `libstdbuf.so`. The OHOS library
allocates persistent buffers, including musl pushback storage, so explicit
capacities and stderr buffering take effect.

## Platform behaviour

`date` resolves `TZ` overrides through Jiff and its bundled timezone database.
Without an override, it reads the TimeService timezone ID and resolves it
against that same database. Current time, file modification times and clock
resolution reuse the selected timezone. Unknown or malformed SDK results
fall back to UTC, and historical daylight saving transitions are preserved.
See [Jiff's timezone documentation](https://docs.rs/jiff/latest/jiff/tz/struct.TimeZone.html).

OHOS lacks the libc utmpx database entry points. `who`, `users` and `pinky`
read native records supplied by an application's PTY provider, rather than
system account information. Set `UUTILS_OHOS_SESSION_DIR` to its record file
or directory; the default is
`/data/storage/el2/base/files/coreutils/sessions`. Directory sources accept
only private files owned by the current UID with a `.utmpx` extension. They
filter dead processes and reject truncated records. Each PTY provider must
write the target libc's native records and remove its record on normal close.
File-backed iterators are independent and do not acquire the libc database
lock. The command help explicitly describes the application session scope.

`uptime` uses `CLOCK_BOOTTIME` for system boot duration and `--since`, including
when application session data is unavailable. Its default output labels the
count as application PTY sessions; unavailable data is not reported as zero
system users. Load averages depend on libc support.

File ownership, device creation, system time changes, sandbox access and
loading native code remain subject to the platform's normal permissions.
Applications should use their own writable directories for `HOME`, `TMPDIR`
and session records.

## Tests

```sh
cargo test --bin coreutils --no-default-features --features ohos
cargo test -p uucore --features utmpx --lib native_file
cargo test -p uu_date --lib
cargo test -p uu_stdbuf_libstdbuf --lib
cargo test --test tests --no-default-features --features date -- test_date::test_timezone_override_for_epoch_and_reference
cargo fmt --all --check
```
