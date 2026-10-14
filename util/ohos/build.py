#!/usr/bin/env python3
"""Cross-compile the OHOS multicall binary and package it with the SDK hnpcli."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import stat
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "arm64-v8a": ("aarch64-unknown-linux-ohos", "aarch64-linux-ohos"),
    "x86_64": ("x86_64-unknown-linux-ohos", "x86_64-linux-ohos"),
    "armeabi-v7a": ("armv7-unknown-linux-ohos", "arm-linux-ohos"),
}


def sdk_root(path: Path) -> Path:
    for candidate in (path, path / "openharmony", path / "default/openharmony"):
        if (candidate / "native/llvm/bin/clang").is_file():
            return candidate.resolve()
    raise ValueError(f"OHOS SDK not found under {path}")


def package_links(utilities, library=False, probe=False):
    links = [{"source": "/bin/coreutils", "target": name} for name in ["coreutils", *utilities]]
    if library:
        links.append({"source": "/lib/libstdbuf.so", "target": "libstdbuf.so"})
    if probe:
        links.append({"source": "/bin/coreutils-stdio-probe", "target": ".coreutils-stdio-probe"})
    return links


def stage_package(binary: Path, utilities: list[str], version: str, stage: Path,
                  library: Path | None = None, probe: Path | None = None):
    if not utilities or len(set(utilities)) != len(utilities):
        raise ValueError("utility list is empty or contains duplicates")
    for name in utilities:
        if name != "[" and not (name.isascii() and name.replace("_", "").isalnum()):
            raise ValueError(f"invalid utility name: {name!r}")
    (stage / "bin").mkdir(parents=True)
    shutil.copyfile(binary, stage / "bin/coreutils")
    if library is not None:
        (stage / "lib").mkdir()
        shutil.copyfile(library, stage / "lib/libstdbuf.so")
    if probe is not None:
        shutil.copyfile(probe, stage / "bin/coreutils-stdio-probe")
    # HNP preserves host UGO modes; the app runs with 'other' permissions.
    (stage / "bin/coreutils").chmod(0o755)
    shutil.copyfile(ROOT / "LICENSE", stage / "LICENSE")
    config = {
        "type": "hnp-config",
        "name": "uutils-coreutils",
        "version": version,
        "install": {
            "links": package_links(utilities, library is not None, probe is not None)
        },
    }
    (stage / "hnp.json").write_text(json.dumps(config, indent=2) + "\n")
    (stage / "utilities.txt").write_text("\n".join(utilities) + "\n")
    for path in stage.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o755 if path.parent == stage / "bin" else 0o644)
    stage.chmod(0o755)


def verify_archive(archive: Path, utilities: list[str]):
    with zipfile.ZipFile(archive) as package:
        binaries = [item for item in package.infolist() if item.filename.endswith("/bin/coreutils")]
        if len(binaries) != 1 or (binaries[0].external_attr >> 16) & 0o777 != 0o755:
            raise ValueError("HNP must contain one coreutils executable with mode 0755")
        configs = [name for name in package.namelist() if name.endswith("/hnp.json")]
        if len(configs) != 1:
            raise ValueError("HNP must contain one hnp.json")
        links = json.loads(package.read(configs[0]))["install"]["links"]
        names = package.namelist()
        library = any(name.endswith("/lib/libstdbuf.so") for name in names)
        probe = any(name.endswith("/bin/coreutils-stdio-probe") for name in names)
        if "stdbuf" in utilities and not library:
            raise ValueError("stdbuf requires its prepackaged preload library")
        expected = package_links(utilities, library, probe)
        if links != expected:
            raise ValueError("HNP links do not match the compiled multicall utility list")


def normalize_archive(archive: Path):
    # Some macOS SDK hnpcli versions write 0xffffffff for every file's mode.
    # Correct ZIP Unix attributes before signing the HAP containing this HNP.
    temporary = archive.with_suffix(".tmp")
    try:
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(temporary, "w") as dest:
            for entry in source.infolist():
                data = source.read(entry)
                entry.create_system = 3
                if entry.is_dir():
                    entry.external_attr = ((stat.S_IFDIR | 0o755) << 16) | 0x10
                else:
                    mode = 0o755 if "/bin/" in entry.filename else 0o644
                    entry.external_attr = (stat.S_IFREG | mode) << 16
                dest.writestr(entry, data)
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)


def toolchain_environment(sdk: Path, arch: str, tools: Path):
    target, clang_target = TARGETS[arch]
    tools.mkdir(parents=True, exist_ok=True)
    for name in ("clang", "clang++"):
        wrapper = tools / name
        command = [str(sdk / "native/llvm/bin" / name), f"--target={clang_target}",
                   f"--sysroot={sdk / 'native/sysroot'}", "-D__MUSL__"]
        if arch == "armeabi-v7a":
            command.extend(["-march=armv7-a", "-mfloat-abi=softfp",
                            "-mtune=generic-armv7-a", "-mthumb"])
        wrapper.write_text("#!/bin/sh\nexec " + shlex.join(command) + ' "$@"\n')
        wrapper.chmod(0o755)
    env = os.environ.copy()
    suffix = target.replace("-", "_")
    env.update({
        "CARGO_TARGET_" + suffix.upper() + "_LINKER": str(tools / "clang"),
        "CC_" + suffix: str(tools / "clang"),
        "CXX_" + suffix: str(tools / "clang++"),
        "AR_" + suffix: str(sdk / "native/llvm/bin/llvm-ar"),
        "LIBSTDBUF_DIR": "/data/service/hnp/bin",
        "OHOS_NDK_HOME": str(sdk),
    })
    return env


def build(sdk: Path, arch: str, profile: str, output: Path, offline: bool, pty_probe=False,
          target_dir: Path | None = None, toolchain: str = "1.97.1"):
    target, _ = TARGETS[arch]
    target_dir = target_dir or ROOT / "target/ohos"
    tools = target_dir / "toolchain" / arch
    env = toolchain_environment(sdk, arch, tools)
    metadata = json.loads(subprocess.check_output(
        ["cargo", "+" + toolchain, "metadata", "--no-deps", "--format-version=1"], cwd=ROOT))
    package_id = next(p["id"] for p in metadata["packages"] if p["name"] == "coreutils")
    stdbuf_id = next(p["id"] for p in metadata["packages"] if p["name"] == "uu_stdbuf")
    command = ["cargo", "+" + toolchain, "build", "--target", target, "--profile", profile,
               "--target-dir", str(target_dir), "--no-default-features",
               "--features", "ohos,feat_diagnostics", "--bin", "coreutils",
               "--message-format=json-render-diagnostics"]
    if offline:
        command.append("--offline")
    binary = out_dir = stdbuf_out = None
    with subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True) as process:
        for line in process.stdout:
            message = json.loads(line)
            if message.get("reason") == "compiler-message":
                print(message["message"].get("rendered", ""), end="", file=sys.stderr)
            if message.get("package_id") == stdbuf_id and message.get("reason") == "build-script-executed":
                stdbuf_out = Path(message["out_dir"])
            if message.get("package_id") != package_id:
                continue
            if message["reason"] == "build-script-executed":
                out_dir = Path(message["out_dir"])
            if message["reason"] == "compiler-artifact" and message.get("executable"):
                binary = Path(message["executable"])
        if process.wait():
            raise RuntimeError("OHOS cargo build failed")
    if binary is None or out_dir is None or stdbuf_out is None:
        raise RuntimeError("Cargo did not report the multicall binary and build metadata")
    utilities = (out_dir / "utilities.txt").read_text().splitlines()
    version = tomllib.loads((ROOT / "Cargo.toml").read_text())["workspace"]["package"]["version"]
    output.mkdir(parents=True, exist_ok=True)
    stage = output / "uutils-coreutils"
    if stage.exists():
        shutil.rmtree(stage)
    probe = None
    if pty_probe:
        probe = tools / "coreutils-stdio-probe"
        subprocess.run([str(tools / "clang"), "-O2", "-Wall", "-Wextra", "-Werror",
                        "-fPIE", "-pie", str(ROOT / "util/ohos/stdio-probe.c"),
                        "-o", str(probe)], check=True)
    stage_package(binary, utilities, version, stage, stdbuf_out / "libstdbuf.so", probe)
    subprocess.run([str(sdk / "toolchains/hnpcli"), "pack", "-i", str(stage),
                    "-o", str(output)], check=True)
    archive = output / "uutils-coreutils.hnp"
    normalize_archive(archive)
    verify_archive(archive, utilities)
    print(f"{archive}: {len(utilities)} utilities, executable mode 0755")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=os.environ.get("OHOS_NDK_HOME"),
                        help="SDK root containing native/ and toolchains/ (or OHOS_NDK_HOME)")
    parser.add_argument("--arch", choices=TARGETS, default="arm64-v8a")
    parser.add_argument("--toolchain", default="1.97.1",
                        help="Rust toolchain with ARM32 time64 metadata support")
    parser.add_argument("--profile", choices=("dev", "release", "release-small"), default="release-small")
    parser.add_argument("--out", type=Path, help="Output directory (defaults to target/ohos/hnp/<arch>)")
    parser.add_argument("--target-dir", type=Path, help="Cargo cache directory (defaults to target/ohos)")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--pty-probe", action="store_true",
                        help="Include a signed C stdio fixture for real PTY buffering tests")
    args = parser.parse_args()
    if args.sdk is None:
        parser.error("set --sdk or OHOS_NDK_HOME")
    build(sdk_root(args.sdk), args.arch, args.profile,
          (args.out or ROOT / "target/ohos/hnp" / args.arch).resolve(), args.offline, args.pty_probe,
          args.target_dir.resolve() if args.target_dir else None, args.toolchain)


if __name__ == "__main__":
    main()
