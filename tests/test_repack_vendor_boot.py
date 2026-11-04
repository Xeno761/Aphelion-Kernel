# SPDX-License-Identifier: GPL-2.0-only
"""Host fixtures only: no device, real LZ4 process, or kernel build is used."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import repack_vendor_boot as repacker


def cpio_entry(name, body=b"", mode=stat.S_IFREG | 0o640, links=1):
    name = name.encode() + b"\0"
    fields = [17, mode, 12, 34, links, 123456, len(body), 0, 0, 0, 0, len(name), 0]
    data = b"070701" + b"".join(f"{field:08x}".encode() for field in fields) + name
    data += bytes((-len(data)) % 4)
    data += body
    return data + bytes((-len(data)) % 4)


def cpio(module=b"old", extra=()):
    data = b"".join((cpio_entry(".", mode=stat.S_IFDIR | 0o755, links=2),
                     cpio_entry("./lib/modules/nt36532.ko", module),
                     cpio_entry("lib/modules/modules.load", b"nt36532.ko\nother.ko\n"),
                     cpio_entry("link", b"lib/modules", stat.S_IFLNK | 0o777),
                     *extra, cpio_entry("TRAILER!!!", mode=0)))
    return data + bytes((-len(data)) % 512)


def module(name="nt36532", vermagic="fixture-a SMP preempt mod_unload modversions aarch64"):
    strings = b"\0.shstrtab\0.modinfo\0"
    info = f"name={name}\0vermagic={vermagic}\0license=GPL\0".encode()
    data = bytearray(64)
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", data, 16, 1, 183, 1)
    data.extend(strings + info)
    data.extend(bytes((-len(data)) % 8))
    shoff = len(data)
    struct.pack_into("<Q", data, 40, shoff)
    struct.pack_into("<H", data, 52, 64)
    struct.pack_into("<HHH", data, 58, 64, 3, 1)
    data.extend(bytes(64))
    data.extend(struct.pack("<IIQQQQIIQQ", 1, 3, 0, 0, 64, len(strings), 0, 0, 1, 0))
    data.extend(struct.pack("<IIQQQQIIQQ", 11, 1, 0, 0, 64 + len(strings), len(info), 0, 0, 1, 0))
    return bytes(data)


def boot_image(platform, recovery=b"recovery fixture", dtb=b"dtb fixture", bootconfig=b"key=value\n",
               size=65536, header=None, entries=None):
    header = bytearray(header) if header is not None else bytearray(repacker.HEADER_SIZE)
    if not any(header):
        header[:8] = b"VNDRBOOT"
        struct.pack_into("<IIII", header, 8, 4, 4096, 0x40080000, 0x45000000)
        command_line = b"fixture command with gap"
        header[28:28 + len(command_line)] = command_line
        struct.pack_into("<II", header, 2096, repacker.HEADER_SIZE, len(dtb))
        struct.pack_into("<IIII", header, 2112, 216, 2, 108, len(bootconfig))
    struct.pack_into("<I", header, 24, len(platform) + len(recovery))
    if entries is None:
        entries = [struct.pack("<III32s16I", len(platform), 0, 1, b"platform", *range(16)),
                   struct.pack("<III32s16I", len(recovery), len(platform), 2, b"recovery", *range(16))]
    else:
        entries = [bytearray(entry) for entry in entries]
        struct.pack_into("<I", entries[0], 0, len(platform))
        struct.pack_into("<I", entries[1], 4, len(platform))
    data = b""
    page = struct.unpack_from("<I", header, 12)[0]
    for part in (bytes(header), platform + recovery, dtb, b"".join(entries), bootconfig):
        data += part
        data += bytes((-len(data)) % page)
    if len(data) > size:
        raise ValueError("fixture exceeds its image size")
    return data + bytes(size - len(data))


def null_args(directory):
    argv = ["--header_version", "4", "--pagesize", "4096", "--base", "0",
            "--kernel_offset", "1074266112", "--ramdisk_offset", "1157627904",
            "--tags_offset", "0", "--dtb_offset", "0", "--vendor_cmdline", "fixture command with gap",
            "--board", "", "--dtb", str(directory / "dtb"),
            "--vendor_bootconfig", str(directory / "bootconfig")]
    for index, name in enumerate(("platform", "recovery")):
        argv.extend(["--ramdisk_type", str(index + 1), "--ramdisk_name", name])
        for board_id in range(1, 16):
            argv.extend([f"--board_id{board_id}", str(board_id)])
        argv.extend(["--vendor_ramdisk_fragment", str(directory / f"vendor_ramdisk{index:02}")])
    return b"\0".join(value.encode() for value in argv) + b"\0"


class RepackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".repack-test-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = self.root / "kernel tools"
        self.tools.mkdir()
        for name in ("mkbootimg.py", "unpack_bootimg.py", "lz4"):
            (self.tools / name).write_bytes(b"host fixture only")
        self.original_module = module()
        self.new_module = module(vermagic="fixture-b SMP preempt mod_unload modversions aarch64")
        self.base_data = boot_image(repacker.LZ4_LEGACY + cpio(self.original_module))
        self.base = self.root / "my backup.img"
        self.base.write_bytes(self.base_data)
        self.ko = self.root / "nt36532.ko"
        self.ko.write_bytes(self.new_module)
        self.mode = "normal"

    def args(self, suffix=""):
        return argparse.Namespace(device="TB373FU", base=self.base, module=self.ko,
                                  work=self.root / f"fresh work{suffix}",
                                  output=self.root / f"new output{suffix}.img",
                                  kernel_tools=self.tools, lz4=str(self.tools / "lz4"))

    def fake_unpack(self, command):
        image = Path(command[command.index("--boot_img") + 1]).read_bytes()
        directory = Path(command[command.index("--out") + 1])
        directory.mkdir()
        layout = repacker.image_layout(image)
        for name, data in (("vendor_ramdisk00", layout["ramdisks"][0]),
                           ("vendor_ramdisk01", layout["ramdisks"][1]),
                           ("dtb", layout["dtb"]), ("bootconfig", layout["bootconfig"])):
            (directory / name).write_bytes(data)
        return null_args(directory)

    def fake_check_output(self, command, **kwargs):
        if any(Path(value).name == "unpack_bootimg.py" for value in command):
            self.assertIn("-0", command)
            return self.fake_unpack(command)
        self.assertEqual(Path(command[0]), self.tools / "lz4")
        if self.mode == "lz4-failure":
            raise subprocess.CalledProcessError(1, command)
        if "-d" in command:
            path = Path(command[-1])
            data = path.read_bytes()
            self.assertTrue(data.startswith(repacker.LZ4_LEGACY))
            if path.parent.name == "verify":
                if self.mode == "recovered-corrupt":
                    return data[4:] + b"unexpected"
                if self.mode == "late-output":
                    self.active_args.output.write_bytes(b"another process owns this output")
            return data[4:]
        self.assertEqual(command[1:], ["-l", "-12", "-c"])
        return repacker.LZ4_LEGACY + kwargs["input"]

    def fake_run(self, command, **kwargs):
        self.assertTrue(kwargs["check"])
        if any(Path(value).name == "unpack_bootimg.py" for value in command):
            self.fake_unpack(command)
            return subprocess.CompletedProcess(command, 0)
        script_index = next(i for i, value in enumerate(command) if Path(value).name == "mkbootimg.py")
        argv = command[script_index + 1:]
        pairs = list(zip(argv[::2], argv[1::2]))
        fragments = [Path(value).read_bytes() for option, value in pairs if option == "--vendor_ramdisk_fragment"]
        options = dict(pairs)
        output = Path(options["--vendor_boot"])
        original = repacker.image_layout(self.base_data)
        header = bytearray(original["header"])
        entries = [bytearray(entry) for entry in original["entries"]]
        dtb = Path(options["--dtb"]).read_bytes()
        bootconfig = Path(options["--vendor_bootconfig"]).read_bytes()
        is_candidate = output.name == "vendor_boot_candidate.img"
        if self.mode == "roundtrip-corrupt" and not is_candidate:
            header[16] ^= 1
        if is_candidate:
            if self.mode == "header-corrupt":
                header[20] ^= 1
            elif self.mode == "table-corrupt":
                entries[0][44] ^= 1
            elif self.mode == "dtb-corrupt":
                dtb = bytes([dtb[0] ^ 1]) + dtb[1:]
            elif self.mode == "recovery-corrupt":
                fragments[1] = bytes([fragments[1][0] ^ 1]) + fragments[1][1:]
            elif self.mode == "bootconfig-corrupt":
                bootconfig = bytes([bootconfig[0] ^ 1]) + bootconfig[1:]
            elif self.mode == "oversize":
                output.write_bytes(self.base_data + b"x")
                return subprocess.CompletedProcess(command, 0)
        image = boot_image(*fragments, dtb, bootconfig, size=len(self.base_data), header=header, entries=entries)
        page = struct.unpack_from("<I", header, 12)[0]
        used_size = sum(repacker.align(size, page) for size in
                        (len(header), len(fragments[0]) + len(fragments[1]), len(dtb), 216, len(bootconfig)))
        output.write_bytes(image[:used_size])
        return subprocess.CompletedProcess(command, 0)

    def run_fixture(self, args):
        self.active_args = args
        with mock.patch.object(repacker.subprocess, "check_output", side_effect=self.fake_check_output), \
                mock.patch.object(repacker.subprocess, "run", side_effect=self.fake_run):
            return repacker.repack(args)

    def test_cpio_preserves_headers_payloads_and_order(self):
        original = cpio()
        before = list(repacker.cpio_entries(original))
        for size in (1, 3, 4, 5, 511, 512, 2049):
            with self.subTest(size=size):
                replacement = b"x" * size
                updated = repacker.replace_cpio_module(original, replacement)
                after = list(repacker.cpio_entries(updated))
                self.assertEqual([e.name for e in before], [e.name for e in after])
                self.assertEqual(len(updated) % 512, 0)
                for old, new in zip(before, after):
                    if old.name == repacker.TARGET:
                        header = bytearray(original[old.start:old.body_start])
                        header[54:62] = f"{size:08x}".encode()
                        self.assertEqual(updated[new.start:new.body_start], header)
                        self.assertEqual(updated[new.body_start:new.body_end], replacement)
                    else:
                        self.assertEqual(original[old.start:old.end], updated[new.start:new.end])

    def test_cpio_rejects_duplicates_malformed_and_nonregular_targets(self):
        original = cpio()
        target = next(e for e in repacker.cpio_entries(original) if e.name == repacker.TARGET)
        bad_hex = bytearray(original)
        bad_hex[6] = ord(" ")
        bad_size = bytearray(original)
        bad_size[target.start + 54:target.start + 62] = b"ffffffff"
        bad_name = bytearray(original)
        bad_name[target.start + 111] = 0
        cases = [bytes(bad_hex), bytes(bad_size), bytes(bad_name), b"070702" + original[6:],
                 cpio(extra=[cpio_entry(repacker.TARGET)]), cpio(extra=[cpio_entry("../unsafe")]),
                 cpio(extra=[cpio_entry("/absolute")]), cpio(extra=[cpio_entry("x//y")]),
                 original + b"signature", original + cpio(), original[:target.end],
                 cpio_entry("TRAILER!!!", b"not empty"), cpio_entry("other") + cpio_entry("TRAILER!!!"),
                 cpio_entry(repacker.TARGET, mode=stat.S_IFLNK | 0o777) + cpio_entry("TRAILER!!!"),
                 cpio_entry(repacker.TARGET, links=2) + cpio_entry("TRAILER!!!")]
        for index, data in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                repacker.replace_cpio_module(data, b"new")

    def test_module_identity_and_elf_bounds(self):
        self.assertEqual(repacker.module_info(self.original_module)["name"], "nt36532")
        cases = [b"", self.original_module[:63], module(name="another_module")]
        for offset, fmt, value in ((4, "B", 1), (5, "B", 2), (16, "H", 2), (18, "H", 62),
                                   (40, "Q", 0xffffffffffffffff), (58, "H", 1),
                                   (60, "H", 0), (62, "H", 9)):
            data = bytearray(self.original_module)
            struct.pack_into("<" + fmt, data, offset, value)
            cases.append(bytes(data))
        data = bytearray(self.original_module)
        shoff = struct.unpack_from("<Q", data, 40)[0]
        struct.pack_into("<Q", data, shoff + 2 * 64 + 32, len(data) * 2)
        cases.append(bytes(data))
        for index, data in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                repacker.module_info(data)

    def test_layout_refuses_signatures_and_unknown_formats(self):
        layout = repacker.image_layout(self.base_data)
        self.assertEqual(layout["ramdisks"][1], b"recovery fixture")
        cases = [self.base_data[:-1], self.base_data[:100], b"ANDROID!" + self.base_data[8:]]
        footer = bytearray(self.base_data)
        footer[-64:-60] = b"AVBf"
        cases.append(bytes(footer))
        trailer = bytearray(self.base_data)
        trailer[-128:-119] = b"signature"
        cases.append(bytes(trailer))
        for offset, value in ((8, 3), (12, 1024), (2096, 2112), (2100, 0), (2116, 3), (2120, 112)):
            data = bytearray(self.base_data)
            struct.pack_into("<I", data, offset, value)
            cases.append(bytes(data))
        table_start = 4096 + repacker.align(len(layout["ramdisks"][0]) + len(layout["ramdisks"][1]), 4096) + 4096
        for offset, value in ((table_start + 8, 0), (table_start + 108 + 8, 1),
                              (table_start + 108 + 4, 0)):
            data = bytearray(self.base_data)
            struct.pack_into("<I", data, offset, value)
            cases.append(bytes(data))
        data = bytearray(self.base_data)
        data[table_start + 12:table_start + 15] = b"../"
        cases.append(bytes(data))
        data = bytearray(self.base_data)
        data[repacker.HEADER_SIZE] = 1
        cases.append(bytes(data))
        data = bytearray(self.base_data)
        data[4096:4100] = b"gzip"
        cases.append(bytes(data))
        for index, data in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                repacker.image_layout(data)

    def test_nul_arguments_keep_empty_and_spaced_values(self):
        directory = self.root / "unpack with spaces"
        raw = null_args(directory)
        argv, fragments = repacker.unpack_arguments(raw, directory)
        self.assertEqual(argv[argv.index("--board") + 1], "")
        self.assertEqual(argv[argv.index("--vendor_cmdline") + 1], "fixture command with gap")
        self.assertEqual(len(fragments), 2)
        self.assertEqual(Path(argv[fragments[0]]), directory / "vendor_ramdisk00")
        cases = [raw[:-1], raw + b"--vendor_boot\0outside.img\0", b"--header_version\0",
                 raw.replace(b"--dtb\0", b"--kernel\0"),
                 raw.replace(str(directory / "dtb").encode(), str(self.base).encode()),
                 raw.replace(b"vendor_ramdisk01", b"vendor_ramdisk00"),
                 b"--base\0" + b"0\0" + raw, raw.replace(b"platform", b"\xff")]
        for index, data in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                repacker.unpack_arguments(data, directory)

    def test_cli_acknowledgement_and_fresh_paths_are_required(self):
        for argv in ([], ["--device", "TB373FC"], ["--device", "TB373FU"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                repacker.main(argv)
            self.assertEqual(error.exception.code, 2)
        for label in ("device", "work", "output", "parent", "base", "module", "tools", "lz4"):
            args = self.args(label)
            if label == "device":
                args.device = "another device"
            elif label == "work":
                args.work.mkdir()
            elif label == "output":
                args.output.write_bytes(b"keep")
            elif label == "parent":
                args.output = self.root / "missing" / "output.img"
            elif label == "tools":
                args.kernel_tools = self.root / "missing tools"
            elif label in ("base", "module"):
                setattr(args, label, self.root / "missing input")
            elif label == "lz4":
                args.lz4 = str(self.root / "missing lz4")
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.run_fixture(args)
            if label == "output":
                self.assertEqual(args.output.read_bytes(), b"keep")
        args = self.args("sameinput")
        args.output = self.base
        with self.assertRaises(ValueError):
            self.run_fixture(args)
        self.assertEqual(self.base.read_bytes(), self.base_data)
        args = self.args("missingpathlz4")
        args.lz4 = None
        with mock.patch.object(repacker.shutil, "which", return_value=None), self.assertRaises(ValueError):
            self.run_fixture(args)

    def test_repack_end_to_end_on_host_fixture(self):
        cases = (("same-size", self.original_module, self.new_module, b"key=value\n"),
                 ("grown", self.original_module, self.new_module + bytes(8193), b"key=value\n"),
                 ("shrunken", self.original_module + bytes(8193), self.new_module, b"key=value\n"),
                 ("empty-bootconfig", self.original_module, self.new_module, b""))
        for label, original, replacement, bootconfig in cases:
            with self.subTest(label=label):
                self.base_data = boot_image(repacker.LZ4_LEGACY + cpio(original), bootconfig=bootconfig)
                self.base.write_bytes(self.base_data)
                self.ko.write_bytes(replacement)
                args = self.args(label)
                args.lz4 = None
                with mock.patch.object(repacker.shutil, "which", return_value=str(self.tools / "lz4")):
                    manifest = self.run_fixture(args)
                result = args.output.read_bytes()
                self.assertEqual(len(result), len(self.base_data))
                self.assertEqual(self.base.read_bytes(), self.base_data)
                self.assertEqual(self.ko.read_bytes(), replacement)
                self.assertEqual((args.work / "vendor_boot_roundtrip.img").read_bytes(), self.base_data)
                self.assertEqual(json.loads((args.work / "repack_manifest.json").read_text()), manifest)
                self.assertEqual(manifest["cpio_changed_paths"], [repacker.TARGET])
                self.assertEqual(manifest["vendor_boot_sha256"], repacker.sha256(result))
                self.assertIn("not performed", manifest["abi_check"])
                before, after = repacker.image_layout(self.base_data), repacker.image_layout(result)
                repacker.verify_layout(before, after)
                archive = after["ramdisks"][0][4:]
                target = next(e for e in repacker.cpio_entries(archive) if e.name == repacker.TARGET)
                self.assertEqual(archive[target.body_start:target.body_end], replacement)

    def test_failed_preservation_checks_never_create_output(self):
        for mode in ("roundtrip-corrupt", "header-corrupt", "table-corrupt", "dtb-corrupt",
                     "recovery-corrupt", "bootconfig-corrupt", "oversize", "recovered-corrupt"):
            self.mode = mode
            args = self.args(mode)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.run_fixture(args)
            self.assertFalse(args.output.exists())
            self.assertEqual(self.base.read_bytes(), self.base_data)
            self.assertEqual(self.ko.read_bytes(), self.new_module)

    def test_external_failure_and_late_output_collision_are_safe(self):
        self.mode = "lz4-failure"
        args = self.args("failure")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_fixture(args)
        self.assertFalse(args.output.exists())
        self.mode = "late-output"
        args = self.args("collision")
        with self.assertRaises(FileExistsError):
            self.run_fixture(args)
        self.assertEqual(args.output.read_bytes(), b"another process owns this output")
        self.assertEqual(self.base.read_bytes(), self.base_data)


if __name__ == "__main__":
    unittest.main()
