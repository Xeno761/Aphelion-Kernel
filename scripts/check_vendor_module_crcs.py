#!/usr/bin/env python3
"""Strict, read-only ARM vendor modversion CRC audit (Python standard library).

Exit 1 on any CRC mismatch, malformed/unreadable input, missing required version
data, ambiguous provider CRC, or empty/incomplete module discovery. There are no
baseline waivers. Exit 0 covers only the comparisons reported, not symbol
resolution, signatures, ABI layout equivalence, Android boot, or hardware tests.
Absent exports must also be checked by audit_vendor_symbols.py. Module-provider
comparisons cover the supplied stock .ko files, not unprovided rebuilt modules.
"""

import argparse
import hashlib
import os
import re
import stat
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SYMVERS = "/root/Aphelion-Kernel-out/vmlinux.symvers"
DEFAULT_MODULE_DIRS = (
    "/root/inspect_modules/lib/modules",
    "/root/inspect_modules/vendor_dlkm_stock/lib/modules",
)
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.$]*\Z")
MAX_MODULE_BYTES = 256 * 1024 * 1024
SHN_ABS = 0xFFF1
ABS_WIDTHS = {(40, 2): 4, (183, 257): 8, (183, 258): 4, (183, 259): 2}
RELOC_WIDTHS = ABS_WIDTHS.copy()
RELOC_WIDTHS.update({(40, 3): 4, (183, 260): 8, (183, 261): 4, (183, 262): 2})


class AuditError(ValueError):
    pass


@dataclass
class Section:
    name_offset: int
    kind: int
    flags: int
    address: int
    offset: int
    size: int
    link: int
    info: int
    alignment: int
    entry_size: int
    name: str = ""


@dataclass
class Symbol:
    name: str
    binding: int
    kind: int
    section: int
    value: int
    size: int


def c_string(data, start, end=None):
    end = len(data) if end is None else end
    if not 0 <= start < end <= len(data):
        raise AuditError("ELF_STRING_BOUNDS: string offset outside its table")
    stop = data.find(b"\0", start, end)
    if stop < 0:
        raise AuditError("ELF_STRING_NUL: unterminated string")
    try:
        return data[start:stop].decode("ascii")
    except UnicodeDecodeError as exc:
        raise AuditError("ELF_STRING_ENCODING: non-ASCII symbol/section name") from exc


class ELF:
    """Bounds-checked ET_REL reader; no execution, loading, or external tooling."""

    def __init__(self, data):
        self.data = data
        if len(data) < 16 or data[:4] != b"\x7fELF":
            raise AuditError("ELF_MAGIC: missing/truncated ELF identification")
        elf_class, byte_order = data[4], data[5]
        if elf_class not in (1, 2) or byte_order not in (1, 2) or data[6] != 1:
            raise AuditError("ELF_IDENT: unsupported class, endian, or version")
        self.word_size = 4 if elf_class == 1 else 8
        self.endian = "<" if byte_order == 1 else ">"
        header = struct.Struct(self.endian + ("HHIIIIIHHHHHH" if elf_class == 1
                                             else "HHIQQQIHHHHHH"))
        header_size = 16 + header.size
        self.bounds(0, header_size)
        fields = header.unpack_from(data, 16)
        kind, self.machine, version = fields[:3]
        phoff, shoff = fields[4:6]
        ehsize, phentsize, phnum, shentsize, shnum, shstrndx = fields[7:]
        if kind != 1 or version != 1 or ehsize != header_size:
            raise AuditError("ELF_HEADER: expected an ELF v1 relocatable module")
        if (elf_class, self.machine) not in ((1, 40), (2, 183)):
            raise AuditError("ELF_MACHINE: expected ARM32/ELF32 or ARM64/ELF64")
        sh = struct.Struct(self.endian + ("IIIIIIIIII" if elf_class == 1
                                         else "IIQQQQIIQQ"))
        if shentsize != sh.size or shoff < header_size:
            raise AuditError("ELF_SECTION_TABLE: invalid section header size/offset")
        self.bounds(shoff, sh.size)
        first = Section(*sh.unpack_from(data, shoff))
        if first.kind != 0 or any((first.name_offset, first.flags, first.address,
                                   first.offset, first.alignment, first.entry_size)):
            raise AuditError("ELF_SECTION_ZERO: section zero is not SHT_NULL")
        shnum = first.size if shnum == 0 else shnum
        shstrndx = first.link if shstrndx == 0xFFFF else shstrndx
        phnum = first.info if phnum == 0xFFFF else phnum
        if not shnum or not 0 < shstrndx < shnum:
            raise AuditError("ELF_SECTION_TABLE: missing sections/string table")
        self.bounds(shoff, shnum * sh.size)
        self.sections = [Section(*sh.unpack_from(data, shoff + i * sh.size))
                         for i in range(shnum)]
        spans = [(0, header_size, "ELF header"),
                 (shoff, shoff + shnum * sh.size, "section headers")]
        if phnum:
            ph = struct.Struct(self.endian + ("IIIIIIII" if elf_class == 1
                                             else "IIQQQQQQ"))
            if phentsize != ph.size or phoff < header_size:
                raise AuditError("ELF_PROGRAM_TABLE: invalid program header size/offset")
            self.bounds(phoff, phnum * ph.size)
            spans.append((phoff, phoff + phnum * ph.size, "program headers"))
            for i in range(phnum):
                p = ph.unpack_from(data, phoff + i * ph.size)
                offset, size = (p[1], p[4]) if elf_class == 1 else (p[2], p[5])
                self.bounds(offset, size)
        elif phoff or phentsize:
            raise AuditError("ELF_PROGRAM_TABLE: inconsistent empty program table")
        for i, section in enumerate(self.sections[1:], 1):
            if section.alignment and section.alignment & (section.alignment - 1):
                raise AuditError("ELF_SECTION_ALIGNMENT: non-power-of-two alignment")
            if section.link >= shnum:
                raise AuditError("ELF_SECTION_LINK: section link outside table")
            if section.entry_size and section.size % section.entry_size:
                raise AuditError("ELF_SECTION_STRIDE: partial section entry")
            self.bounds(section.offset, 0 if section.kind == 8 else section.size)
            if section.kind not in (0, 8) and section.size:
                spans.append((section.offset, section.offset + section.size, str(i)))
            if section.kind == 3:
                strings = self.payload(i)
                if not strings or strings[0] or strings[-1]:
                    raise AuditError("ELF_STRING_TABLE: missing boundary NUL")
        spans.sort()
        for previous, current in zip(spans, spans[1:]):
            if previous[1] > current[0]:
                raise AuditError("ELF_SECTION_OVERLAP: %s overlaps %s" %
                                 (previous[2], current[2]))
        if self.sections[shstrndx].kind != 3:
            raise AuditError("ELF_SECTION_NAMES: shstrndx is not SHT_STRTAB")
        strings = self.payload(shstrndx)
        for section in self.sections:
            section.name = c_string(strings, section.name_offset)
        symtab_index = self.find(".symtab")
        if symtab_index is None or self.sections[symtab_index].kind != 2:
            raise AuditError("ELF_SYMTAB_MISSING: no loadable module symbol table")
        symtabs = {}
        sym = struct.Struct(self.endian + ("IIIBBH" if elf_class == 1 else "IBBHQQ"))
        for i, section in enumerate(self.sections):
            if section.kind not in (2, 11):
                continue
            if section.flags & 0x800:
                raise AuditError("ELF_SYMBOL_DATA: compressed symbol table")
            if section.entry_size != sym.size or section.size < sym.size:
                raise AuditError("ELF_SYMBOL_STRIDE: invalid symbol table entry size")
            if self.sections[section.link].kind != 3:
                raise AuditError("ELF_SYMBOL_STRINGS: invalid symbol string table link")
            count = section.size // sym.size
            if section.info > count:
                raise AuditError("ELF_SYMBOL_INFO: local symbol boundary outside table")
            strings = self.payload(section.link)
            extended = [j for j, s in enumerate(self.sections) if s.kind == 18 and s.link == i]
            if len(extended) > 1:
                raise AuditError("ELF_SYMBOL_INDEX: duplicate extended-index tables")
            indexes = None
            if extended:
                s = self.sections[extended[0]]
                if s.entry_size != 4 or s.size != count * 4:
                    raise AuditError("ELF_SYMBOL_INDEX: malformed extended-index table")
                indexes = struct.unpack(self.endian + str(count) + "I", self.payload(extended[0]))
            symbols = []
            for j in range(count):
                values = sym.unpack_from(data, section.offset + j * sym.size)
                if j == 0 and any(values):
                    raise AuditError("ELF_SYMBOL_ZERO: symbol zero is not null")
                if elf_class == 1:
                    name, value, size, info, _, index = values
                else:
                    name, info, _, index, value, size = values
                if index == 0xFFFF:
                    if indexes is None:
                        raise AuditError("ELF_SYMBOL_INDEX: missing extended-index table")
                    index = indexes[j]
                if index not in (0, SHN_ABS, 0xFFF2):
                    if index >= shnum:
                        raise AuditError("ELF_SYMBOL_INDEX: symbol section outside table")
                    target = self.sections[index]
                    if value > target.size or size > target.size - value:
                        raise AuditError("ELF_SYMBOL_BOUNDS: symbol exceeds its section")
                symbols.append(Symbol(c_string(strings, name), info >> 4, info & 15,
                                      index, value, size))
            symtabs[i] = symbols
        self.symbols = symtabs[symtab_index]
        self.imports = {s.name for s in self.symbols
                        if s.name and s.section == 0 and s.binding in (1, 2)}
        self.relocations = defaultdict(list)
        for section in self.sections:
            if section.kind not in (4, 9):
                continue
            if section.flags & 0x800:
                raise AuditError("ELF_RELOCATION_DATA: compressed relocation table")
            rela = section.kind == 4
            rel = struct.Struct(self.endian + (("IIi" if rela else "II") if elf_class == 1
                                              else ("QQq" if rela else "QQ")))
            if section.entry_size != rel.size:
                raise AuditError("ELF_RELOCATION_STRIDE: invalid relocation entry size")
            if section.link not in symtabs or not 0 < section.info < shnum:
                raise AuditError("ELF_RELOCATION_LINK: invalid symbol/target section link")
            target = self.sections[section.info]
            for offset in range(section.offset, section.offset + section.size, rel.size):
                r = rel.unpack_from(data, offset)
                location, info = r[:2]
                symbol_index = info >> (8 if elf_class == 1 else 32)
                rel_kind = info & (0xFF if elf_class == 1 else 0xFFFFFFFF)
                if symbol_index >= len(symtabs[section.link]):
                    raise AuditError("ELF_RELOCATION_SYMBOL: symbol index outside table")
                width = 0 if rel_kind == 0 else RELOC_WIDTHS.get((self.machine, rel_kind), 1)
                if location > target.size or width > target.size - location:
                    raise AuditError("ELF_RELOCATION_BOUNDS: relocation outside target")
                if rel_kind and (target.name == "__versions" or "kcrctab" in target.name):
                    self.relocations[section.info].append(
                        (location, rel_kind, symtabs[section.link][symbol_index], r[2] if rela else None))

    def bounds(self, offset, size):
        if offset < 0 or size < 0 or offset > len(self.data) or size > len(self.data) - offset:
            raise AuditError("ELF_BOUNDS: file range outside ELF")

    def find(self, name):
        indexes = [i for i, s in enumerate(self.sections) if s.name == name]
        if len(indexes) > 1:
            raise AuditError("ELF_DUPLICATE_SECTION: " + name)
        return indexes[0] if indexes else None

    def payload(self, index):
        section = self.sections[index]
        if section.kind in (0, 8) or section.flags & 0x800:
            raise AuditError("ELF_SECTION_DATA: absent/compressed section data")
        self.bounds(section.offset, section.size)
        return self.data[section.offset:section.offset + section.size]

    def constant(self, index, offset, width):
        section = self.sections[index]
        if section.kind != 1 or offset < 0 or offset + width > section.size:
            raise AuditError("CRC_FIELD_BOUNDS: invalid CRC section/field")
        data = self.payload(index)
        value = int.from_bytes(data[offset:offset + width],
                               "little" if self.endian == "<" else "big")
        relevant = []
        for rel in self.relocations[index]:
            location, kind, _, _ = rel
            rel_width = ABS_WIDTHS.get((self.machine, kind))
            if rel_width is None:
                raise AuditError("CRC_RELOCATION_UNSUPPORTED: non-absolute CRC relocation")
            if location < offset + width and offset < location + rel_width:
                relevant.append(rel)
        if relevant:
            if len(relevant) != 1 or relevant[0][0] != offset:
                raise AuditError("CRC_RELOCATION_OVERLAP: overlapping CRC relocations")
            _, kind, symbol, addend = relevant[0]
            # LLVM can fold an absolute symbol to STN_UNDEF plus a constant addend.
            null_symbol = symbol == Symbol("", 0, 0, 0, 0, 0)
            if ABS_WIDTHS[(self.machine, kind)] != width or not (symbol.section == SHN_ABS or null_symbol):
                raise AuditError("CRC_RELOCATION_UNSUPPORTED: CRC needs a runtime section address")
            value = (symbol.value + (value if addend is None else addend)) & ((1 << (8 * width)) - 1)
        if value > 0xFFFFFFFF:
            raise AuditError("CRC_WIDTH: modversion CRC is not a uint32")
        return value

    def versions(self, modversions):
        index = self.find("__versions")
        if index is None:
            modinfo = self.find(".modinfo")
            if modversions or modinfo is None:
                raise AuditError("VERSIONS_MISSING: no __versions; not proven non-modversions")
            if self.sections[modinfo].kind != 1:
                raise AuditError("MODINFO_DATA: module metadata is not SHT_PROGBITS")
            data = self.payload(modinfo)
            if not data or data[-1]:
                raise AuditError("MODINFO_NUL: unterminated module metadata")
            try:
                items = data.decode("ascii").split("\0")
            except UnicodeDecodeError as exc:
                raise AuditError("MODINFO_ENCODING: non-ASCII non-modversions evidence") from exc
            vermagic = [item[9:] for item in items if item.startswith("vermagic=")]
            if len(vermagic) != 1 or not vermagic[0].strip() or "modversions" in vermagic[0].split():
                raise AuditError("VERSIONS_MISSING: vermagic does not prove non-modversions")
            return {}
        if not modversions:
            raise AuditError("CONFIG_MODVERSIONS_CONFLICT: versioned vendor module, unversioned kernel")
        section = self.sections[index]
        if section.kind != 1 or not section.size or section.size % 64 or section.entry_size not in (0, 64):
            raise AuditError("VERSIONS_STRIDE: expected nonempty 64-byte modversion records")
        data = self.payload(index)
        for location, kind, _, _ in self.relocations[index]:
            if location % 64 or ABS_WIDTHS.get((self.machine, kind)) != self.word_size:
                raise AuditError("VERSIONS_RELOCATION: relocation is not a whole CRC constant")
        result = {}
        for offset in range(0, len(data), 64):
            name = c_string(data, offset + self.word_size, offset + 64)
            if not NAME.fullmatch(name):
                raise AuditError("VERSIONS_NAME: invalid/empty modversion symbol name")
            if name in result:
                raise AuditError("VERSIONS_DUPLICATE: " + name)
            result[name] = self.constant(index, offset, self.word_size)
        if "module_layout" not in result:
            raise AuditError("MODULE_LAYOUT_MISSING: versioned module has no module_layout CRC")
        return result

    def exports(self):
        by_name = defaultdict(list)
        for symbol in self.symbols:
            by_name[symbol.name].append(symbol)
        result = {}
        for symbol in self.symbols:
            if not symbol.name.startswith("__ksymtab_") or symbol.kind not in (0, 1):
                continue
            if not 0 < symbol.section < len(self.sections):
                raise AuditError("EXPORT_SECTION: export marker has no section")
            section = self.sections[symbol.section]
            if not section.name.startswith(("__ksymtab", "___ksymtab")) or symbol.value >= section.size:
                raise AuditError("EXPORT_SECTION: export marker outside an export table")
            name = symbol.name[len("__ksymtab_"):]
            if not NAME.fullmatch(name) or name in result:
                raise AuditError("EXPORT_NAME: invalid/duplicate export marker " + name)
            crcs = by_name["__crc_" + name]
            if len(crcs) > 1:
                raise AuditError("EXPORT_CRC_DUPLICATE: " + name)
            if not crcs:
                result[name] = (None, "export has no __crc_ constant")
                continue
            crc = crcs[0]
            if crc.section == SHN_ABS:
                if crc.value > 0xFFFFFFFF:
                    raise AuditError("CRC_WIDTH: absolute __crc_ is not a uint32")
                result[name] = (crc.value, "")
                continue
            if not 0 < crc.section < len(self.sections):
                result[name] = (None, "__crc_ is undefined/not section-backed")
                continue
            s = self.sections[crc.section]
            if not s.name.startswith(("__kcrctab", "___kcrctab")):
                result[name] = (None, "__crc_ is not an absolute or direct __kcrctab constant")
                continue
            if s.size % 4 or s.entry_size not in (0, 4) or crc.value % 4 or crc.size not in (0, 4):
                raise AuditError("EXPORT_CRC_STRIDE: malformed uint32 export CRC")
            try:
                result[name] = (self.constant(crc.section, crc.value, 4), "")
            except AuditError as exc:
                if not str(exc).startswith("CRC_RELOCATION_UNSUPPORTED:"):
                    raise
                result[name] = (None, str(exc))
        return result


def fingerprint(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def read_stable(path, limit=None):
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or (limit is not None and before.st_size > limit):
            raise AuditError("INPUT_TYPE_SIZE: expected a regular, bounded input file")
        data = handle.read()
        if len(data) != before.st_size or fingerprint(before) != fingerprint(os.fstat(handle.fileno())):
            raise AuditError("INPUT_CHANGED: file changed while being read")
    return data, fingerprint(before)


def load_symvers(data):
    result = {}
    for number, line in enumerate(data.decode("ascii").splitlines(), 1):
        parts = line.split()
        if not parts:
            continue
        if (len(parts) not in (4, 5) or not re.fullmatch(r"0[xX][0-9a-fA-F]{1,8}", parts[0])
                or not NAME.fullmatch(parts[1]) or parts[3] not in ("EXPORT_SYMBOL", "EXPORT_SYMBOL_GPL")):
            raise AuditError("SYMVERS_FORMAT: malformed CRC/name/provider at line %d" % number)
        name = parts[1]
        if name in result:
            raise AuditError("SYMVERS_DUPLICATE: " + name)
        result[name] = (int(parts[0], 16), parts[2])
    if not result or not any(provider == "vmlinux" for _, provider in result.values()):
        raise AuditError("SYMVERS_EMPTY: no vmlinux CRC exports")
    return result


def config_setting(data, name, required=True):
    lines = data.decode("utf-8").splitlines()
    values = [line[len(name) + 1:] for line in lines if line.startswith(name + "=")]
    values += ["n" for line in lines if line == "# " + name + " is not set"]
    if not values and not required:
        return None
    if len(values) != 1 or values[0] not in ("y", "n"):
        raise AuditError("CONFIG_SETTING: missing/invalid/duplicate " + name)
    return values[0] == "y"


def collect_modules(roots, errors):
    modules, counts, seen = [], [], set()
    for root in roots:
        count = 0
        if root.is_symlink() or not root.is_dir():
            errors.append("MODULE_ROOT: missing/symlink/non-directory " + str(root))
            counts.append(0)
            continue
        for directory, subdirs, files in os.walk(root, followlinks=False,
                                                onerror=lambda exc: errors.append("MODULE_WALK: " + str(exc))):
            subdirs.sort()
            for subdir in subdirs[:]:
                path = Path(directory) / subdir
                if path.is_symlink():
                    errors.append("MODULE_SYMLINK_DIRECTORY: " + str(path))
                    subdirs.remove(subdir)
            for filename in sorted(files):
                if not filename.endswith((".ko", ".ko.gz", ".ko.xz", ".ko.zst")):
                    continue
                path = Path(directory) / filename
                count += 1
                absolute = os.path.abspath(path)
                if absolute in seen:
                    errors.append("MODULE_OVERLAP: input roots repeat " + absolute)
                else:
                    seen.add(absolute)
                    modules.append(path)
        if not count:
            errors.append("EMPTY_MODULE_TREE: " + str(root))
        counts.append(count)
    return sorted(modules), counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symvers", type=Path, default=Path(DEFAULT_SYMVERS))
    parser.add_argument("--config", type=Path, help="default: .config next to --symvers")
    parser.add_argument("--modules", type=Path, action="append", help="module tree (repeatable; replaces both defaults)")
    parser.add_argument("--max-files", type=int, default=10000, help="fail, never truncate, above this module count")
    parser.add_argument("--details", action="store_true", help="list all consuming modules for each mismatch/scope gap")
    args = parser.parse_args(argv)
    config = args.config if args.config is not None else args.symvers.parent / ".config"
    snapshots, errors = {}, []
    try:
        symvers_data, snapshots[args.symvers] = read_stable(args.symvers)
        exports = load_symvers(symvers_data)
        config_data, snapshots[config] = read_stable(config)
        modversions = config_setting(config_data, "CONFIG_MODVERSIONS")
        if not config_setting(config_data, "CONFIG_MODULES"):
            raise AuditError("CONFIG_MODULES: kernel cannot load vendor modules")
        kernel_64bit = config_setting(config_data, "CONFIG_64BIT", required=False)
    except (OSError, ValueError) as exc:
        print("[ERROR] " + str(exc))
        print("[RESULT] FAIL: kernel input could not be audited")
        return 1
    print("[INPUT] symvers=%s sha256=%s exports=%d vmlinux_exports=%d" %
          (args.symvers, hashlib.sha256(symvers_data).hexdigest(), len(exports),
           sum(provider == "vmlinux" for _, provider in exports.values())))
    print("[INPUT] config=%s sha256=%s CONFIG_MODVERSIONS=%s" %
          (config, hashlib.sha256(config_data).hexdigest(), "y" if modversions else "n"))
    roots = args.modules if args.modules is not None else list(map(Path, DEFAULT_MODULE_DIRS))
    modules, root_counts = collect_modules(roots, errors)
    for root, count in zip(roots, root_counts):
        print("[TREE] %s modules=%d" % (root, count))
    if args.max_files <= 0 or len(modules) > args.max_files:
        print("[ERROR] MAX_FILES: discovered=%d limit=%d; no truncated audit" % (len(modules), args.max_files))
        for error in errors:
            print("[ERROR] " + error)
        print("[RESULT] FAIL")
        return 1
    counts, parsed, providers = Counter(), [], defaultdict(list)
    required_unique, version_unique, undefined_unique = set(), set(), set()
    for path in modules:
        try:
            if path.is_symlink():
                raise AuditError("MODULE_SYMLINK: refusing a potentially out-of-tree module")
            data, snapshots[path] = read_stable(path, MAX_MODULE_BYTES)
            counts["read"] += 1
            if path.suffix != ".ko":
                raise AuditError("MODULE_COMPRESSION: decompress explicitly before auditing")
            elf = ELF(data)
            if kernel_64bit is not None and (elf.word_size == 8) != kernel_64bit:
                raise AuditError("MODULE_CLASS: module ELF class disagrees with kernel .config")
            versions = elf.versions(modversions)
            module_exports = elf.exports()
            parsed.append((path, versions, elf.imports))
            counts["parsed"] += 1
            counts["no_modversions"] += not versions
            counts["version_records"] += len(versions)
            counts["module_layout_present"] += "module_layout" in versions
            required_unique.update(versions)
            required_unique.update(elf.imports)
            version_unique.update(versions)
            undefined_unique.update(elf.imports)
            for name, (crc, reason) in module_exports.items():
                providers[name].append((path, crc, reason))
        except (OSError, ValueError) as exc:
            errors.append("%s: %s" % (path, exc))
    mismatches, uncompared, absent = defaultdict(list), defaultdict(list), defaultdict(list)
    compared_unique = {"vmlinux": set(), "modules": set()}
    mismatch_unique = set()
    non_vmlinux_unique, unversioned_unique = set(), set()
    for path, versions, imports in parsed:
        for name in sorted(imports - versions.keys()):
            counts["unversioned_imports"] += 1
            unversioned_unique.add(name)
            if modversions and (name in exports or name in providers):
                counts["known_unversioned_imports"] += 1
                errors.append("VERSIONS_REQUIRED_MISSING: %s symbol=%s" % (path, name))
            elif name not in exports and name not in providers:
                absent[name].append(path)
                counts["absent_unversioned_imports"] += 1
        for name, expected in sorted(versions.items()):
            kernel = exports.get(name)
            if kernel is not None and kernel[1] == "vmlinux":
                actual, provider, scope = kernel[0], "vmlinux", "vmlinux"
            else:
                counts["non_vmlinux_records"] += 1
                non_vmlinux_unique.add(name)
                candidates = [candidate for candidate in providers.get(name, []) if candidate[0] != path]
                if not candidates:
                    if kernel is None:
                        absent[name].append(path)
                        counts["absent_version_records"] += 1
                    else:
                        uncompared[(name, "symvers provider=%s; provider .ko not supplied" % kernel[1])].append(path)
                    continue
                values = {crc for _, crc, _ in candidates}
                if None in values:
                    reason = "; ".join("%s: %s" % (p, why) for p, crc, why in candidates if crc is None)
                    uncompared[(name, reason)].append(path)
                    continue
                if len(values) != 1:
                    reason = "ambiguous provider CRCs: " + "; ".join("%s=0x%08x" % (p, crc) for p, crc, _ in candidates)
                    uncompared[(name, reason)].append(path)
                    errors.append("PROVIDER_CRC_AMBIGUOUS: %s symbol=%s" % (path, name))
                    continue
                actual, provider, scope = values.pop(), "stock_modules", "modules"
            counts[scope + "_comparisons"] += 1
            compared_unique[scope].add(name)
            match = expected == actual
            counts[scope + ("_matches" if match else "_mismatches")] += 1
            if name == "module_layout":
                counts["module_layout_comparisons"] += 1
                counts["module_layout_matches" if match else "module_layout_mismatches"] += 1
            if not match:
                mismatches[(name, expected, actual, provider)].append(path)
                mismatch_unique.add(name)
    if modversions and not counts["vmlinux_comparisons"] and not counts["modules_comparisons"]:
        errors.append("NO_CRC_COMPARISONS: no required CRC was actually checked")
    for path, before in snapshots.items():
        try:
            if fingerprint(path.stat()) != before:
                errors.append("INPUT_CHANGED: " + str(path))
        except OSError as exc:
            errors.append("INPUT_CHANGED: %s: %s" % (path, exc))
    for (name, expected, actual, provider), consumers in sorted(mismatches.items()):
        print("[MISMATCH] symbol=%s vendor=0x%08x actual=0x%08x provider=%s modules=%d" %
              (name, expected, actual, provider, len(consumers)))
        if args.details:
            for path in consumers:
                print("  " + str(path))
    for (name, reason), consumers in sorted(uncompared.items()):
        print("[PROVIDER_UNCOMPARED] symbol=%s records=%d reason=%s" % (name, len(consumers), reason))
        if args.details:
            for path in consumers:
                print("  " + str(path))
    for name, consumers in sorted(absent.items()):
        print("[ABSENT_EXPORT] symbol=%s requirements=%d; NOT compared, defer to symbol-resolution audit" %
              (name, len(consumers)))
        if args.details:
            for path in consumers:
                print("  " + str(path))
    for error in errors:
        print("[ERROR] " + error)
    print("[SUMMARY] modules discovered=%d read=%d parsed=%d failed=%d legitimate_no_modversions=%d" %
          (len(modules), counts["read"], counts["parsed"], len(modules) - counts["parsed"], counts["no_modversions"]))
    print("[SUMMARY] required_unique=%d version_unique=%d undefined_unique=%d version_records=%d" %
          (len(required_unique), len(version_unique), len(undefined_unique), counts["version_records"]))
    for scope in ("vmlinux", "modules"):
        print("[SUMMARY] %s comparisons=%d unique=%d matches=%d mismatches=%d" %
              (scope, counts[scope + "_comparisons"], len(compared_unique[scope]),
               counts[scope + "_matches"], counts[scope + "_mismatches"]))
    print("[SUMMARY] mismatch_symbols=%d non_vmlinux_records=%d non_vmlinux_unique=%d" %
          (len(mismatch_unique), counts["non_vmlinux_records"], len(non_vmlinux_unique)))
    print("[SUMMARY] provider_uncompared_records=%d provider_uncompared_unique=%d absent_version_records=%d absent_unique=%d" %
          (sum(map(len, uncompared.values())), len({name for name, _ in uncompared}),
           counts["absent_version_records"], len(absent)))
    print("[SUMMARY] unversioned_imports=%d unique=%d known_provider_missing_crc=%d absent_unversioned_imports=%d" %
          (counts["unversioned_imports"], len(unversioned_unique), counts["known_unversioned_imports"],
           counts["absent_unversioned_imports"]))
    layout = exports.get("module_layout")
    layout_crc = "0x%08x" % layout[0] if layout is not None and layout[1] == "vmlinux" else "ABSENT_FROM_VMLINUX"
    print("[SUMMARY] module_layout kernel_crc=%s present=%d comparisons=%d matches=%d mismatches=%d" %
          (layout_crc, counts["module_layout_present"], counts["module_layout_comparisons"],
           counts["module_layout_matches"], counts["module_layout_mismatches"]))
    if errors or mismatches:
        print("[RESULT] FAIL: CRC mismatch records=%d symbols=%d input/coverage_errors=%d; no waivers" %
              (sum(map(len, mismatches.values())), len(mismatch_unique), len(errors)))
        return 1
    if not modversions:
        print("[RESULT] PASS: CRC check NOT APPLICABLE; kernel and every parsed module explicitly lack modversions")
    else:
        print("[RESULT] PASS: all compared CRCs match; absent/uncompared providers are NOT certified")
    print("[SCOPE] Offline CRC checks only; run symbol/config/signature audits and hardware validation separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
