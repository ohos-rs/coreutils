<!-- spell-checker:ignore OHOS HNP HAP arkit hvigor ohpm readelf libstdbuf utmpx musl hnpcli -->

# OHOS and HarmonyOS HNP integration

The `ohos` feature currently includes 107 applets, including `uptime`,
`who`, `users`, `pinky` and external-library `stdbuf`. The session tools read
real application-owned PTY records; they do not report all HarmonyOS system
logins. SELinux utilities are not enabled. The command list is generated from
the same map as `coreutils --list`, including `[` and the `dir`/`vdir` aliases.

## Build the HNP

Install Python 3.11+, Rust with the OHOS target, and the official OHOS SDK.
`OHOS_NDK_HOME` should contain `native/` and `toolchains/`.

```sh
rustup target add aarch64-unknown-linux-ohos
python3 util/ohos/build.py --sdk "$OHOS_NDK_HOME" --pty-probe
```

The default profile is `release-small`. Outputs are under
`target/ohos/hnp/arm64-v8a/`: `uutils-coreutils.hnp`, and an unpacked staging
directory containing the executable, MIT license, command list, and
`hnp.json`. `--profile dev`, `--offline`, `--out`, and `--arch` are supported.
Only arm64 has been exercised in the HarmonyOS emulator.

`--pty-probe` adds a small C stdio fixture used to verify actual buffering.
Omit it for a production package. `libstdbuf.so` is always packaged in `lib/`
and exported as `/data/service/hnp/bin/libstdbuf.so`, the compile-time search
path for external `stdbuf`. It is signed with the HNP before installation;
the command never extracts an unsigned library into application storage.

The package exports every compiled applet, plus the `coreutils` entry point,
using `install.links` to the single `/bin/coreutils` executable. HNP installation
creates these links; the package does not contain copied executables per
applet. Files use mode 0644, directories and the executable use 0755. The
packager also corrects the invalid ZIP attributes emitted by the tested macOS
`hnpcli`, and verifies the archive after packaging. This matters because
applications execute an installed HNP using the "other" permission bits.
See the [official HNP packaging guide](https://github.com/openharmony/startup_appspawn/blob/master/service/hnp/pack/README_zh.md).

## Integrate with arkit's real local PTY

Use a clean, disposable arkit checkout of `feat/terminal-local-pty` at
`7fd6a95`. The integration patch adds a separate `coreutils_terminal` native
entry and an opt-in `coreutils-hnp` terminal feature. It leaves ordinary
terminal examples on their existing path. From the coreutils checkout:

```sh
git -C "$ARKIT" apply "$PWD/util/ohos/arkit-terminal.patch"
cp util/ohos/pty-smoke.sh "$ARKIT/examples/terminal/src/coreutils-hnp-smoke.sh"
(cd "$ARKIT" && ohrs build --arch aarch -p coreutils_terminal)
python3 util/ohos/prepare_arkit.py --arkit "$ARKIT" \
  --ability "$OPENHARMONY_ABILITY" --sdk "$OHOS_NDK_HOME"
```

Use a Rust toolchain compatible with arkit's lockfile; the test used 1.97.1
with its OHOS target installed. The `openharmony-ability` HAR checkout must
match arkit's pinned revision `2b5defdb0a016b841736470f9c32f2929380c448`.
`prepare_arkit.py` stages a separate app under `target/ohos/arkit-app`, with
bundle name `com.arkit.coreutils`, API 26, and `requestPermissions: []`.
It does not retain the sample app's signing configuration.

Run `ohpm install` and `hvigorw assembleHap --mode module -p product=default
-p buildMode=debug --no-daemon` in the staged app using the DevEco SDK tools.
Set `DEVECO_SDK_HOME` to DevEco's `Contents/sdk` directory and `JAVA_HOME`
to its bundled `Contents/jbr/Contents/Home` on macOS. Include its
`Contents/tools/node/bin`, `Contents/tools/ohpm/bin` and
`Contents/tools/hvigor/bin` directories in `PATH`.
Then, from the coreutils checkout:

```sh
python3 util/ohos/attach_hnp.py \
  target/ohos/arkit-app/entry/build/default/outputs/default/entry-default-unsigned.hap \
  target/ohos/hnp/arm64-v8a/uutils-coreutils.hnp \
  target/ohos/coreutils-terminal-unsigned.hap
```

The attachment step adds the actual `hnp/arm64-v8a/uutils-coreutils.hnp`
payload and the public `hnpPackages` declaration. The tested hvigor preserved
the declaration but omitted the payload, so declaration-only checks are
insufficient. The official packing tool also supports `--hnp-path`.

Sign the resulting HAP with the official SDK tools and a valid normal-app
profile for the selected emulator. Enable HAP code signing (`sign-app
-signCode 1`) so the native libraries and executable inside the HNP are
covered. Merely signing the outer ZIP is insufficient. Signing material
stays outside the source tree. Install only on the explicitly selected device:

```sh
hdc -t "$HDC_TARGET" install -r target/ohos/coreutils-terminal-signed.hap
hdc -t "$HDC_TARGET" shell aa start -a EntryAbility -b com.arkit.coreutils
```

When replacing a changed HNP with the same package version, uninstall this
test app first. The HNP installer can reuse an already-installed version,
even after a HAP update; `--list` must show the expected 107 applets.

Click **Local PTY** first. Its status must change to `host=pty pid=...`.
Click **HNP probe** next. It sends the following to that real PTY before
running the embedded test script:

```sh
export PATH=/data/service/hnp/bin:$PATH
export HNP_BIN=/data/service/hnp/bin
( . /data/storage/el2/base/files/terminal/coreutils-hnp-smoke.sh )
```

The script is sourced in a subshell of the already-running interpreter:
starting a second `/system/bin/sh` from this PTY was rejected on the tested
emulator. The test uses explicit HNP paths, so shell builtins and system
utilities cannot satisfy its checks accidentally. It checks every exported
applet, controlling tty, pipelines, temporary files, copies, renames,
permissions, hashes, time formatting, timeouts, and exit codes. It also
requires mode-000 reads, sandbox-root listing and app-created symbolic links
to fail on API 26. It compares an exported command's contents with the
multicall binary: the sandbox can expose installed links as mounted files,
so `realpath` need not resolve different command names to one pathname.
`HOME` and the
working directory point at app-owned files; `TMPDIR` points at app-owned
cache. No root privileges or changes to SELinux policy are used.

The terminal registers its actual shell PID, tty, UID and timestamps in
`$HOME/sessions/<pid>.utmpx`, using the target libc's native record layout
and mode 0600. `UUTILS_OHOS_SESSION_DIR` selects this application-owned source.
Normal PTY close removes the record; the reader ignores records of dead
processes and rejects malformed data. `who`, `users` and `pinky` report only
these application sessions, as their help text states. `uptime` labels the
count as app PTY sessions and obtains boot duration from `CLOCK_BOOTTIME`,
including when session data is unavailable.

The C fixture checks signed `LD_PRELOAD` by observing stdout before a timed
exit, stderr buffering and stdin's underlying file offset. OHOS's first
stdout write has platform-specific behaviour, so the full-buffering control
is configured separately from the invocations affected by `stdbuf`.
The OHOS library supplies persistent caller-owned buffers, including musl's
pushback storage, to support explicit buffer sizes and buffered stderr.

The final marker is `COREUTILS_HNP_PASS`, and the UI reports `HNP probe passed`.
The transcript is saved inside the app at
`/data/storage/el2/base/files/terminal/coreutils-hnp-transcript.txt`.
To retrieve the corresponding app logs, use `hdc -t "$HDC_TARGET" shell
hilog -x -e 'coreutils-hnp:'`; `hdc hilog` itself does not forward these query
options.

After installation and launch, unlock the emulator and dismiss any system
first-run dialogs that cover the app. The same click sequence can then be
verified with an explicitly selected target; this saves the UI layout,
screenshot and logs:

```sh
python3 util/ohos/verify_pty.py --target "$HDC_TARGET"
```

## Checks

On 2026-10-14, the arm64 package passed the real Local PTY probe on a newly
created HarmonyOS 7.0.0.106 / API 26 emulator, using SDK 26.0.0.105. The app
ran as an ordinary UID with `requestPermissions: []`. All 107 applet exports,
the native session ABI, startup clock, signed stdio preload and permission
denials passed. The host checks passed 30 tests: 3 multicall tests, 3 record
reader tests, 2 buffer allocation tests, 8 HNP tests and 14 arkit PTY/input
tests. The production HNP contains the same validated binary and library,
with the C test fixture omitted.

```sh
python3 util/ohos/test_build.py
cargo test --bin coreutils --no-default-features --features ohos,feat_diagnostics
cargo fmt --all --check
python3 "$ARKIT/scripts/test-terminal-host.py" --toolchain 1.97.1 --offline
```

See [OHOS capability adaptation](ohos-capabilities.md) for the remaining
utility and permission boundaries.
