#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline, module-only repack of the supported TB373FU vendor_boot v4 layout."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys


TARGET = "lib/modules/nt36532.ko"
LZ4_LEGACY = b"\x02\x21\x4c\x18"
HEADER_SIZE = 2128
TABLE_ENTRY_SIZE = 108


def align(value, boundary):
    return (value + boundary - 1) & ~(boundary - 1)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class CpioEntry:
    name: str
    mode: int
    links: int
    start: int
    body_start: int
    body_end: int
    end: int


def cpio_entries(data):
    """Parse one newc archive without extracting paths or following symlinks."""
    offset = 0
    seen = set()
    while offset + 110 <= len(data):
        header = data[offset:offset + 110]
        if header[:6] != b"070701" or not re.fullmatch(rb"[0-9a-fA-F]{104}", header[6:]):
            raise ValueError(f"unsupported or malformed CPIO header at {offset}")
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        name_end = offset + 110 + fields[11]
        if not fields[11] or name_end > len(data) or data[name_end - 1] != 0:
            raise ValueError(f"invalid CPIO name at {offset}")
        raw_name = data[offset + 110:name_end - 1]
        if b"\0" in raw_name or fields[12] != 0:
            raise ValueError(f"unsupported CPIO name/check field at {offset}")
        name = raw_name.decode("utf-8")
        name = "." if name == "./" else name.removeprefix("./")
        if (not name or "\\" in name or
                (name != "." and any(part in ("", ".", "..") for part in name.split("/")))):
            raise ValueError(f"unsafe or noncanonical CPIO path: {name!r}")
        if name in seen:
            raise ValueError(f"duplicate CPIO path: {name}")
        seen.add(name)
        body_start = align(name_end, 4)
        body_end = body_start + fields[6]
        entry_end = align(body_end, 4)
        if entry_end > len(data):
            raise ValueError(f"truncated CPIO entry: {name}")
        if name == "TRAILER!!!" and (raw_name != b"TRAILER!!!" or fields[6]):
            raise ValueError("malformed CPIO trailer")
        yield CpioEntry(name, fields[1], fields[4], offset, body_start, body_end, entry_end)
        offset = entry_end
        if name == "TRAILER!!!":
            if any(data[offset:]):
                raise ValueError("extra data or concatenated archive after CPIO trailer")
            return
    raise ValueError("missing or truncated CPIO trailer")


def replace_cpio_module(archive, module):
    entries = list(cpio_entries(archive))
    matches = [entry for entry in entries if entry.name == TARGET]
    if len(matches) != 1:
        raise ValueError(f"platform ramdisk must contain exactly one {TARGET}")
    target = matches[0]
    if not stat.S_ISREG(target.mode) or target.links != 1:
        raise ValueError("target module must be a regular file without hard links")
    if not module or len(module) > 0xffffffff:
        raise ValueError("invalid replacement module size")
    pieces = []
    for entry in entries:
        if entry.name == TARGET:
            header = bytearray(archive[entry.start:entry.body_start])
            header[54:62] = f"{len(module):08x}".encode("ascii")
            pieces.extend((bytes(header), module, bytes((-len(module)) % 4)))
        else:
            pieces.append(archive[entry.start:entry.end])
    pieces.append(archive[entries[-1].end:])
    updated = b"".join(pieces)
    updated += bytes((-len(updated)) % 512)
    checked = list(cpio_entries(updated))
    if [entry.name for entry in checked] != [entry.name for entry in entries]:
        raise ValueError("CPIO entry order changed")
    for old, new in zip(entries, checked):
        if old.name == TARGET:
            expected = bytearray(archive[old.start:old.body_start])
            expected[54:62] = f"{len(module):08x}".encode("ascii")
            if (updated[new.start:new.body_start] != expected or
                    updated[new.body_start:new.body_end] != module):
                raise ValueError("target CPIO replacement verification failed")
        elif archive[old.start:old.end] != updated[new.start:new.end]:
            raise ValueError(f"non-target CPIO entry changed: {old.name}")
    return updated


def module_info(data):
    """Check basic ELF identity, not kernel ABI, CRCs or a module signature."""
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("module must be ELF64 little-endian")
    kind, machine, version = struct.unpack_from("<HHI", data, 16)
    shoff = struct.unpack_from("<Q", data, 40)[0]
    ehsize = struct.unpack_from("<H", data, 52)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 58)
    if (kind != 1 or machine != 183 or version != 1 or ehsize != 64 or
            shentsize != 64 or shnum < 2 or not 0 < shstrndx < shnum or
            shoff < 64 or shoff + shnum * 64 > len(data)):
        raise ValueError("unsupported module ELF header; expected relocatable AArch64")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * 64) for i in range(shnum)]
    strings = sections[shstrndx]
    if strings[1] != 3 or not strings[5] or strings[4] + strings[5] > len(data):
        raise ValueError("invalid ELF section-name table")
    names = data[strings[4]:strings[4] + strings[5]]
    matches = []
    for section in sections:
        end = names.find(b"\0", section[0])
        if section[0] >= len(names) or end < 0:
            raise ValueError("invalid ELF section name")
        if names[section[0]:end] == b".modinfo":
            if section[1] != 1 or section[4] + section[5] > len(data):
                raise ValueError("invalid ELF .modinfo section")
            matches.append(data[section[4]:section[4] + section[5]])
    if len(matches) != 1 or not matches[0].endswith(b"\0"):
        raise ValueError("module must contain one terminated .modinfo section")
    fields = matches[0].split(b"\0")
    name = [field[5:] for field in fields if field.startswith(b"name=")]
    vermagic = [field[9:] for field in fields if field.startswith(b"vermagic=")]
    if name != [b"nt36532"] or len(vermagic) != 1 or not vermagic[0]:
        raise ValueError("module .modinfo must identify nt36532 and one vermagic")
    return {"name": "nt36532", "vermagic": vermagic[0].decode("ascii")}


def image_layout(data):
    """Accept only zero-padded, unsigned v4 platform + recovery containers."""
    if len(data) >= 64 and data[-64:-60] == b"AVBf":
        raise ValueError("AVB footer found; signing/AVB images are not supported")
    if len(data) < HEADER_SIZE or data[:8] != b"VNDRBOOT":
        raise ValueError("not a supported vendor_boot image")
    version, page = struct.unpack_from("<II", data, 8)
    ramdisk_size = struct.unpack_from("<I", data, 24)[0]
    header_size, dtb_size = struct.unpack_from("<II", data, 2096)
    table_size, count, entry_size, bootconfig_size = struct.unpack_from("<IIII", data, 2112)
    if (version != 4 or page not in (2048, 4096, 8192, 16384) or
            header_size != HEADER_SIZE or count != 2 or entry_size != TABLE_ENTRY_SIZE or
            table_size != count * entry_size or not ramdisk_size or not dtb_size):
        raise ValueError("unsupported vendor_boot layout; expected v4 platform + recovery with DTB")
    ramdisk_start = align(header_size, page)
    dtb_start = ramdisk_start + align(ramdisk_size, page)
    table_start = dtb_start + align(dtb_size, page)
    bootconfig_start = table_start + align(table_size, page)
    end = bootconfig_start + align(bootconfig_size, page)
    if end > len(data) or len(data) % page:
        raise ValueError("truncated or unaligned vendor_boot image")
    padding = ((header_size, ramdisk_start), (ramdisk_start + ramdisk_size, dtb_start),
               (dtb_start + dtb_size, table_start), (table_start + table_size, bootconfig_start),
               (bootconfig_start + bootconfig_size, len(data)))
    if any(any(data[first:last]) for first, last in padding):
        raise ValueError("nonzero padding/trailing metadata; signed or unknown images are unsupported")
    entries, ramdisks, names = [], [], set()
    next_offset = 0
    for index, expected_type in enumerate((1, 2)):
        offset = table_start + index * entry_size
        entry = data[offset:offset + entry_size]
        size, fragment_offset, kind = struct.unpack_from("<III", entry)
        name, separator, tail = entry[12:44].partition(b"\0")
        if (not separator or any(tail) or not re.fullmatch(rb"[A-Za-z0-9_.-]*", name) or
                name in (b".", b"..") or name in names):
            raise ValueError("unsupported or duplicate ramdisk name")
        names.add(name)
        if (kind != expected_type or fragment_offset != next_offset or not size or
                fragment_offset + size > ramdisk_size):
            raise ValueError("expected contiguous platform then recovery ramdisk fragments")
        entries.append(entry)
        ramdisks.append(data[ramdisk_start + fragment_offset:ramdisk_start + fragment_offset + size])
        next_offset += size
    if next_offset != ramdisk_size or not ramdisks[0].startswith(LZ4_LEGACY):
        raise ValueError("unsupported ramdisk extent or compression; expected legacy LZ4")
    return {"header": data[:HEADER_SIZE], "entries": entries, "ramdisks": ramdisks,
            "dtb": data[dtb_start:dtb_start + dtb_size],
            "bootconfig": data[bootconfig_start:bootconfig_start + bootconfig_size]}


def verify_layout(before, after):
    # Only aggregate ramdisk size, platform size and recovery offset may move.
    old_header, new_header = bytearray(before["header"]), bytearray(after["header"])
    old_header[24:28] = new_header[24:28] = bytes(4)
    if old_header != new_header:
        raise ValueError("unexpected vendor_boot header change")
    if (before["entries"][0][4:] != after["entries"][0][4:] or
            before["entries"][1][:4] != after["entries"][1][:4] or
            before["entries"][1][8:] != after["entries"][1][8:]):
        raise ValueError("unexpected ramdisk table metadata change")
    for name in ("dtb", "bootconfig"):
        if before[name] != after[name]:
            raise ValueError(f"unexpected modification: {name}")
    if before["ramdisks"][1] != after["ramdisks"][1]:
        raise ValueError("unexpected modification: recovery ramdisk")


def unpack_arguments(raw, unpack):
    if not raw or not raw.endswith(b"\0"):
        raise ValueError("unpacker must emit NUL-terminated mkbootimg arguments (-0)")
    argv = [part.decode("utf-8") for part in raw[:-1].split(b"\0")]
    single = {"--header_version", "--pagesize", "--base", "--kernel_offset", "--ramdisk_offset",
              "--tags_offset", "--dtb_offset", "--vendor_cmdline", "--board", "--dtb",
              "--vendor_bootconfig"}
    fragment_flags = {"--ramdisk_type", "--ramdisk_name"}
    seen, fragment_seen, fragments = set(), set(), []
    if len(argv) % 2:
        raise ValueError("malformed mkbootimg argument pairs")
    for index in range(0, len(argv), 2):
        option, value = argv[index:index + 2]
        if option in single:
            if option in seen or fragment_seen or fragments:
                raise ValueError(f"duplicate or misplaced argument: {option}")
            seen.add(option)
        elif option == "--vendor_ramdisk_fragment":
            if not fragment_flags.issubset(fragment_seen):
                raise ValueError("missing ramdisk fragment metadata")
            expected = unpack / f"vendor_ramdisk{len(fragments):02}"
            if Path(value).resolve() != expected.resolve():
                raise ValueError("unpacker referenced an unexpected ramdisk path")
            fragments.append(index + 1)
            fragment_seen.clear()
        elif option in fragment_flags or re.fullmatch(r"--board_id(?:[0-9]|1[0-5])", option):
            if option in fragment_seen:
                raise ValueError(f"duplicate fragment argument: {option}")
            fragment_seen.add(option)
        else:
            raise ValueError(f"unsupported mkbootimg argument: {option}")
        if option in ("--dtb", "--vendor_bootconfig"):
            name = "dtb" if option == "--dtb" else "bootconfig"
            if Path(value).resolve() != (unpack / name).resolve():
                raise ValueError(f"unpacker referenced an unexpected {name} path")
    if seen != single or len(fragments) != 2 or fragment_seen:
        raise ValueError("incomplete or unsupported mkbootimg arguments")
    return argv, fragments


def pad_image(path, size):
    data = path.read_bytes()
    if len(data) > size:
        raise ValueError("repacked image exceeds the base image size; refusing output")
    data += bytes(size - len(data))
    path.write_bytes(data)
    return data


def repack(args):
    if args.device != "TB373FU":
        raise ValueError("explicit --device TB373FU acknowledgement is required")
    for path, label in ((args.work, "work directory"), (args.output, "output")):
        if os.path.lexists(path) or not path.parent.is_dir():
            raise ValueError(f"{label} must be new and its parent must already exist")
    base_path, module_path = args.base.resolve(), args.module.resolve()
    work, output = args.work.resolve(), args.output.resolve()
    tools = args.kernel_tools.resolve()
    unpacker, mkbootimg = tools / "unpack_bootimg.py", tools / "mkbootimg.py"
    for path in (base_path, module_path, unpacker, mkbootimg):
        if not path.is_file():
            raise ValueError(f"required input file not found: {path}")
    executable = str(Path(args.lz4).resolve()) if args.lz4 else shutil.which("lz4")
    if not executable or not Path(executable).is_file():
        raise ValueError("lz4 executable not found; install it or provide --lz4")
    base, module = base_path.read_bytes(), module_path.read_bytes()
    before, replacement_info = image_layout(base), module_info(module)
    work.mkdir()
    snapshot = work / "base.img"
    snapshot.write_bytes(base)
    unpack = work / "unpack"
    python = [sys.executable, "-B", "-X", "utf8"]
    raw = subprocess.check_output([*python, str(unpacker), "--boot_img", str(snapshot),
                                   "--out", str(unpack), "--format=mkbootimg", "-0"])
    (work / "mkbootimg_args.bin").write_bytes(raw)
    argv, fragments = unpack_arguments(raw, unpack)
    expected_files = {"vendor_ramdisk00": before["ramdisks"][0],
                      "vendor_ramdisk01": before["ramdisks"][1],
                      "dtb": before["dtb"], "bootconfig": before["bootconfig"]}
    for name, expected in expected_files.items():
        if (unpack / name).read_bytes() != expected:
            raise ValueError(f"unpacker content mismatch: {name}")
    roundtrip = work / "vendor_boot_roundtrip.img"
    subprocess.run([*python, str(mkbootimg), *argv, "--vendor_boot", str(roundtrip)], check=True)
    if pad_image(roundtrip, len(base)) != base:
        raise ValueError("unchanged vendor_boot roundtrip is not byte-identical")
    archive = subprocess.check_output([executable, "-d", "-c", str(unpack / "vendor_ramdisk00")])
    updated = replace_cpio_module(archive, module)
    original_entry = next(entry for entry in cpio_entries(archive) if entry.name == TARGET)
    original_module = archive[original_entry.body_start:original_entry.body_end]
    original_info = module_info(original_module)
    compressed = subprocess.check_output([executable, "-l", "-12", "-c"], input=updated)
    replacement = work / "vendor_ramdisk00.repacked"
    replacement.write_bytes(compressed)
    argv[fragments[0]] = str(replacement)
    candidate = work / "vendor_boot_candidate.img"
    subprocess.run([*python, str(mkbootimg), *argv, "--vendor_boot", str(candidate)], check=True)
    packed = pad_image(candidate, len(base))
    after = image_layout(packed)
    verify_layout(before, after)
    verify = work / "verify"
    subprocess.run([*python, str(unpacker), "--boot_img", str(candidate), "--out", str(verify)],
                   check=True, stdout=subprocess.DEVNULL)
    for name, expected in expected_files.items():
        if name == "vendor_ramdisk00":
            expected = compressed
        if (verify / name).read_bytes() != expected:
            raise ValueError(f"repacked image content mismatch: {name}")
    recovered = subprocess.check_output([executable, "-d", "-c", str(verify / "vendor_ramdisk00")])
    if recovered != updated:
        raise ValueError("repacked CPIO does not match the verified module-only replacement")
    manifest = {
        "device_acknowledgement": "TB373FU",
        "base_sha256": sha256(base), "vendor_boot_sha256": sha256(packed), "size": len(packed),
        "module_sha256": sha256(module), "module_size": len(module),
        "module_vermagic": replacement_info["vermagic"],
        "original_module_vermagic": original_info["vermagic"],
        "cpio_changed_paths": [TARGET] if original_module != module else [],
        "base_roundtrip": "byte-identical",
        "non_target_cpio_headers_payloads_order": "byte-identical",
        "dtb_recovery_bootconfig": "byte-identical",
        "layout": "unsigned vendor_boot v4, platform + recovery, legacy LZ4/newc",
        "abi_check": "not performed; repacking is not kernel compatibility or boot validation",
        "avb_signing": "not supported; external vbmeta descriptors are not inspected",
    }
    (work / "repack_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # Exclusive creation also refuses an output created while the tools were running.
    stream = output.open("xb")
    try:
        with stream:
            stream.write(packed)
    except OSError:
        output.unlink(missing_ok=True)
        raise
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, choices=["TB373FU"],
                        help="acknowledge TB373FU only; this does not detect hardware or validate ABI")
    parser.add_argument("--base", required=True, type=Path, help="your exact unsigned vendor_boot backup")
    parser.add_argument("--module", required=True, type=Path, help="matching nt36532.ko")
    parser.add_argument("--output", required=True, type=Path, help="new output image; never overwritten")
    parser.add_argument("--work", required=True, type=Path, help="fresh work directory; retained for inspection")
    parser.add_argument("--kernel-tools", required=True, type=Path,
                        help="directory containing official mkbootimg.py and unpack_bootimg.py")
    parser.add_argument("--lz4", help="explicit lz4 executable path; default: find lz4 on PATH")
    args = parser.parse_args(argv)
    try:
        manifest = repack(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\nStop; no install was attempted. Any work directory is retained.\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
