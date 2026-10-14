#!/usr/bin/env python3
"""Build three OHOS architectures and QEMU fixtures; never install or package them."""

# This file is part of the uutils coreutils package.
# For the full copyright and license information, please view the LICENSE file.

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "aarch64-unknown-linux-ohos": "aarch64",
    "armv7-unknown-linux-ohos": "arm",
    "x86_64-unknown-linux-ohos": "x86_64",
}
TESTS = {
    "coreutils": [
        "--bin",
        "coreutils",
        "--no-default-features",
        "--features",
        "ohos,feat_diagnostics",
    ],
    "uucore": ["-p", "uucore", "--features", "utmpx", "--lib"],
    "date": ["-p", "uu_date", "--lib"],
    "stdbuf": ["-p", "uu_stdbuf_libstdbuf", "--lib"],
}


def cargo(command, env, log):
    with log.open("w") as stream:
        result = subprocess.run(
            ["cargo", *command, "--message-format=json-render-diagnostics"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=stream,
        )
        messages = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        for message in messages:
            if message.get("reason") == "compiler-message":
                stream.write(message["message"].get("rendered") or "")
    if result.returncode:
        raise RuntimeError(f"Cargo failed: {log}")
    return messages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=os.environ.get("OHOS_NDK_HOME"))
    parser.add_argument(
        "--runtime",
        action="append",
        required=True,
        metavar="TARGET=LIBC_SO",
        help="Real OHOS musl runtime for each target, not the SDK's link stub",
    )
    parser.add_argument("--out", type=Path, default=ROOT / "target/ohos-qemu")
    parser.add_argument("--target-dir", type=Path, default=ROOT / "target/ohos-qemu/cargo")
    args = parser.parse_args()
    if args.sdk is None:
        parser.error("set --sdk or OHOS_NDK_HOME")
    sdk = args.sdk.resolve()
    runtimes = {}
    for entry in args.runtime:
        target, separator, path = entry.partition("=")
        if not separator or target not in TARGETS or target in runtimes:
            parser.error(f"invalid or duplicate runtime: {entry}")
        runtimes[target] = Path(path).resolve()
    if set(runtimes) != set(TARGETS):
        parser.error("supply a real libc.so for all three targets")
    output = args.out.resolve()
    metadata = json.loads(
        subprocess.check_output(["cargo", "metadata", "--no-deps", "--format-version=1"], cwd=ROOT)
    )
    ids = {package["name"]: package["id"] for package in metadata["packages"]}
    results = {}
    for target, loader in TARGETS.items():
        suffix = target.replace("-", "_")
        cc = sdk / "native/llvm/bin" / (target + "-clang")
        env = dict(
            os.environ,
            OHOS_NDK_HOME=str(sdk),
            CARGO_TARGET_DIR=str(args.target_dir.resolve()),
            CARGO_PROFILE_DEV_DEBUG="0",
            CARGO_PROFILE_TEST_DEBUG="0",
            CARGO_INCREMENTAL="0",
            CARGO_PROFILE_RELEASE_LTO="false",
            CARGO_PROFILE_RELEASE_CODEGEN_UNITS="16",
            CARGO_PROFILE_RELEASE_OPT_LEVEL="2",
            CARGO_PROFILE_RELEASE_PANIC="unwind",
            LIBSTDBUF_DIR="/opt/coreutils-ohos/lib",
        )
        env.update(
            {
                "CARGO_TARGET_" + suffix.upper() + "_LINKER": str(cc),
                "CC_" + suffix: str(cc),
                "CXX_" + suffix: str(sdk / "native/llvm/bin" / (target + "-clang++")),
                "AR_" + suffix: str(sdk / "native/llvm/bin/llvm-ar"),
            }
        )
        dest = output / target
        for folder in ("bin", "lib", "sysroot/lib"):
            (dest / folder).mkdir(parents=True, exist_ok=True)
        runtime = dest / "sysroot/lib/libc.so"
        if runtimes[target] != runtime:
            shutil.copyfile(runtimes[target], runtime)
        shutil.copyfile(runtime, dest / "sysroot/lib" / f"ld-musl-{loader}.so.1")
        fixtures = Path(__file__).parent / "fixtures"
        subprocess.run(
            [
                str(cc),
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-fPIC",
                "-shared",
                "-Wl,-soname,libtime_service_ndk.so",
                str(fixtures / "time-service.c"),
                "-o",
                str(dest / "sysroot/lib/libtime_service_ndk.so"),
            ],
            check=True,
        )
        subprocess.run(
            [
                str(cc),
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-fPIE",
                "-pie",
                str(fixtures / "probe.c"),
                "-o",
                str(dest / "bin/probe"),
            ],
            check=True,
        )
        messages = cargo(
            ["build", "--profile", "release", "--target", target, *TESTS["coreutils"]],
            env,
            dest / "build.log",
        )
        binary = next(
            Path(m["executable"])
            for m in messages
            if m.get("reason") == "compiler-artifact"
            and m.get("executable")
            and m["target"]["name"] == "coreutils"
        )
        out_dirs = {
            m["package_id"]: Path(m["out_dir"])
            for m in messages
            if m.get("reason") == "build-script-executed"
        }
        names = re.findall(
            r'\("([^"\\]+)", \(', (out_dirs[ids["coreutils"]] / "uutils_map.rs").read_text()
        )
        shutil.copyfile(binary, dest / "bin/coreutils")
        (dest / "bin/coreutils").chmod(0o755)
        shutil.copyfile(out_dirs[ids["uu_stdbuf"]] / "libstdbuf.so", dest / "lib/libstdbuf.so")
        shutil.copyfile(dest / "lib/libstdbuf.so", dest / "bin/libstdbuf.so")
        (dest / "utilities.txt").write_text("\n".join(names) + "\n")
        for label, options in TESTS.items():
            messages = cargo(
                ["test", "--no-run", "--target", target, *options],
                env,
                dest / f"build-test-{label}.log",
            )
            binary = next(
                Path(m["executable"])
                for m in messages
                if m.get("reason") == "compiler-artifact"
                and m.get("executable")
                and m["profile"]["test"]
            )
            shutil.copyfile(binary, dest / "bin" / ("test-" + label))
            (dest / "bin" / ("test-" + label)).chmod(0o755)
        results[target] = {
            "build": "passed",
            "applets": len(names),
            "profile": "release, opt=2, panic=unwind",
        }
        (output / "build-results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(f"{target}: {len(names)} applets and four test binaries built", flush=True)


if __name__ == "__main__":
    main()
