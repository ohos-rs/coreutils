#!/usr/bin/env python3
"""Regression tests for HNP links, attribution and executable permissions."""

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build import normalize_archive, stage_package, verify_archive
from attach_hnp import attach


class HnpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.binary = self.root / "coreutils"
        self.binary.write_bytes(b"ELF fixture")
        self.binary.chmod(0o700)
        self.stage = self.root / "uutils-coreutils"
        self.utilities = ["[", "cat", "ls", "test"]

    def archive(self, mode=0o755):
        path = self.root / "uutils-coreutils.hnp"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("uutils-coreutils/bin/coreutils")
            info.create_system = 3 if mode is not None else 0
            info.external_attr = (0o100000 | mode) << 16 if mode is not None else 0xffffffff
            archive.writestr(info, self.binary.read_bytes())
            archive.write(self.stage / "hnp.json", "uutils-coreutils/hnp.json")
            archive.write(self.stage / "utilities.txt", "uutils-coreutils/utilities.txt")
        return path

    def test_other_users_can_execute_and_read_attribution(self):
        stage_package(self.binary, self.utilities, "0.13.0", self.stage)
        self.assertEqual((self.stage / "bin/coreutils").stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.stage / "LICENSE").stat().st_mode & 0o777, 0o644)
        self.assertIn("MIT", (self.stage / "LICENSE").read_text())
        for directory in (self.stage, self.stage / "bin"):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
        verify_archive(self.archive(), self.utilities)

    def test_archive_rejects_owner_only_executable(self):
        stage_package(self.binary, self.utilities, "0.13.0", self.stage)
        with self.assertRaisesRegex(ValueError, "0755"):
            verify_archive(self.archive(0o700), self.utilities)

    def test_normalizes_macos_sdk_invalid_permission_attributes(self):
        stage_package(self.binary, self.utilities, "0.13.0", self.stage)
        archive = self.archive(None)
        normalize_archive(archive)
        verify_archive(archive, self.utilities)
        with zipfile.ZipFile(archive) as package:
            config = package.getinfo("uutils-coreutils/hnp.json")
            self.assertEqual(config.external_attr >> 16 & 0o777, 0o644)
            self.assertEqual(config.create_system, 3)

    def test_aliases_point_to_the_single_signed_executable(self):
        stage_package(self.binary, self.utilities, "0.13.0", self.stage)
        config = json.loads((self.stage / "hnp.json").read_text())
        links = config["install"]["links"]
        self.assertEqual([link["target"] for link in links], ["coreutils", *self.utilities])
        self.assertEqual({link["source"] for link in links}, {"/bin/coreutils"})
        config["install"]["links"].pop()
        (self.stage / "hnp.json").write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "compiled multicall"):
            verify_archive(self.archive(), self.utilities)

    def test_preload_library_is_packaged_and_exported_instead_of_extracted(self):
        library = self.root / "libstdbuf.so"
        library.write_bytes(b"signed-library fixture")
        stage_package(self.binary, ["stdbuf"], "0.13.0", self.stage, library=library)
        self.assertEqual((self.stage / "lib/libstdbuf.so").read_bytes(), library.read_bytes())
        self.assertEqual((self.stage / "lib/libstdbuf.so").stat().st_mode & 0o777, 0o644)
        config = json.loads((self.stage / "hnp.json").read_text())
        self.assertIn({"source": "/lib/libstdbuf.so", "target": "libstdbuf.so"}, config["install"]["links"])
        archive = self.root / "with-library.hnp"
        with zipfile.ZipFile(archive, "w") as package:
            for path in self.stage.rglob("*"):
                package.write(path, str(path.relative_to(self.root)))
        verify_archive(archive, ["stdbuf"])

    def test_stdbuf_without_prepackaged_library_is_rejected(self):
        self.utilities = ["stdbuf"]
        stage_package(self.binary, self.utilities, "0.13.0", self.stage)
        with self.assertRaisesRegex(ValueError, "prepackaged preload library"):
            verify_archive(self.archive(), self.utilities)

    def test_rejects_empty_duplicate_and_traversal_names(self):
        for names in ([], ["cat", "cat"], ["../cat"], ["/bin/cat"], ["cät"]):
            with self.subTest(names=names), self.assertRaises(ValueError):
                stage_package(self.binary, names, "0.13.0", self.stage)

    def test_hap_contains_public_declaration_and_exact_hnp_payload(self):
        stage_package(self.binary, self.utilities, "0.13.0", self.stage)
        hnp = self.archive()
        hap = self.root / "input-unsigned.hap"
        output = self.root / "output-unsigned.hap"
        with zipfile.ZipFile(hap, "w") as package:
            package.writestr("module.json", json.dumps({"module": {"requestPermissions": []}}))
            package.writestr("ets/modules.abc", b"existing bytecode")
        original = hap.read_bytes()
        attach(hap, hnp, output, "arm64-v8a")
        self.assertEqual(hap.read_bytes(), original)
        with zipfile.ZipFile(output) as package:
            config = json.loads(package.read("module.json"))
            self.assertEqual(config["module"]["requestPermissions"], [])
            self.assertEqual(config["module"]["hnpPackages"], [
                {"package": "uutils-coreutils.hnp", "type": "public"},
            ])
            self.assertEqual(package.read("hnp/arm64-v8a/uutils-coreutils.hnp"), hnp.read_bytes())
            self.assertEqual(package.read("ets/modules.abc"), b"existing bytecode")


if __name__ == "__main__":
    unittest.main()
