#!/system/bin/sh
# Run inside the application's real PTY, after setting HOME, TMPDIR and PATH.
set -eu
export LC_ALL=C
: "${HNP_BIN:?set HNP_BIN to the installed HNP link directory}"
: "${HOME:?set HOME to app-owned storage}"
: "${TMPDIR:?set TMPDIR to an app-owned cache directory}"
cu="$HNP_BIN/coreutils"

fail() {
    printf 'COREUTILS_HNP_FAIL: %s\n' "$*" >&2
    exit 1
}

require_text() {
    case "$1" in
        *"$2"*) ;;
        *) fail "expected output: $2; got: $1" ;;
    esac
}

"$cu" test -t 0 || fail 'stdin is not a PTY'
"$cu" test -t 1 || fail 'stdout is not a PTY'
"$cu" --version
printf 'uid=%s tty=%s size=%s\n' "$("$cu" id -u)" "$("$HNP_BIN/tty")" "$("$HNP_BIN/stty" size)"
"$cu" test "$("$cu" id -u)" -ne 0 || fail 'test must run as an ordinary app'
"$cu" test "$(command -v coreutils)" = "$cu" || fail 'wrong PATH'
"$HNP_BIN/cat" --version
"$HNP_BIN/ls" --version
"$HNP_BIN/date" --version
"$HNP_BIN/test" uutils = uutils
"$HNP_BIN/[" -n PTY ]
count=0
for name in $("$cu" --list); do
    "$cu" test -x "$HNP_BIN/$name" || fail "missing exported command: $name"
    case "$name" in '['|test|true|false) ;; *)
        version="$("$HNP_BIN/$name" --version)" || fail "cannot execute exported command: $name"
        case "$version" in *'uutils coreutils'*) ;; *) fail "wrong command: $name";; esac
    esac
    count=$((count + 1))
done
printf 'verified %s exported commands; executable mode=%s\n' "$count" "$("$cu" stat -Lc %a "$cu")"
"$cu" test "$("$cu" stat -Lc %a "$cu")" = 755 || fail 'unsafe HNP executable mode'
"$cu" env | "$cu" sort | "$cu" head -n 5

work="$("$HNP_BIN/mktemp" -d)"
case "$work" in "$TMPDIR"/*) ;; *) fail 'mktemp escaped TMPDIR';; esac
stage='file operations'
cleanup() {
    result=$?
    if [ "$result" -ne 0 ]; then
        printf 'COREUTILS_HNP_FAIL: stage=%s exit=%s\n' "$stage" "$result" >&2
    fi
    "$cu" chmod -R u+rwX "$work" || true
    "$cu" rm -rf "$work" || true
    exit "$result"
}
trap cleanup EXIT
"$cu" mkdir "$work/sub"
"$cu" printf 'beta\nalpha\nalpha\n' > "$work/input"
"$HNP_BIN/cp" "$work/input" "$work/sub/copy"
"$cu" test "$("$HNP_BIN/cat" "$work/input" | "$HNP_BIN/sort" | "$HNP_BIN/uniq" | "$HNP_BIN/wc" -l)" -eq 2
"$cu" test "$("$cu" wc -c < "$work/input")" -eq 17
"$HNP_BIN/mv" "$work/sub/copy" "$work/sub/moved"
if [ "${EXPECT_OHOS_SANDBOX:-0}" = 1 ]; then
    if "$cu" ln -s sub/moved "$work/link" 2> "$work/link-error"; then
        fail 'third-party application unexpectedly created a symlink'
    fi
    case "$("$cu" cat "$work/link-error")" in
        *'Permission denied'*) printf 'app symlink creation denied as expected\n';;
        *) fail 'wrong symlink error';;
    esac
    # The app sandbox can expose installed links as mounted regular files.
    "$cu" test "$("$cu" sha256sum < "$HNP_BIN/cat")" = "$("$cu" sha256sum < "$cu")"
    "$cu" test "$("$cu" realpath "$work/sub/moved")" = "$work/sub/moved"
else
    "$cu" ln -s sub/moved "$work/link"
    "$cu" test "$("$cu" readlink "$work/link")" = sub/moved
    "$cu" test "$("$cu" realpath "$work/link")" = "$work/sub/moved"
fi
stage='metadata and encodings'
"$cu" chmod 600 "$work/sub/moved"
"$cu" test "$("$cu" stat -c %a "$work/sub/moved")" = 600
"$cu" touch "$work/empty"
"$cu" test "$("$cu" stat -c %s "$work/empty")" = 0
"$cu" test "$("$cu" printf abc | "$cu" sha256sum | "$cu" cut -d ' ' -f 1)" = ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
"$cu" test "$("$cu" printf abc | "$cu" base64 | "$cu" base64 -d)" = abc
"$cu" test "$("$cu" seq 1 3 | "$cu" tail -n 1)" = 3
"$cu" test "$("$cu" date -u -d @0 +%F)" = 1970-01-01
printf 'passed file operations, metadata, hashes, encodings and dates\n'
stage='timeouts'
"$cu" timeout 2 "$cu" sleep 0.01
if "$cu" timeout 0.1 "$cu" sleep 5; then fail 'timeout did not terminate child'; else
    "$cu" test "$?" -eq 124 || fail 'wrong timeout exit code'
fi

# Validate enforcement with an app-owned file, without changing system policy.
stage='permission enforcement'
"$cu" chmod 000 "$work/input"
if "$HNP_BIN/cat" "$work/input" > "$work/denied-output" 2> "$work/denied-error"; then
    fail 'read of mode 000 succeeded'
fi
"$cu" test -s "$work/denied-error" || fail 'permission error was suppressed'
"$cu" chmod 600 "$work/input"
"$cu" ls -la "$HOME"
if [ "${EXPECT_OHOS_SANDBOX:-0}" = 1 ]; then
    if "$HNP_BIN/ls" / > "$work/root-output" 2> "$work/root-error"; then
        fail 'sandbox root unexpectedly readable'
    fi
    "$cu" test -s "$work/root-error" || fail 'sandbox error was suppressed'
fi
printf 'passed timeouts and app permission enforcement\n'
if [ "${EXPECT_OHOS_SANDBOX:-0}" = 1 ]; then
    stage='application PTY sessions and uptime'
    : "${UUTILS_OHOS_SESSION_DIR:?PTY session provider is missing}"
    uid="$("$cu" id -u)"
    "$cu" test "$("$HNP_BIN/users")" = "$uid"
    require_text "$("$HNP_BIN/who")" "$("$HNP_BIN/tty" | "$cu" cut -c 6-)"
    require_text "$("$HNP_BIN/who" -m)" "$uid"
    "$cu" test "$("$HNP_BIN/who" -q | "$cu" tail -n 1 | "$cu" cut -d = -f 2)" -eq 1
    require_text "$("$HNP_BIN/pinky" -sf)" "$uid"
    require_text "$("$HNP_BIN/uptime")" '1 app PTY session'
    require_text "$("$HNP_BIN/uptime" -p)" up
    probe="$HNP_BIN/.coreutils-stdio-probe"
    "$cu" test -x "$probe" || fail 'signed C stdio fixture is missing'
    export TZ=UTC
    since="$("$HNP_BIN/uptime" -s)"
    duration=$(( $("$cu" date -u +%s) - $("$cu" date -u -d "$since" +%s) ))
    sdk_duration="$("$probe" uptime)"
    "$cu" test "$duration" -ge "$((sdk_duration - 2))"
    "$cu" test "$duration" -le "$((sdk_duration + 2))"
    "$cu" test "$("$cu" stat -c %a "$UUTILS_OHOS_SESSION_DIR/$$.utmpx")" = 600
    "$cu" test "$("$cu" stat -c %s "$UUTILS_OHOS_SESSION_DIR/$$.utmpx")" -eq "$((2 * $("$probe" utmpx-size)))"
    "$cu" printf malformed > "$work/bad.utmpx"
    for command in who users; do
        if "$HNP_BIN/$command" "$work/bad.utmpx" > "$work/bad-output" 2> "$work/bad-error"; then
            fail "$command accepted a truncated session record"
        fi
        "$cu" test -s "$work/bad-error"
    done
    if "$cu" env UUTILS_OHOS_SESSION_DIR="$work/bad.utmpx" "$HNP_BIN/pinky" -sf > "$work/bad-output" 2> "$work/bad-error"; then
        fail 'pinky accepted a truncated session record'
    fi
    "$cu" test -s "$work/bad-error"
    printf 'passed real app PTY records, native ABI, mode 0600 and startup clock\n'

    stage='signed C stdout preload'
    short_run() {
        if "$cu" timeout 0.3 "$@"; then
            fail 'stdio fixture exited before timeout'
        else
            "$cu" test "$?" -eq 124 || fail 'stdio fixture timeout status changed'
        fi
    }
    # OHOS writes stdout's first line before it detects a redirected stream.
    # Use a separately configured full-buffering control, without changing
    # buffering in the stdbuf-controlled invocations below.
    short_run "$probe" stdout-buffered > "$work/buffer-default"
    "$cu" test ! -s "$work/buffer-default"
    short_run "$HNP_BIN/stdbuf" -o0 "$probe" stdout > "$work/buffer-none"
    "$cu" test "$("$cu" cat "$work/buffer-none")" = first
    short_run "$HNP_BIN/stdbuf" -oL "$probe" stdout > "$work/buffer-line"
    "$cu" test "$("$cu" cat "$work/buffer-line")" = first
    short_run "$HNP_BIN/stdbuf" -o4096 "$probe" stdout > "$work/buffer-full"
    "$cu" test ! -s "$work/buffer-full"
    short_run "$HNP_BIN/stdbuf" -o1 "$probe" stdout > "$work/buffer-one"
    "$cu" test "$("$cu" cat "$work/buffer-one")" = first
    printf 'passed signed C stdout unbuffered, line and full buffering\n'
    stage='signed C stderr preload'
    short_run "$probe" stderr 2> "$work/error-default"
    "$cu" test "$("$cu" cat "$work/error-default")" = first
    short_run "$HNP_BIN/stdbuf" -e4096 "$probe" stderr 2> "$work/error-buffered"
    "$cu" test ! -s "$work/error-buffered"
    stage='signed C stdin preload'
    "$cu" printf 0123456789 > "$work/stdio-input"
    "$cu" test "$("$probe" input < "$work/stdio-input")" -eq 10
    "$cu" test "$("$HNP_BIN/stdbuf" -i0 "$probe" input < "$work/stdio-input")" -eq 1
    printf 'passed signed LD_PRELOAD: real C stdin, stdout and stderr buffering\n'
fi
stage='exit codes'
if "$HNP_BIN/false"; then fail 'false exit code lost'; else
    "$cu" test "$?" -eq 1 || fail 'wrong false exit code'
fi
"$HNP_BIN/true"
# Split the marker so the PTY's echoed command cannot produce a false success.
printf 'COREUTILS_HNP_%s\n' PASS
