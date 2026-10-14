#!/usr/bin/env python3
"""Run OHOS ELF/ABI checks with qemu-user and real OHOS musl, as an ordinary user."""

# This file is part of the uutils coreutils package.
# For the full copyright and license information, please view the LICENSE file.

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import datetime
import hashlib
import json
import os
import pty
import select
import shutil
import subprocess
import tempfile
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--artifacts", type=Path, required=True)
parser.add_argument(
    "--launcher",
    type=Path,
    required=True,
    help="Statically linked native Linux executable built from fixtures/native-launcher.c",
)
parser.add_argument(
    "--target",
    action="append",
    choices=["aarch64-unknown-linux-ohos", "armv7-unknown-linux-ohos", "x86_64-unknown-linux-ohos"],
)
parser.add_argument("--timeout", type=float, default=45)
args = parser.parse_args()
ROOT = args.artifacts.resolve()
launcher = str(args.launcher.resolve())
MATRIX = [
    ("aarch64-unknown-linux-ohos", "qemu-aarch64"),
    ("armv7-unknown-linux-ohos", "qemu-arm"),
    ("x86_64-unknown-linux-ohos", "qemu-x86_64"),
]
results = {}
if os.getuid() == 0:
    parser.error("run as an ordinary UID to exercise file permissions")
for target, emulator in MATRIX:
    if args.target and target not in args.target:
        continue
    base = ROOT / target
    sysroot = base / "sysroot"
    cu = base / "bin/coreutils"
    probe = base / "bin/probe"
    work = Path(tempfile.mkdtemp(prefix="coreutils-" + target + "-"))
    master, slave = pty.openpty()
    tty = os.ttyname(slave)
    env = os.environ.copy()
    env.update(TZ="UTC", LC_ALL="C", UUTILS_OHOS_SESSION_DIR=str(work / "sessions"))
    library_path = str(sysroot / "lib") + ":" + str(base / "lib")
    prefix = [emulator, "-L", str(sysroot), "-E", "LD_LIBRARY_PATH=" + library_path]
    checks = []

    def run(command, *args, input=None, code=0, environment=None, stdin=None, timeout=args.timeout):
        result = subprocess.run(
            [*prefix, str(command), *map(str, args)],
            input=input,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment or env,
            timeout=timeout,
        )
        if result.returncode != code:
            raise AssertionError(
                f'{command.name} {args}: exit={result.returncode} expected={code}; stderr={result.stderr.decode(errors="replace")}'
            )
        return result.stdout.decode()

    def check(name, value=True):
        assert value, name
        checks.append(name)
        if len(checks) % 10 == 0:
            print(f"{target}: {len(checks)} checks passed ({name})", flush=True)

    def tool(*args, **kwargs):
        return run(cu, *args, **kwargs)

    entry = {
        "target": target,
        "qemu": emulator,
        "uid": os.getuid(),
        "status": "running",
        "checks": checks,
        "time_service": "explicit test fixture; IPC service unavailable in qemu-user",
        "libc_sha256": hashlib.sha256((sysroot / "lib/libc.so").read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(cu.read_bytes()).hexdigest(),
    }
    try:
        names = tool("--list").splitlines()
        check(
            "107 compiled applets match build map",
            len(names) == 107 and names == (base / "utilities.txt").read_text().splitlines(),
        )

        def version(name):
            output = tool(name, "--version")
            assert "uutils coreutils" in output, name

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(version, [n for n in names if n not in ["[", "test", "true", "false"]]))
        check("all versioned applets execute")
        tool("[", "-n", "qemu", "]")
        tool("test", "qemu", "=", "qemu")
        tool("true")
        tool("false", code=1)
        check("test/bracket/true/false aliases")
        check("ordinary UID", tool("id", "-u").strip() == str(os.getuid()))
        abi = json.loads(run(probe, "abi"))
        entry["sdk_abi"] = abi
        check(
            "SDK time64 and utmpx layout",
            abi["utmpx"] == 400 and abi["time_t"] == 8 and abi["ut_tv"] == 344,
        )
        source = work / "input"
        source.write_text("beta\nalpha\nalpha\n")
        dest = work / "copied"
        tool("cp", source, dest)
        tool("mv", dest, work / "moved")
        check("copy/move/read", tool("cat", work / "moved") == source.read_text())
        ordered = tool("sort", input=source.read_bytes())
        unique = tool("uniq", input=ordered.encode())
        check("pipeline", tool("wc", "-l", input=unique.encode()).strip() == "2")
        check(
            "sha256",
            tool("sha256sum", input=b"abc").split()[0]
            == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )
        check("base64", tool("base64", "-d", input=tool("base64", input=b"abc").encode()) == "abc")
        check("float formatting", tool("printf", "%.2f", "1.5") == "1.50")
        tool("chmod", "600", source)
        check("stat size and mode", tool("stat", "-c", "%s %a", source).strip() == "17 600")
        tool("chmod", "000", source)
        tool("cat", source, code=1)
        tool("chmod", "600", source)
        check("mode 000 denied for ordinary UID")
        tool("df", work)
        tool("du", "-b", source)
        check("statfs and disk usage")
        link = work / "link"
        tool("ln", "-s", source, link)
        check("symlink ABI", tool("readlink", link).strip() == str(source))
        check("TTY ABI", tool("tty", stdin=slave).strip() == tty)
        for zone, expected in [
            ("UTC0", "1970-01-01 00:00:00 +0000"),
            ("Asia/Shanghai", "1970-01-01 08:00:00 +0800"),
            ("America/New_York", "1969-12-31 19:00:00 -0500"),
        ]:
            zone_env = dict(env, TZ=zone)
            check(
                "TZ " + zone,
                tool("date", "-d", "@0", "+%F %T %z", environment=zone_env).strip() == expected,
            )
            os.utime(source, (0, 0))
            check(
                "mtime TZ " + zone,
                tool("date", "-r", source, "+%F %T %z", environment=zone_env).strip() == expected,
            )
        system_env = dict(env, COREUTILS_QEMU_SYSTEM_ZONE="Asia/Shanghai")
        system_env.pop("TZ")
        check(
            "TimeService callback fixture",
            tool("date", "-d", "@0", "+%H %z", environment=system_env).strip() == "08 +0800",
        )
        error_env = dict(env)
        error_env.pop("TZ")
        check(
            "TimeService unavailable fallback",
            tool("date", "-d", "@0", "+%H %z", environment=error_env).strip() == "00 +0000",
        )
        sessions = work / "sessions"
        sessions.mkdir(mode=0o700)
        record = sessions / "active.utmpx"
        run(probe, "record", record, os.getpid(), tty)
        check(
            "native C session record size/mode",
            record.stat().st_size == 800 and record.stat().st_mode & 0o777 == 0o600,
        )
        check("users reads C ABI", tool("users").strip() == "qemu-user")
        check("who reads C ABI", "qemu-user" in tool("who"))
        check("who current tty", "qemu-user" in tool("who", "-m", stdin=slave))
        check("pinky reads C ABI", "qemu-user" in tool("pinky", "-sf"))
        check("uptime session scope", "1 app PTY session" in tool("uptime"))
        now, boot = map(int, run(probe, "clock").split())
        since = tool("uptime", "-s").strip()
        since_epoch = int(
            datetime.datetime.strptime(since, "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=datetime.timezone.utc)
            .timestamp()
        )
        check("CLOCK_BOOTTIME agrees with native C", abs(now - since_epoch - boot) <= 2)
        bad = work / "bad.utmpx"
        bad.write_bytes(b"partial")
        tool("who", bad, code=1)
        tool("users", bad, code=1)
        tool("pinky", "-sf", environment=dict(env, UUTILS_OHOS_SESSION_DIR=str(bad)), code=1)
        check("truncated records rejected")
        child = [launcher, shutil.which(emulator), str(sysroot), str(probe)]
        # stdbuf locates the library beside its executable in this test directory.
        library_alias = base / "bin/libstdbuf.so"
        assert library_alias.is_file()

        def sample(mode, options=None, stream="stdout"):
            read_fd, write_fd = os.pipe()
            run_env = dict(
                env, COREUTILS_PROBE_READY_FD=str(write_fd), LD_LIBRARY_PATH=library_path
            )
            command = (
                [*prefix, str(cu), "stdbuf", *(options or []), *child, mode]
                if options
                else [*prefix, str(probe), mode]
            )
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=run_env,
                pass_fds=(write_fd,),
            )
            os.close(write_fd)
            try:
                if (
                    not select.select([read_fd], [], [], args.timeout)[0]
                    or os.read(read_fd, 1) != b"R"
                ):
                    raise AssertionError(
                        f"probe did not reach stdio write: {options}; {process.poll()}"
                    )
                selected = process.stdout if stream == "stdout" else process.stderr
                data = (
                    os.read(selected.fileno(), 4096)
                    if select.select([selected], [], [], 0.3)[0]
                    else b""
                )
                return data
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                os.close(read_fd)

        check("stdout full control", sample("stdout-buffered") == b"")
        for option, expected in [
            ("-o0", b"first\n"),
            ("-oL", b"first\n"),
            ("-o1", b"first\n"),
            ("-o4096", b""),
        ]:
            check("OHOS library preload " + option, sample("stdout", [option]) == expected)
        check("stderr default", sample("stderr", stream="stderr") == b"first\n")
        check("stderr capacity 4096", sample("stderr", ["-e4096"], stream="stderr") == b"")
        input_file = work / "stdio-input"
        input_file.write_bytes(b"0123456789")
        with input_file.open("rb") as source_file:
            check("stdin baseline offset", run(probe, "input", stdin=source_file).strip() == "10")
        with input_file.open("rb") as source_file:
            check(
                "stdin unbuffered offset",
                tool(
                    "stdbuf",
                    "-i0",
                    *child,
                    "input",
                    stdin=source_file,
                    environment=dict(env, LD_LIBRARY_PATH=library_path),
                ).strip()
                == "1",
            )
        sleep_child = [launcher, shutil.which(emulator), str(sysroot), str(cu), "sleep", "5"]
        tool(
            "timeout",
            "0.3",
            *sleep_child,
            code=124,
            environment=dict(env, LD_LIBRARY_PATH=library_path),
        )
        check("timeout child termination")
        unit_results = {}
        for label, filters in [
            ("coreutils", []),
            ("uucore", ["native_file"]),
            ("date", []),
            ("stdbuf", []),
        ]:
            test_binary = base / "bin" / ("test-" + label)
            unit_results[label] = run(test_binary, *filters, "--test-threads=1")
        entry["unit_tests"] = unit_results
        entry["unit_tests_passed"] = sum(
            int(re.search(r"test result: ok\. (\d+) passed", output).group(1))
            for output in unit_results.values()
        )
        entry["status"] = "passed"
    except Exception as error:
        entry["status"] = "failed"
        entry["error"] = str(error)
    finally:
        os.close(master)
        os.close(slave)
        shutil.rmtree(work)
    results[target] = entry
    print(target, entry["status"], len(checks), "checks", entry.get("error", ""), flush=True)
(ROOT / "runtime-results.json").write_text(json.dumps(results, indent=2) + "\n")
if any(item["status"] != "passed" for item in results.values()):
    raise SystemExit(1)
