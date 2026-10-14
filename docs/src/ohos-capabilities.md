<!-- spell-checker:ignore OHOS HNP HAP utmpx libstdbuf ArkTS IPC BOOTTIME STARTUP LD_PRELOAD -->

# OHOS capability adaptation

The OHOS HNP now includes 107 applets. The five previously excluded utilities
have been adapted and exercised in an ordinary application's real PTY.
Application session data is explicitly scoped; privileged system operations
remain subject to normal platform policy.

| Capability | Official platform mechanism | Adaptation route |
| --- | --- | --- |
| `uptime` | `systemDateTime.getUptime(TimeType.STARTUP)` includes suspend time. | Implemented using `CLOCK_BOOTTIME`, independent of utmpx database functions. `--since` agrees with an independent SDK C clock query; default output labels its app PTY session count. Missing session data is reported as unavailable rather than zero users. Load averages are shown only if libc can retrieve them. |
| `who`, `users`, `pinky` | OSAccount manages HarmonyOS system accounts, which are distinct from terminal login sessions. | Implemented a native-record file reader and a real arkit PTY provider. The provider registers the actual shell PID, tty, Unix UID and timestamps with mode 0600, and removes records on normal PTY close. Dead processes are filtered; malformed data produces errors. These utilities report app-owned sessions, not all system logins. Their help text states that scope. |
| `stdbuf` | HNP signs native executables and dependent libraries. OHOS musl's `setvbuf` uses caller-provided buffers and reserves pushback storage. | Implemented with the existing external-library feature and a signed public `libstdbuf.so`. The OHOS library allocates persistent stream buffers, including pushback storage. Real C stdio tests passed for unbuffered, line, 1-byte and 4096-byte stdout, buffered stderr and unbuffered stdin. The tests demonstrate actual `LD_PRELOAD` effects. |
| `chcon`, `runcon` | SELinux and access-token policies are enforced by the OS; ordinary applications cannot administer system labels. | Requires a separately authorized system integration, rather than adding the commands to the normal-app feature set. |
| `chown`, `chroot`, `mknod`, setting the system clock | File ownership, Linux capabilities, application sandbox and platform authorization remain enforced after HNP installation. | Keep normal error/exit-code behaviour. Do not grant system privileges simply to make tests pass. App-owned file operations should be tested separately from privileged operations. |
| Executing or loading code | HAP/HNP code signing and, where needed, per-binary permission policy. | Package and sign code before installation. Verify the installed binary under the application's UID and PTY, rather than using shell-user results as evidence. |
| `ln -s` in app storage | The official file API documents that symlink creation is unavailable to third-party apps since API 11. The API 26 emulator also rejects the native syscall with `Permission denied`. | Preserve the failure and test it explicitly. Have HNP's system installer create command links at installation time. The sandbox exports need not appear as symlinks; validate the executable contents and command dispatch instead. |

Sources: [official system time API](https://github.com/openharmony/docs/blob/master/zh-cn/application-dev/reference/apis-basic-services-kit/js-apis-date-time.md),
[official system account API](https://github.com/openharmony/docs/blob/master/zh-cn/application-dev/reference/apis-basic-services-kit/js-apis-osAccount.md),
and [official HNP packaging guide](https://github.com/openharmony/startup_appspawn/blob/master/service/hnp/pack/README_zh.md).
The symlink restriction is documented in the
[official SDK file API](https://github.com/openharmony/interface_sdk-js/blob/master/api/%40ohos.file.fs.d.ts).
Buffer allocation follows the official
[musl setvbuf implementation](https://github.com/openharmony/third_party_musl/blob/master/src/stdio/setvbuf.c)
and [pushback storage definition](https://github.com/openharmony/third_party_musl/blob/master/src/internal/stdio_impl.h).
The test's full-buffering control is separate because OHOS
[writes stdout's first line before testing whether it is redirected](https://github.com/openharmony/third_party_musl/blob/master/src/stdio/__stdout_write.c).

The adaptation routes above are engineering conclusions from those API
contracts and the local SDK. They are not claims that the official platform
ships GNU-compatible versions of these utilities. In particular, declaring
that OSAccount represents every PTY login, or substituting an empty utmpx
shim, would hide missing functionality.

For API 26 and later, inspect the SDK's `hnpPackages.independentSign` and
per-binary permission/signing support when a native executable needs a kernel
permission. Only request the permissions that the binary actually needs.
The current coreutils test app has no requested application permissions and
does not require executable anonymous memory or unsigned-library loading.
The existence of a kernel-permission escape hatch is not evidence that a
normal app can change system security policy.
