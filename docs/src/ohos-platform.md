<!-- spell-checker:ignore OHOS libstdbuf utmpx TimeService BOOTTIME -->

# OHOS platform support

The `ohos` feature selects the Unix utilities, with OHOS implementations for
system timezones, native session records and stdio buffering. The current
selection contains 107 multicall applets, including `[` and `dir`/`vdir`.
The platform feature shares the existing Unix feature sets instead of
maintaining a separate command list.

## Cross compilation

Install the official OHOS SDK and the Rust targets using Rust 1.97.1 or newer.
Rust 1.95's ARM32 standard library truncates file metadata timestamps after
2038; Rust 1.97.1 preserves their full width. Set `OHOS_NDK_HOME` to the
SDK directory containing `native/`. All three SDK architectures are supported:

| SDK ABI | Rust target | SDK compiler wrapper |
| --- | --- | --- |
| arm64-v8a | aarch64-unknown-linux-ohos | aarch64-unknown-linux-ohos-clang |
| armeabi-v7a | armv7-unknown-linux-ohos | armv7-unknown-linux-ohos-clang |
| x86_64 | x86_64-unknown-linux-ohos | x86_64-unknown-linux-ohos-clang |

For arm64:

```sh
rustup target add --toolchain 1.97.1 aarch64-unknown-linux-ohos armv7-unknown-linux-ohos x86_64-unknown-linux-ohos
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER="$OHOS_NDK_HOME/native/llvm/bin/aarch64-unknown-linux-ohos-clang"
export CC_aarch64_unknown_linux_ohos="$CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER"
export CXX_aarch64_unknown_linux_ohos="$OHOS_NDK_HOME/native/llvm/bin/aarch64-unknown-linux-ohos-clang++"
export AR_aarch64_unknown_linux_ohos="$OHOS_NDK_HOME/native/llvm/bin/llvm-ar"
export CFLAGS_aarch64_unknown_linux_ohos=-D__MUSL__
export CXXFLAGS_aarch64_unknown_linux_ohos=-D__MUSL__
export LIBSTDBUF_DIR=/absolute/device/path/to/the/installed/library
cargo +1.97.1 build --target aarch64-unknown-linux-ohos --no-default-features --features ohos
```

For another architecture, replace the Rust target and its environment-variable
suffix with the values from the table. Use the SDK compiler wrappers: the ARM32
wrapper supplies `-march=armv7-a -mfloat-abi=softfp -mtune=generic-armv7-a -mthumb`.
ARM32 also bundles the SDK's `native/llvm/lib/arm-linux-ohos/libunwind.a` in
utilities and the preload library. The whole archive is linked so standalone
utilities cannot accidentally resolve EHABI symbols against libc's SDK link
stub, which exports symbols absent from some actual OHOS runtimes.

The repository Cargo configuration enables `musl_redir_time64` for ARM32.
This matches the SDK header redirects while libc 0.2.190 selects time64
structures without redirecting the corresponding functions. Without it,
`timeout` can disarm its timer and calls using file timestamp structures
can pass the wrong layout.
When building outside this repository or overriding Rust flags, include
`--cfg musl_redir_time64` in the ARM32 target's Rust flags as well.

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
cargo test -p uucore --features utmpx,process --lib -- native_file timer_uses_the_native_time64_abi
cargo test -p uu_date --lib
cargo test -p uu_stdbuf_libstdbuf --lib
cargo test --test tests --no-default-features --features date -- test_date::test_timezone_override_for_epoch_and_reference
cargo fmt --all --check
```

## QEMU architecture checks

`util/ohos-qemu/build.py` builds all 107 applets and four Rust test binaries
for each architecture. Supply real OHOS musl `libc.so` files built for each
target. SDK sysroot libraries are link stubs and cannot serve as runtime
libraries. No OHOS system service is available in qemu-user, so the test-only
TimeService fixture returns a requested timezone or an error. It is never
installed with production artifacts.

```sh
python3 util/ohos-qemu/build.py --sdk "$OHOS_NDK_HOME" \
  --runtime aarch64-unknown-linux-ohos=/path/to/arm64/libc.so \
  --runtime armv7-unknown-linux-ohos=/path/to/arm32/libc.so \
  --runtime x86_64-unknown-linux-ohos=/path/to/x86_64/libc.so
```

On a Linux host with `qemu-aarch64`, `qemu-arm`, `qemu-x86_64`, Python 3 and
a native C compiler, build the static native exec adapter. It forwards guest
`LD_PRELOAD` to QEMU without loading the foreign library into QEMU itself.
Copy the built artifacts to that host if cross-compiling elsewhere, then run
as an ordinary UID with write access to the output directory:

```sh
cc -O2 -Wall -Wextra -Werror -static util/ohos-qemu/fixtures/native-launcher.c \
  -o target/ohos-qemu/native-launcher
python3 util/ohos-qemu/check.py --artifacts target/ohos-qemu \
  --launcher target/ohos-qemu/native-launcher
```

The JSON report records artifact hashes, SDK C layouts, all command entry
points, ordinary-user file permissions, PTY handling, time64 clocks and
session records, timezone resolution, C stdio buffering, child termination
and Rust tests including panic unwinding. QEMU validates the CPU and libc
ABI on Linux; platform access tokens, SELinux policy, native-code signing,
HNP installation and real TimeService IPC require a HarmonyOS device or
full system emulator.
