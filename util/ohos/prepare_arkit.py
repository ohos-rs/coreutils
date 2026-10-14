#!/usr/bin/env python3
"""Stage a normal-permission HAP shell for the patched arkit terminal example."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from build import ROOT, sdk_root


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def prepare(arkit: Path, ability: Path, sdk: Path, output: Path):
    library = arkit / "dist/arm64-v8a/libcoreutils_terminal.so"
    if not library.is_file():
        raise ValueError("build coreutils_terminal with ohrs before staging the HAP")
    if not (ability / "native_ability/oh-package.json5").is_file():
        raise ValueError("--ability must point to the matching openharmony-ability checkout")
    if output.exists():
        raise ValueError(f"output already exists: {output}; choose a fresh staging directory")
    shutil.copytree(arkit / "app", output,
                    ignore=shutil.ignore_patterns("build", "oh_modules", ".hvigor", "libs", "hnp", "run.sh", "sign.sh"))
    profile = json.loads((output / "build-profile.json5").read_text())
    profile["app"].pop("signingConfigs", None)
    product = profile["app"]["products"][0]
    product.pop("signingConfig", None)
    product.update(compatibleSdkVersion="26.0.0", targetSdkVersion="26.0.0")
    profile["modules"] = [
        {"name": "native_ability", "srcPath": str(ability / "native_ability")},
        {"name": "entry", "srcPath": "./entry", "targets": [{"name": "default"}]},
    ]
    write_json(output / "build-profile.json5", profile)
    app = json.loads((output / "AppScope/app.json5").read_text())
    app["app"]["bundleName"] = "com.arkit.coreutils"
    write_json(output / "AppScope/app.json5", app)
    module = json.loads((output / "entry/src/main/module.json5").read_text())
    module["module"].pop("extensionAbilities", None)
    module["module"]["requestPermissions"] = []
    module["module"]["hnpPackages"] = [{"package": "uutils-coreutils.hnp", "type": "public"}]
    write_json(output / "entry/src/main/module.json5", module)
    types = output / "entry/src/main/cpp/types/libcoreutils_terminal"
    types.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(arkit / "dist/index.d.ts", types / "Index.d.ts")
    write_json(types / "oh-package.json5", {
        "name": "libcoreutils_terminal.so", "types": "./Index.d.ts", "version": "1.0.0",
    })
    write_json(output / "entry/oh-package.json5", {
        "name": "entry", "version": "1.0.0", "dependencies": {
            "libcoreutils_terminal.so": "file:./src/main/cpp/types/libcoreutils_terminal",
            "@ohos-rs/ability": "file:" + str(ability / "native_ability"),
        },
    })
    libs = output / "entry/libs/arm64-v8a"
    libs.mkdir(parents=True)
    for name in ("libcoreutils_terminal.so", "libc++_shared.so"):
        shutil.copyfile(arkit / "dist/arm64-v8a" / name, libs / name)
    subprocess.run([str(sdk / "native/llvm/bin/llvm-strip"),
                    str(libs / "libcoreutils_terminal.so")], check=True)
    (output / "entry/src/main/ets/entryability/EntryAbility.ets").write_text('''\
import { NativeAbility } from "@ohos-rs/ability";
import window from "@ohos.window";

export default class EntryAbility extends NativeAbility {
  public moduleName: string = "coreutils_terminal";
  public defaultPage: boolean = false;

  protected async loadWindowStageContent(windowStage: window.WindowStage): Promise<void> {
    try {
      await windowStage.loadContent("pages/Index");
    } catch (error) {
      console.error(`coreutils terminal window failed: ${String(error)}`);
      throw new Error(String(error));
    }
  }
}
''')
    index = output / "entry/src/main/ets/pages/Index.ets"
    index.write_text(index.read_text().replace('"demos"', '"coreutils_terminal"'))
    print(f"HAP shell: {output}; bundle=com.arkit.coreutils; requestPermissions=[]")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arkit", type=Path, required=True)
    parser.add_argument("--ability", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "target/ohos/arkit-app")
    args = parser.parse_args()
    prepare(args.arkit.resolve(), args.ability.resolve(), sdk_root(args.sdk), args.out.resolve())


if __name__ == "__main__":
    main()
