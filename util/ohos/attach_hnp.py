#!/usr/bin/env python3
"""Add the public coreutils HNP to an unsigned HAP before code signing."""

import argparse
import json
from pathlib import Path
import zipfile

from build import TARGETS, verify_archive


def attach(hap: Path, hnp: Path, output: Path, arch: str):
    if output.resolve() == hap.resolve():
        raise ValueError("output must differ from the input unsigned HAP")
    with zipfile.ZipFile(hnp) as package:
        utilities = next(name for name in package.namelist() if name.endswith("/utilities.txt"))
        names = package.read(utilities).decode().splitlines()
    verify_archive(hnp, names)
    hnp_path = f"hnp/{arch}/uutils-coreutils.hnp"
    with zipfile.ZipFile(hap) as source:
        config = json.loads(source.read("module.json"))
        packages = config["module"].setdefault("hnpPackages", [])
        packages[:] = [p for p in packages if p["package"] != "uutils-coreutils.hnp"]
        packages.append({"package": "uutils-coreutils.hnp", "type": "public"})
        with zipfile.ZipFile(output, "w") as dest:
            for entry in source.infolist():
                if entry.filename == hnp_path:
                    continue
                data = (json.dumps(config, separators=(",", ":")).encode()
                        if entry.filename == "module.json" else source.read(entry))
                dest.writestr(entry, data)
            dest.write(hnp, hnp_path, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output) as result:
        if result.read(hnp_path) != hnp.read_bytes():
            raise ValueError("HAP contains a different HNP payload")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hap", type=Path, help="Unsigned HAP produced by hvigor")
    parser.add_argument("hnp", type=Path)
    parser.add_argument("output", type=Path, help="New unsigned HAP; sign this file afterwards")
    parser.add_argument("--arch", choices=TARGETS, default="arm64-v8a")
    args = parser.parse_args()
    attach(args.hap, args.hnp, args.output, args.arch)
    print(f"{args.output}: public HNP included; HAP code signing is still required")


if __name__ == "__main__":
    main()
