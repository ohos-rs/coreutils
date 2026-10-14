#!/usr/bin/env python3
"""Verify the HNP through Local PTY on one explicitly selected emulator."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from build import ROOT


def verify(target: str, bundle: str, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    hdc = ["hdc", "-t", target]

    def run(*args):
        result = subprocess.check_output([*hdc, *args], text=True, stderr=subprocess.STDOUT)
        if "[Fail]" in result:
            raise RuntimeError(result.strip())
        return result

    def layout():
        remote = "/data/local/tmp/coreutils-hnp-layout.json"
        run("shell", "uitest", "dumpLayout", "-b", bundle, "-p", remote)
        run("file", "recv", remote, str(output / "layout.json"))
        tree = json.loads((output / "layout.json").read_text())

        def nodes(value):
            if isinstance(value, dict):
                if "attributes" in value:
                    yield value["attributes"]
                for child in value.values():
                    yield from nodes(child)
            elif isinstance(value, list):
                for child in value:
                    yield from nodes(child)

        return list(nodes(tree))

    def wait_for(predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            state = layout()
            for node in state:
                if predicate(node):
                    return node
            time.sleep(0.5)
        raise RuntimeError("expected PTY state did not appear; inspect layout.json and app logs")

    def click(label):
        node = wait_for(lambda n: n.get("text") == label and n.get("type") == "Button")
        bounds = [int(v) for v in re.findall(r"-?\d+", node["bounds"])]
        if len(bounds) != 4 or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise RuntimeError(f"invalid bounds for {label}")
        run("shell", "uitest", "uiInput", "click", str((bounds[0] + bounds[2]) // 2),
            str((bounds[1] + bounds[3]) // 2))

    click("Local PTY")
    wait_for(lambda n: "host=pty pid=" in n.get("text", ""))
    click("HNP probe")
    result = wait_for(lambda n: "HNP probe passed" in n.get("text", "")
                      or "HNP probe failed" in n.get("text", ""))
    # Query options belong to the device's hilog, not hdc's hilog shortcut.
    logs = run("shell", "hilog", "-x", "-e", "coreutils-hnp:")
    (output / "pty-events.log").write_text(logs)
    remote = "/data/local/tmp/coreutils-hnp-result.png"
    run("shell", "uitest", "screenCap", "-p", remote)
    run("file", "recv", remote, str(output / "result.png"))
    if "HNP probe passed" not in result["text"]:
        raise RuntimeError(f"{result['text']}; see {output / 'pty-events.log'}")
    print(f"{target}: {result['text']}")
    print(f"Evidence: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Required explicit hdc connect key")
    parser.add_argument("--bundle", default="com.arkit.coreutils")
    parser.add_argument("--out", type=Path, default=ROOT / "target/ohos/verification")
    args = parser.parse_args()
    verify(args.target, args.bundle, args.out.resolve())


if __name__ == "__main__":
    main()
