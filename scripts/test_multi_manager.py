#!/usr/bin/env python3
"""Compile real KernelSU functions in transient, sanitized host test harnesses.

Run inside native WSL. Only fixtures under /root are written; kernel sources
are read, snapshotted, and extracted without changing their implementation.
Linux locking, RCU, credentials, user copies, and file I/O are host stubs, not
an Android runtime or kernel boot test.
"""

import argparse
import hashlib
import io
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile


DEFAULT_KERNEL = "/root/Aphelion-Kernel/KernelSU"
DEFAULT_CLANG = "/root/toolchains/clang-r487747c/bin/clang"
OPTIONS = None
CERTIFICATES = (
    ("BAKASU", 0, 0x377, "d3469712b6214462764a1d8d3e5cbe1d6819a0b629791b9f4101867821f1df64"),
    ("OFFICIAL", 1, 0x33B, "c371061b19d8c7d7d6133c6a9bafe198fa944e50c1b31c9d8daa8d7f1fc2d2d6"),
    ("KSUNEXT", 2, 0x3E6, "79e590113c4c4c0c222978e413a5faa801666957b1212a328e46c00c69821bf7"),
    ("FINASU", 3, 0x2CC, "2d89b50aaf1db013c2b6738f973f48b62ea21a3a8d7216bfec3521065d448458"),
    ("SUKISU", 4, 0x35C, "947ae944f3de4ed4c21a7e4f7953ecf351bfa2b36239da37a34111ad29993eef"),
    ("MILKSU", 5, 0x3CB, "86330097ea9dd3046a802d6ba1d9fd897dd5df87a5930b674d819179550a0d0f"),
    ("WILDKSU", 6, 0x381, "52d52c546f75448464566da175d72b2c147bc5cb55a10886941da2a20ca2efac"),
    ("KSUNEXT_ALT", 7, 0x135, "a6ed6cedaaffa928d69a92a2df5cf2891ffb1f588d523cf5978706d75c918a52"),
)
SOURCES = (
    "kernel/manager/manager_sign.h",
    "kernel/manager/manager_identity.h",
    "kernel/manager/throne_tracker.h",
    "kernel/manager/manager.c",
    "kernel/manager/apk_sign.c",
    "kernel/manager/apk_sign.h",
    "kernel/supercall/dispatch.c",
    "kernel/supercall/perm.c",
    "kernel/supercall/supercall.h",
    "kernel/policy/feature.c",
    "kernel/policy/feature.h",
    "kernel/feature/finasu_net_isolate.h",
    "kernel/feature/finasu_uts_view.h",
    "kernel/feature/finasu_dynamic_manager.h",
    "uapi/app_profile.h",
    "uapi/feature.h",
    "uapi/selinux.h",
    "uapi/supercall.h",
    "../security/selinux/avc.c",
    "../security/selinux/include/avc.h",
    "../include/linux/lsm_audit.h",
)


def mask_c(text):
    """Hide comments and literals while retaining offsets and line numbers."""
    pattern = r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m[0]), text, flags=re.S)


def block_end(masked, opening):
    depth = 1
    for index in range(opening + 1, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if not depth:
                return index + 1
    raise ValueError("Unterminated C definition")


def extract_function(text, name):
    masked = mask_c(text)
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\(", masked):
        opening = masked.index("(", match.start())
        depth = 1
        position = opening + 1
        while position < len(masked) and depth:
            depth += (masked[position] == "(") - (masked[position] == ")")
            position += 1
        while position < len(masked) and masked[position].isspace():
            position += 1
        if position < len(masked) and masked[position] == "{":
            start = text.rfind("\n", 0, match.start()) + 1
            return start, text[start:block_end(masked, position)]
    raise ValueError(f"Missing real function: {name}")


def extract_block(text, expression):
    masked = mask_c(text)
    match = re.search(expression, masked, re.M)
    if not match:
        raise ValueError(f"Missing real definition: {expression}")
    opening = masked.index("{", match.start())
    end = block_end(masked, opening)
    semicolon = masked.find(";", end)
    if semicolon < 0 or re.search(r"[{}]", masked[end:semicolon]):
        raise ValueError("C definition does not end in a semicolon")
    return match.start(), text[match.start():semicolon + 1]


def source_fragment(path, text, start=0):
    return f'\n#line {text.count(chr(10), 0, start) + 1} "{path}"\n'


def without_includes(text):
    return re.sub(r"^[ \t]*#include[^\n]*", "", text, flags=re.M)


HOST_STUBS = r"""
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <linux/ioctl.h>
#include <linux/types.h>
typedef __u8 u8;
typedef __u16 u16;
typedef __u32 u32;
typedef __u64 u64;
#define __user
#define __init
#define __exit
#define __randomize_layout
#define noinline __attribute__((noinline))
#define IS_BUILTIN(option) (option)
#define WARN_ON(condition) (condition)
#define GFP_KERNEL 0
#define GFP_ATOMIC 0
#define KERNEL_VERSION(a, b, c) (((a) << 16) | ((b) << 8) | (c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6, 1, 0)
#define KERNEL_SU_VERSION 424242
#define KSU_VERSION_FULL "aphelion-host-regression-version-string-long-enough-to-exercise-32-and-64-byte-truncation"
#define KSYM_NAME_LEN 128
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define unlikely(x) (x)
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_debug(...) ((void)0)
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x, v) ((*(volatile __typeof__(x) *)&(x)) = (v))
#define min_t(type, a, b) ({ type _a = (a), _b = (b); _a < _b ? _a : _b; })
#define le16_to_cpu(x) (x)
#define le32_to_cpu(x) (x)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { \
    fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
#define CHECK_EQ(a, b) do { long long _a = (a), _b = (b); checks++; if (_a != _b) { \
    fprintf(stderr, "%s:%d: %s = %lld, expected %s = %lld\n", \
            __FILE__, __LINE__, #a, _a, #b, _b); exit(1); } } while (0)

/* Fault injection is restricted to the kernel-facing allocator/copy stubs. */
static int alloc_fail_after = -1;
static bool from_fault, to_fault, get_fault, put_fault, string_fault;
static size_t last_copy_size;
static void *host_alloc(size_t size, bool zero)
{
    if (alloc_fail_after == 0) return NULL;
    if (alloc_fail_after > 0) alloc_fail_after--;
    if (!size) return NULL;
    return zero ? calloc(1, size) : malloc(size);
}
#define kmalloc(n, g) host_alloc((n), false)
#define kzalloc(n, g) host_alloc((n), true)
#define kcalloc(n, s, g) host_alloc((size_t)(n) * (s), true)
#define kfree(p) free(p)
#define vzalloc(n) host_alloc((n), true)
#define vfree(p) free(p)
static size_t copy_from_user(void *to, const void *from, size_t size)
{
    if (from_fault || !from) return size;
    memcpy(to, from, size);
    return 0;
}
static size_t copy_to_user(void *to, const void *from, size_t size)
{
    last_copy_size = size;
    if (to_fault || !to) return size;
    memcpy(to, from, size);
    return 0;
}
#define get_user(value, ptr) ({ int _ret = 0; \
    if (get_fault || !(ptr)) _ret = -EFAULT; else (value) = *(ptr); _ret; })
#define put_user(value, ptr) ({ int _ret = 0; \
    if (put_fault || !(ptr)) _ret = -EFAULT; else *(ptr) = (value); _ret; })
static char *strndup_user(const char *source, size_t max)
{
    if (string_fault || !source) return ERR_PTR(-EFAULT);
    size_t size = strnlen(source, max);
    if (size == max) return ERR_PTR(-EINVAL);
    char *result = kmalloc(size + 1, GFP_KERNEL);
    if (!result) return ERR_PTR(-ENOMEM);
    memcpy(result, source, size + 1);
    return result;
}
static ssize_t strscpy(char *to, const char *from, size_t size)
{
    if (!size) return -E2BIG;
    size_t length = strlen(from), copied = length < size ? length : size - 1;
    memcpy(to, from, copied);
    to[copied] = '\0';
    return length < size ? (ssize_t)length : -E2BIG;
}
static char *kasprintf(int gfp, const char *format, ...)
{
    (void)gfp;
    if (alloc_fail_after == 0) return NULL;
    if (alloc_fail_after > 0) alloc_fail_after--;
    va_list args;
    char *result = NULL;
    va_start(args, format);
    int size = vasprintf(&result, format, args);
    va_end(args);
    return size < 0 ? NULL : result;
}

struct list_head { struct list_head *next, *prev; };
struct rcu_head { int unused; };
#define LIST_HEAD_INIT(name) { &(name), &(name) }
#define LIST_HEAD(name) struct list_head name = LIST_HEAD_INIT(name)
#define container_of(p, type, member) ((type *)((char *)(p) - offsetof(type, member)))
#define list_entry(p, type, member) container_of(p, type, member)
#define list_first_entry(head, type, member) list_entry((head)->next, type, member)
#define list_for_each_entry(pos, head, member) \
    for (struct list_head *_cursor = (head)->next; \
         _cursor != (head) && ((pos) = list_entry(_cursor, __typeof__(*(pos)), member), 1); \
         _cursor = _cursor->next)
#define list_for_each_entry_rcu list_for_each_entry
#define list_for_each_entry_safe(pos, tmp, head, member) \
    for (struct list_head *_cursor = (head)->next, *_next = NULL; \
         _cursor != (head) && (_next = _cursor->next, \
             (pos) = list_entry(_cursor, __typeof__(*(pos)), member), \
             (tmp) = _next == (head) ? NULL : list_entry(_next, __typeof__(*(tmp)), member), 1); \
         _cursor = _next)
static bool list_empty(const struct list_head *head) { return head->next == head; }
static void list_add_tail_rcu(struct list_head *node, struct list_head *head)
{
    node->prev = head->prev; node->next = head;
    head->prev->next = node; head->prev = node;
}
static void list_del_rcu(struct list_head *node)
{
    node->prev->next = node->next; node->next->prev = node->prev;
}
#define DEFINE_SPINLOCK(name) int name
#define DEFINE_MUTEX(name) int name
static void host_lock(int *lock) { CHECK_EQ(*lock, 0); *lock = 1; }
static void host_unlock(int *lock) { CHECK_EQ(*lock, 1); *lock = 0; }
#define spin_lock(p) host_lock(p)
#define spin_unlock(p) host_unlock(p)
#define mutex_lock(p) host_lock(p)
#define mutex_unlock(p) host_unlock(p)
static unsigned rcu_depth, deferred_count;
static void *deferred[128];
static u32 remove_at_unlock;
void ksu_unregister_manager(u32 uid);
static void rcu_read_lock(void) { rcu_depth++; }
static void host_rcu_free(void *pointer)
{
    if (!rcu_depth) { free(pointer); return; }
    CHECK(deferred_count < ARRAY_SIZE(deferred));
    deferred[deferred_count++] = pointer;
}
#define kfree_rcu(pointer, member) host_rcu_free(pointer)
static void rcu_read_unlock(void)
{
    CHECK(rcu_depth > 0);
    if (--rcu_depth) return;
    /* Free precisely at unlock to expose any subsequent node dereference. */
    if (remove_at_unlock) {
        u32 uid = remove_at_unlock;
        remove_at_unlock = 0;
        ksu_unregister_manager(uid);
    }
    while (deferred_count) free(deferred[--deferred_count]);
}
#define DECLARE_BITMAP(name, bits) unsigned long name[((bits) + 63) / 64]
static bool test_bit(unsigned bit, const unsigned long *map)
{ return !!(map[bit / 64] & (1UL << (bit % 64))); }
static void set_bit(unsigned bit, unsigned long *map) { map[bit / 64] |= 1UL << (bit % 64); }
static void clear_bit(unsigned bit, unsigned long *map) { map[bit / 64] &= ~(1UL << (bit % 64)); }
#define for_each_set_bit(bit, map, bits) \
    for ((bit) = 0; (bit) < (bits); (bit)++) if (test_bit((bit), (map)))
struct kernel_param { int unused; };
struct kernel_param_ops { unsigned flags; int (*set)(const char *, const struct kernel_param *); };
#define KERNEL_PARAM_OPS_FL_NOARG 1
#define module_param_cb(...)
static int kstrtou64(const char *text, unsigned base, u64 *out)
{
    char *end;
    errno = 0;
    if (!*text || *text == '-') return -EINVAL;
    *out = strtoull(text, &end, base);
    return errno || *end ? -EINVAL : 0;
}
static int kstrtou32(const char *text, unsigned base, u32 *out)
{
    u64 value;
    int result = kstrtou64(text, base, &value);
    if (result || value > UINT32_MAX) return -EINVAL;
    *out = value;
    return 0;
}
struct static_key_false { bool enabled; };
#define DEFINE_STATIC_KEY_FALSE(name) struct static_key_false name = { false }
struct static_key_false susfs_is_avc_log_spoofing_enabled;
u32 susfs_ksu_sid = 111, susfs_priv_app_sid = 222;
static bool static_key_enabled(const struct static_key_false *key) { return key->enabled; }
static void static_branch_enable(struct static_key_false *key) { key->enabled = true; }
static void static_branch_disable(struct static_key_false *key) { key->enabled = false; }
#define static_branch_likely(key) static_key_enabled(key)
#define static_branch_unlikely(key) static_key_enabled(key)

struct inode { loff_t size; };
struct file { struct inode inode; unsigned char *data; size_t size; int refs; bool su_session; };
struct mm_struct { struct file *exe; };
struct task_struct { struct mm_struct *mm; };
static struct task_struct host_task;
#define current (&host_task)
static u32 host_uid;
#define current_uid() (host_uid)
#define ksu_get_uid_t(uid) (uid)
static bool ksu_late_loaded, ksu_bundled, preinit_enabled;
static bool ksu_preinit_enabled_param(void) { return preinit_enabled; }
static bool ksu_is_allow_uid_for_current(u32 uid) { (void)uid; return false; }
static bool ksu_is_su_session_fd(const struct file *file) { return file && file->su_session; }
static unsigned exe_gets, exe_puts, daemon_calls;
static int daemon_signature = -ENODATA;
static u32 daemon_uapi_version;
static struct file *daemon_examined;
static struct file *get_mm_exe_file(struct mm_struct *mm)
{
    exe_gets++;
    if (mm->exe) mm->exe->refs++;
    return mm->exe;
}
static void fput(struct file *file) { CHECK(file->refs > 1); file->refs--; exe_puts++; }
int ksu_get_daemon_info(struct file *executable, u32 *uapi_version)
{
    daemon_calls++; daemon_examined = executable;
    if (uapi_version) *uapi_version = daemon_uapi_version;
    return daemon_signature;
}
int ksu_get_daemon_signature_index(struct file *executable)
{ return ksu_get_daemon_info(executable, NULL); }
/* Census/VFS scheduling is a boundary, not simulated kernel implementation. */
static unsigned census_boundary_calls;
void track_throne(unsigned int flags)
{ (void)flags; census_boundary_calls++; }
static unsigned resolver_calls;
static int resolver_error;
static int ksu_lookup_kernel_symbols(const char *const *names, unsigned long *addrs, u32 count)
{
    resolver_calls++;
    if (resolver_error) return resolver_error;
    int found = 0;
    for (u32 i = 0; i < count; i++) {
        addrs[i] = names[i] && !strcmp(names[i], "known") ? 0xffff000012340000UL : 0;
        if (names[i] && !strcmp(names[i], "second")) addrs[i] = 0xffff000023450000UL;
        found += !!addrs[i];
    }
    return found;
}

/* Fake kernel I/O reads immutable, Python-generated fixture bytes in memory. */
static struct file *apk_file, *extracted_file;
static bool short_read;
static unsigned open_calls;
static struct inode *file_inode(struct file *file) { return &file->inode; }
static loff_t i_size_read(const struct inode *inode) { return inode->size; }
static ssize_t ksu_kernel_read_compat(struct file *file, void *to, size_t count, loff_t *position)
{
    if (*position < 0 || (u64)*position > file->size) return -EINVAL;
    size_t available = file->size - (size_t)*position;
    if (count > available) count = available;
    if (short_read && count) count--;
    if (count) memcpy(to, file->data + *position, count);
    *position += count;
    return count;
}
static struct file *ksu_filp_open_nonotify(const char *path, int flags)
{
    open_calls++;
    struct file *file = NULL;
    if (!strcmp(path, "/data/app/test/base.apk")) {
        CHECK(flags & O_NOFOLLOW); file = apk_file;
    } else if (!strcmp(path, "/data/app/test/lib/arm64/libksud.so")) file = extracted_file;
    if (!file) return ERR_PTR(-ENOENT);
    file->refs++;
    return file;
}
static int filp_close(struct file *file, void *unused)
{ (void)unused; CHECK(file->refs > 1); file->refs--; return 0; }
"""


ZLIB_SHIM = r"""
#line 1 "host-system-zlib-shim.c"
/* Only the Linux zlib API boundary is adapted; the kernel stream loop is real. */
#define z_stream host_z_stream
#define z_streamp host_z_streamp
#include <zlib.h>
#undef z_stream
#undef z_streamp
typedef struct {
    host_z_stream system;
    unsigned char *next_in, *next_out;
    unsigned int avail_in, avail_out;
    unsigned long total_in, total_out;
    void *workspace;
} z_stream;
static bool inflate_init_fault;
static size_t zlib_inflate_workspacesize(void) { return 1; }
static int zlib_inflateInit2(z_stream *stream, int bits)
{
    CHECK(stream->workspace);
    if (inflate_init_fault) return Z_MEM_ERROR;
    return inflateInit2_(&stream->system, bits, ZLIB_VERSION, sizeof(host_z_stream));
}
static int zlib_inflate(z_stream *stream, int flush)
{
    stream->system.next_in = stream->next_in;
    stream->system.avail_in = stream->avail_in;
    stream->system.next_out = stream->next_out;
    stream->system.avail_out = stream->avail_out;
    int result = inflate(&stream->system, flush);
    stream->next_in = stream->system.next_in;
    stream->avail_in = stream->system.avail_in;
    stream->next_out = stream->system.next_out;
    stream->avail_out = stream->system.avail_out;
    stream->total_in = stream->system.total_in;
    stream->total_out = stream->system.total_out;
    return result;
}
static int zlib_inflateEnd(z_stream *stream) { return inflateEnd(&stream->system); }
"""


DYNAMIC_BOUNDARY_SPIES = r"""
#line 1 "host-dynamic-backend-boundary-spies.c"
/* Programmed backend responses only: no grant, certificate or persistence logic. */
static u32 backend_denied_appid = UINT32_MAX;
static u32 backend_denied_full_uid = UINT32_MAX;
static u8 backend_denied_signature = 252;
static unsigned backend_authorization_calls, backend_version_calls;
static u32 backend_last_appid, backend_last_version_uid;
static u8 backend_last_signature;
static bool backend_version_present;
static u32 backend_version_value = 731004;
bool ksu_finasu_dynamic_manager_uid_allowed(u32 uid, u8 signature_index)
{
    backend_authorization_calls++;
    backend_last_appid = uid; backend_last_signature = signature_index;
    return (uid != backend_denied_appid && uid != backend_denied_full_uid) ||
           signature_index != backend_denied_signature;
}
bool ksu_finasu_dynamic_manager_version_code(u32 uid, u32 *out)
{
    backend_version_calls++; backend_last_version_uid = uid;
    if (!backend_version_present) return false;
    CHECK(out); *out = backend_version_value; return true;
}
"""


AUDIT_STUBS = r"""
#line 1 "host-audit-stubs.c"
struct selinux_state { u64 marker; };
struct audit_buffer { int unused; };
static const int secclass_map[4] = {0};
static struct selinux_audit_data observed_audit;
static unsigned observed_audit_calls;
static char observed_audit_type;
static int observed_auxiliary;
static void avc_audit_pre_callback(struct audit_buffer *buffer, void *data)
{ (void)buffer; (void)data; }
static void avc_audit_post_callback(struct audit_buffer *buffer, void *data)
{ (void)buffer; (void)data; }
static void common_lsm_audit(struct common_audit_data *data,
        void (*pre)(struct audit_buffer *, void *), void (*post)(struct audit_buffer *, void *))
{
    CHECK(pre == avc_audit_pre_callback); CHECK(post == avc_audit_post_callback);
    CHECK(data->selinux_audit_data);
    /* Copy synchronously while slow_avc_audit's actual stack metadata is live. */
    observed_audit = *data->selinux_audit_data;
    observed_audit_type = data->type;
    observed_auxiliary = data->type == LSM_AUDIT_DATA_NONE ? 0 : data->u.ipc_id;
    observed_audit_calls++;
}
"""


HOST_CASES = r"""
#line 1 "host-regression-cases.c"
static void reset_registry(void)
{
    ksu_unregister_all_manager();
    host_uid = 0; current->mm = NULL; remove_at_unlock = 0;
    alloc_fail_after = -1;
}
static void case_lifecycle(void)
{
    CHECK_EQ(KSU_INVALID_APPID, UINT32_MAX);
    CHECK_EQ(ksu_last_manager_appid, KSU_INVALID_APPID);
    CHECK(!ksu_has_manager());
    CHECK_EQ(ksu_get_manager_appid(), KSU_INVALID_APPID);
    struct ksu_get_manager_appid_cmd reply;
    CHECK_EQ(do_get_manager_appid(&reply), 0); CHECK_EQ(reply.appid, UINT32_MAX);
    for (u8 i = 0; i < 8; i++) {
        ksu_register_manager(10000 + i, i);
        CHECK_EQ(ksu_get_manager_signature_index_by_appid(10000 + i), i);
    }
    CHECK_EQ(ksu_get_manager_appid(), 10000);
    ksu_mark_manager(10003); CHECK_EQ(ksu_get_manager_appid(), 10003);
    ksu_mark_manager(19000); CHECK_EQ(ksu_get_manager_appid(), 10003);
    ksu_mark_manager(42 * PER_USER_RANGE + 10007);
    CHECK_EQ(ksu_get_manager_appid(), 10007);
    ksu_register_manager(42 * PER_USER_RANGE + 10007, KSU_SIG_OFFICIAL);
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(10007), KSU_SIG_KSUNEXT_ALT);
    CHECK(ksu_is_manager_uid(19 * PER_USER_RANGE + 10007));
    host_uid = 19 * PER_USER_RANGE + 10007; CHECK(is_manager()); host_uid = 0;
    ksu_unregister_manager(10002); CHECK_EQ(ksu_get_manager_appid(), 10007);
    ksu_unregister_manager(42 * PER_USER_RANGE + 10007);
    CHECK_EQ(ksu_get_manager_appid(), 10000);
    ksu_register_manager(11007, KSU_SIG_KSUNEXT_ALT);
    CHECK(!ksu_is_manager_uid(10007)); CHECK(ksu_is_manager_uid(11007));
    ksu_register_manager(20003, KSU_SIG_FINASU); ksu_mark_manager(20003);
    for (u8 i = 0; i < 4; i++) ksu_register_manager(21000 + i, 252 + i);
    ksu_unregister_manager_by_signature_index(KSU_SIG_FINASU);
    CHECK(!ksu_is_manager_uid(10003)); CHECK(!ksu_is_manager_uid(20003));
    CHECK_EQ(ksu_get_manager_appid(), 10000);
    for (u8 i = 0; i < 4; i++)
        CHECK_EQ(ksu_get_manager_signature_index_by_appid(21000 + i), 252 + i);
    CHECK_EQ(KSU_SIGNATURE_INDEX_FINASU_DYNAMIC_MANAGER, 252);
    CHECK_EQ(KSU_SIGNATURE_INDEX_KSU_TOOLKIT, 253);
    CHECK_EQ(KSU_SIGNATURE_INDEX_KSU_DEBUG, 254);
    CHECK_EQ(KSU_SIGNATURE_INDEX_DYNAMIC_MANAGER, 255);
    ksu_unregister_all_manager(); CHECK_EQ(ksu_last_manager_appid, KSU_INVALID_APPID);
    CHECK(!ksu_has_manager());
    ksu_register_manager(23001, KSU_SIG_MILKSU); CHECK_EQ(ksu_get_manager_appid(), 23001);
    ksu_last_manager_appid = 19999;
    CHECK_EQ(ksu_get_manager_appid(), KSU_INVALID_APPID);
    ksu_unregister_manager(19998); CHECK_EQ(ksu_get_manager_appid(), 23001);
    alloc_fail_after = 0; ksu_register_manager(23002, KSU_SIG_OFFICIAL);
    CHECK(!ksu_is_manager_uid(23002)); alloc_fail_after = -1;
    ksu_unregister_manager(23001); CHECK_EQ(ksu_get_manager_appid(), KSU_INVALID_APPID);
}
static void case_appid_width(void)
{
    CHECK_EQ(sizeof(ksu_last_manager_appid), sizeof(u32));
    CHECK_EQ(sizeof(ksu_get_manager_appid()), sizeof(u32));
    CHECK_EQ(sizeof(((struct ksu_manager_node *)0)->appid), sizeof(u32));
    ksu_register_manager(10000, KSU_SIG_BAKASU);
    CHECK(ksu_is_manager_uid(10000)); CHECK(!ksu_is_manager_uid(75536));
    CHECK(!ksu_is_manager_uid(7 * PER_USER_RANGE + 75536));
    CHECK(!ksu_is_manager_appid(75536));
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(75536), -ENODATA);
    host_uid = 75536; CHECK(!is_manager()); CHECK_EQ(get_caller_signature_index(), -ENODATA);
    ksu_unregister_manager(75536); CHECK(ksu_is_manager_uid(10000));
    ksu_register_manager(75536, KSU_SIG_MILKSU);
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(10000), KSU_SIG_BAKASU);
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(75536), KSU_SIG_MILKSU);
    CHECK(ksu_is_manager_appid(75536)); CHECK(ksu_is_manager_uid(75536));
    CHECK(ksu_is_manager_uid(42 * PER_USER_RANGE + 75536));
    host_uid = 42 * PER_USER_RANGE + 75536; CHECK(is_manager());
    CHECK_EQ(get_caller_signature_index(), KSU_SIG_MILKSU);
    ksu_mark_manager(host_uid); CHECK_EQ(ksu_last_manager_appid, 75536);
    CHECK_EQ(ksu_get_manager_appid(), 75536);
    struct ksu_get_manager_appid_cmd selected;
    CHECK_EQ(do_get_manager_appid(&selected), 0); CHECK_EQ(selected.appid, 75536);
    unsigned char bytes[32] = {0}; struct ksu_get_managers_cmd *list = (void *)bytes;
    list->count = 2; CHECK_EQ(do_get_managers(list), 0);
    CHECK_EQ(list->count, 2); CHECK_EQ(list->total_count, 2);
    CHECK_EQ(list->managers[0].uid, 10000); CHECK_EQ(list->managers[0].signature_index, 0);
    CHECK_EQ(list->managers[1].uid, 75536); CHECK_EQ(list->managers[1].signature_index, KSU_SIG_MILKSU);
    ksu_unregister_manager(10000); CHECK_EQ(ksu_get_manager_appid(), 75536);
    CHECK(!ksu_is_manager_uid(10000)); CHECK(ksu_is_manager_uid(75536));
    ksu_unregister_manager(2 * PER_USER_RANGE + 75536);
    CHECK(!ksu_has_manager()); CHECK_EQ(ksu_get_manager_appid(), UINT32_MAX);
    ksu_register_manager(75536, KSU_SIG_MILKSU); ksu_register_manager(10000, KSU_SIG_OFFICIAL);
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(75536), KSU_SIG_MILKSU);
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(10000), KSU_SIG_OFFICIAL);
    ksu_unregister_manager_by_signature_index(KSU_SIG_OFFICIAL);
    CHECK(ksu_is_manager_uid(75536)); CHECK(!ksu_is_manager_uid(10000));
    CHECK_EQ(ksu_get_manager_appid(), 75536);
}
static void case_dynamic_denied(void)
{
    ksu_register_manager(10000, KSU_SIG_BAKASU);
    ksu_register_manager(10003, KSU_SIG_FINASU);
    ksu_register_manager(75536, KSU_SIGNATURE_INDEX_FINASU_DYNAMIC_MANAGER);
    host_uid = 7 * PER_USER_RANGE + 75536;
    ksu_mark_manager(host_uid); CHECK_EQ(ksu_get_manager_appid(), 75536);
    backend_denied_appid = 75536;
    backend_denied_full_uid = host_uid;
    CHECK(!ksu_is_manager_uid(host_uid)); CHECK_EQ(backend_last_appid, 75536);
    CHECK_EQ(backend_last_signature, 252); CHECK(!is_manager());
    CHECK_EQ(ksu_get_manager_appid(), UINT32_MAX);
    CHECK_EQ(ksu_last_manager_appid, 75536); CHECK(ksu_has_manager());
    CHECK_EQ(get_caller_signature_index(), 252); CHECK(!finasu_or_root());
    struct file session = { .su_session = true };
    const unsigned commands[] = { KSU_FINASU_IOCTL_GET_DYNAMIC_MANAGERS,
        KSU_FINASU_IOCTL_GET_UTS_VIEW_CONFIG, KSU_FINASU_IOCTL_SET_UTS_VIEW_CONFIG,
        KSU_FINASU_IOCTL_GET_NETISOLATE_CONFIG, KSU_FINASU_IOCTL_SET_NETISOLATE_CONFIG,
        KSU_FINASU_IOCTL_GET_NETISOLATE_POLICIES, KSU_FINASU_IOCTL_SET_NETISOLATE_POLICIES,
        KSU_FINASU_IOCTL_GET_NETISOLATE_EVENTS, KSU_FINASU_IOCTL_CLEAR_NETISOLATE_EVENTS,
        KSU_IOCTL_FINASU_GET_TRY_UMOUNT, KSU_IOCTL_GET_FEATURE, KSU_IOCTL_GET_MANAGER_APPID };
    unsigned calls = unrelated_calls;
    for (unsigned i = 0; i < ARRAY_SIZE(commands); i++)
        CHECK_EQ(ksu_supercall_handle_ioctl(&session, commands[i], NULL), -EPERM);
    CHECK_EQ(unrelated_calls, calls);
    unsigned auth_calls = backend_authorization_calls;
    ksu_register_manager(host_uid, KSU_SIG_OFFICIAL);
    ksu_register_manager(3 * PER_USER_RANGE + 75536, KSU_SIG_MILKSU);
    CHECK_EQ(backend_authorization_calls, auth_calls);
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(75536), 252);
    unsigned char bytes[32] = {0}; struct ksu_get_managers_cmd *list = (void *)bytes;
    list->count = 4; CHECK_EQ(do_get_managers(list), 0);
    CHECK_EQ(list->count, 3); CHECK_EQ(list->total_count, 3);
    CHECK_EQ(list->managers[2].uid, 75536); CHECK_EQ(list->managers[2].signature_index, 252);
    CHECK(ksu_is_manager_uid(10000)); CHECK(ksu_is_manager_uid(10003));
    ksu_mark_manager(10000); CHECK_EQ(ksu_get_manager_appid(), 10000);
    ksu_mark_manager(host_uid); CHECK_EQ(ksu_get_manager_appid(), 10000);
    ksu_mark_manager(10003); ksu_unregister_manager(10003);
    CHECK_EQ(ksu_get_manager_appid(), 10000);
    backend_version_present = true; struct ksu_get_info_cmd info = {0};
    unsigned versions = backend_version_calls;
    CHECK_EQ(do_get_info(&info), 0); CHECK_EQ(info.version, KERNEL_SU_VERSION);
    CHECK(!(info.flags & KSU_GET_INFO_FLAG_MANAGER)); CHECK_EQ(backend_version_calls, versions);
    backend_denied_appid = UINT32_MAX; backend_denied_full_uid = UINT32_MAX;
    CHECK(is_manager()); CHECK(finasu_or_root()); ksu_mark_manager(host_uid);
    CHECK_EQ(ksu_get_manager_appid(), 75536);
    CHECK_EQ(ksu_supercall_handle_ioctl(NULL, KSU_FINASU_IOCTL_GET_NETISOLATE_CONFIG, NULL), -EOPNOTSUPP);
    CHECK_EQ(unrelated_calls, calls + 1); backend_version_present = false;
}
static void case_version_metadata(void)
{
    for (u8 i = 0; i < 8; i++) ksu_register_manager(10000 + i, i);
    for (u8 i = 0; i < 4; i++) ksu_register_manager(11252 + i, 252 + i);
    backend_version_present = true;
    for (u32 appid = 10000; appid < 10008; appid++) {
        host_uid = 4 * PER_USER_RANGE + appid;
        unsigned previous = backend_version_calls;
        struct ksu_get_info_cmd cmd = { .uapi_version = 4 };
        CHECK_EQ(do_get_info(&cmd), 0); CHECK_EQ(cmd.uapi_version, 4);
        CHECK_EQ(cmd.version, appid == 10003 ? backend_version_value : KERNEL_SU_VERSION);
        CHECK_EQ(backend_version_calls, previous + (appid == 10003));
        if (appid == 10003) CHECK_EQ(backend_last_version_uid, host_uid);
    }
    for (u32 appid = 11252; appid < 11256; appid++) {
        host_uid = 9 * PER_USER_RANGE + appid;
        unsigned previous = backend_version_calls;
        struct ksu_get_info_cmd cmd = {0}; CHECK_EQ(do_get_info(&cmd), 0);
        CHECK_EQ(cmd.version, appid == 11252 ? backend_version_value : KERNEL_SU_VERSION);
        CHECK_EQ(backend_version_calls, previous + (appid == 11252));
        if (appid == 11252) CHECK_EQ(backend_last_version_uid, host_uid);
    }
    host_uid = 11252; backend_version_present = false;
    struct ksu_get_info_cmd cmd = {0}; unsigned previous = backend_version_calls;
    CHECK_EQ(do_get_info(&cmd), 0); CHECK_EQ(cmd.version, KERNEL_SU_VERSION);
    CHECK_EQ(backend_version_calls, previous + 1);
    backend_version_present = true; backend_denied_appid = 11252;
    previous = backend_version_calls; memset(&cmd, 0, sizeof(cmd));
    CHECK_EQ(do_get_info(&cmd), 0); CHECK_EQ(cmd.version, KERNEL_SU_VERSION);
    CHECK_EQ(backend_version_calls, previous);
    struct file executable = { .refs = 1 }; struct mm_struct mm = { .exe = &executable };
    host_uid = 0; current->mm = &mm; daemon_signature = 3;
    memset(&cmd, 0, sizeof(cmd)); CHECK_EQ(do_get_info(&cmd), 0);
    CHECK_EQ(cmd.version, KERNEL_SU_VERSION); CHECK_EQ(backend_version_calls, previous);
    CHECK_EQ(executable.refs, 1); current->mm = NULL;
    backend_denied_appid = UINT32_MAX; backend_version_present = false;
}
static void check_census(u16 capacity, u16 total, u16 copied)
{
    size_t size = sizeof(struct ksu_get_managers_cmd) + capacity * sizeof(struct ksu_manager_entry);
    unsigned char *bytes = malloc(size + 16); CHECK(bytes);
    memset(bytes, 0xa5, size + 16);
    struct ksu_get_managers_cmd *cmd = (void *)bytes;
    cmd->count = capacity; cmd->total_count = 0xbeef;
    CHECK_EQ(do_get_managers(cmd), 0);
    CHECK_EQ(cmd->count, copied); CHECK_EQ(cmd->total_count, total);
    const u32 uids[] = { 15001, 15002, 15003 };
    const u8 signatures[] = { KSU_SIG_BAKASU, KSU_SIG_MILKSU, 255 };
    for (u16 i = 0; i < copied; i++) {
        CHECK_EQ(cmd->managers[i].uid, uids[i]);
        CHECK_EQ(cmd->managers[i].signature_index, signatures[i]);
    }
    for (size_t i = sizeof(*cmd) + copied * sizeof(struct ksu_manager_entry); i < size + 16; i++)
        CHECK_EQ(bytes[i], 0xa5);
    free(bytes);
}
static void case_census(void)
{
    check_census(0, 0, 0); check_census(10, 0, 0);
    ksu_register_manager(3 * PER_USER_RANGE + 15001, KSU_SIG_BAKASU);
    ksu_register_manager(15002, KSU_SIG_MILKSU); ksu_register_manager(15003, 255);
    check_census(0, 3, 0); check_census(1, 3, 1); check_census(2, 3, 2); check_census(9, 3, 3);
    unsigned char bytes[32] = {0}; struct ksu_get_managers_cmd *cmd = (void *)bytes;
    cmd->count = 1; alloc_fail_after = 0; CHECK_EQ(do_get_managers(cmd), -ENOMEM);
    cmd->count = 0; CHECK_EQ(do_get_managers(cmd), 0); CHECK_EQ(cmd->total_count, 3);
    alloc_fail_after = -1; cmd->count = 1; to_fault = true;
    CHECK_EQ(do_get_managers(cmd), -EFAULT); to_fault = false;
    from_fault = true; CHECK_EQ(do_get_managers(cmd), -EFAULT); from_fault = false;
}
static void case_rcu(void)
{
    ksu_register_manager(19001, KSU_SIG_MILKSU);
    remove_at_unlock = 19001;
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(19001), KSU_SIG_MILKSU);
    CHECK(!ksu_is_manager_uid(19001));
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(19001), -ENODATA);
    ksu_register_manager(15001, KSU_SIG_BAKASU);
    remove_at_unlock = 15001;
    check_census(1, 1, 1);
    CHECK(!ksu_has_manager()); check_census(0, 0, 0);
    CHECK_EQ(rcu_depth, 0); CHECK_EQ(deferred_count, 0);
}
static void case_identity(void)
{
    struct file executable = { .refs = 1 }; struct mm_struct mm = { .exe = &executable };
    for (u8 i = 0; i < 8; i++) ksu_register_manager(10000 + i, i);
    ksu_mark_manager(10001);
    CHECK_EQ(get_caller_signature_index(), -ENODATA);
    current->mm = &mm;
    for (int i = -1; i <= 7; i++) {
        daemon_signature = i < 0 ? -ENODATA : i;
        CHECK_EQ(get_caller_signature_index(), daemon_signature);
        CHECK(daemon_examined == &executable); CHECK_EQ(executable.refs, 1);
    }
    CHECK_EQ(exe_gets, exe_puts); CHECK_EQ(daemon_calls, 9);
    for (u8 i = 0; i < 8; i++) {
        host_uid = 7 * PER_USER_RANGE + 10000 + i;
        CHECK_EQ(get_caller_signature_index(), i);
    }
    CHECK_EQ(daemon_calls, 9);
    host_uid = 19999; CHECK_EQ(get_caller_signature_index(), -ENODATA);
    host_uid = 0; mm.exe = NULL;
    CHECK_EQ(get_caller_signature_index(), -ENODATA); CHECK_EQ(daemon_calls, 9);
    current->mm = NULL;
}
static void case_info(void)
{
    const u32 versions[] = { 6, 4, 5, 6, 6, 6, 6, 5 };
    const u32 maxima[][4] = { {7,7,7,7}, {5,5,7,7}, {7,7,10004,10004}, {11,11,11,11},
                              {7,7,7,7}, {10004,10004,10004,10004}, {7,7,7,7}, {7,7,10004,10004} };
    struct file executable = { .refs = 1 }; struct mm_struct mm = { .exe = &executable };
    struct ksu_get_info_cmd cmd;
    for (u8 i = 0; i < 8; i++) ksu_register_manager(10000 + i, i);
    ksu_mark_manager(10001);
    memset(&cmd, 0, sizeof(cmd)); CHECK_EQ(do_get_info(&cmd), 0); CHECK_EQ(cmd.uapi_version, 6);
    current->mm = &mm;
    for (unsigned i = 0; i < 8; i++) {
        daemon_signature = i;
        for (u32 requested = 0; requested <= 7; requested++) {
            memset(&cmd, 0, sizeof(cmd)); cmd.uapi_version = requested;
            CHECK_EQ(do_get_info(&cmd), 0);
            u32 expected = requested >= 3 && requested <= 6 ? requested : versions[i];
            CHECK_EQ(cmd.uapi_version, expected);
            CHECK_EQ(cmd.version, KERNEL_SU_VERSION); CHECK_EQ(cmd.features, maxima[i][expected - 3]);
            CHECK(!(cmd.flags & KSU_GET_INFO_FLAG_PR_BUILD));
#ifdef MODULE
            CHECK(cmd.flags & KSU_GET_INFO_FLAG_LKM);
#else
            CHECK(!(cmd.flags & KSU_GET_INFO_FLAG_LKM));
#endif
        }
        host_uid = 9 * PER_USER_RANGE + 10000 + i;
        for (u32 requested = 0; requested <= 7; requested++) {
            memset(&cmd, 0, sizeof(cmd)); cmd.uapi_version = requested;
            CHECK_EQ(do_get_info(&cmd), 0);
            u32 expected = requested >= 3 && requested <= 6 ? requested : versions[i];
            CHECK_EQ(cmd.uapi_version, expected);
            CHECK_EQ(cmd.features, maxima[i][expected - 3]); CHECK(cmd.flags & KSU_GET_INFO_FLAG_MANAGER);
        }
        host_uid = 0;
    }
    const int unknown[] = { -ENODATA, 253, 254, 255 };
    for (unsigned i = 0; i < ARRAY_SIZE(unknown); i++) {
        daemon_signature = unknown[i]; memset(&cmd, 0, sizeof(cmd)); cmd.uapi_version = UINT32_MAX;
        CHECK_EQ(do_get_info(&cmd), 0); CHECK_EQ(cmd.uapi_version, 6);
        CHECK_EQ(cmd.features, 7);
    }
    daemon_signature = 252; memset(&cmd, 0, sizeof(cmd));
    CHECK_EQ(do_get_info(&cmd), 0); CHECK_EQ(cmd.uapi_version, 6); CHECK_EQ(cmd.features, 11);
    ksu_register_manager(75536, 252); host_uid = 5 * PER_USER_RANGE + 75536;
    memset(&cmd, 0, sizeof(cmd)); cmd.uapi_version = 4;
    CHECK_EQ(do_get_info(&cmd), 0); CHECK_EQ(cmd.uapi_version, 4); CHECK_EQ(cmd.features, 11);
    host_uid = 0; daemon_signature = -ENODATA;
    preinit_enabled = true; memset(&cmd, 0, sizeof(cmd)); CHECK_EQ(do_get_info(&cmd), 0);
    CHECK(cmd.flags & KSU_GET_INFO_FLAG_PREINIT);
    ksu_late_loaded = true; memset(&cmd, 0, sizeof(cmd)); CHECK_EQ(do_get_info(&cmd), 0);
    CHECK(cmd.flags & KSU_GET_INFO_FLAG_LATE_LOAD); CHECK(!(cmd.flags & KSU_GET_INFO_FLAG_PREINIT));
    ksu_late_loaded = false; preinit_enabled = false;
    from_fault = true; CHECK_EQ(do_get_info(&cmd), 0); CHECK_EQ(cmd.uapi_version, 6); from_fault = false;
    to_fault = true; CHECK_EQ(do_get_info(&cmd), -EFAULT); to_fault = false;
    unsigned char legacy[32]; memset(legacy, 0xa5, sizeof(legacy));
    CHECK_EQ(do_get_info_legacy(legacy), 0); CHECK_EQ(last_copy_size, 12);
    CHECK_EQ(((struct ksu_get_info_legacy_cmd *)(void *)legacy)->features, 7);
    for (unsigned i = 12; i < sizeof(legacy); i++) CHECK_EQ(legacy[i], 0xa5);
    current->mm = NULL; CHECK_EQ(executable.refs, 1);
}
static void case_uapi_metadata(void)
{
    const struct { u8 signature; u32 uapi, maximum; } profiles[] = {
        {1,4,5}, {1,5,7}, {2,4,7}, {2,5,10004}, {7,4,7}, {7,5,10004},
        {0,6,7}, {3,6,11}, {252,6,11}, {5,6,10004}, {1,3,5}, {2,6,10004},
    };
    struct file executable = { .refs = 1 }; struct mm_struct mm = { .exe = &executable };
    for (unsigned i = 0; i < ARRAY_SIZE(profiles); i++) {
        u32 appid = 14000 + i;
        ksu_register_manager_with_uapi(appid, profiles[i].signature, profiles[i].uapi);
        CHECK_EQ(ksu_get_manager_uapi_by_appid(appid), profiles[i].uapi);
        for (unsigned root = 0; root < 2; root++) {
            host_uid = root ? 0 : 10 * PER_USER_RANGE + appid;
            current->mm = root ? &mm : NULL;
            daemon_signature = profiles[i].signature; daemon_uapi_version = profiles[i].uapi;
            u32 detected = 0;
            CHECK_EQ(get_caller_manager_info(&detected), profiles[i].signature);
            CHECK_EQ(detected, profiles[i].uapi);
            struct ksu_get_info_cmd info = {0}; CHECK_EQ(do_get_info(&info), 0);
            CHECK_EQ(info.uapi_version, profiles[i].uapi); CHECK_EQ(info.features, profiles[i].maximum);
            for (u32 requested = 3; requested <= 6; requested++) {
                memset(&info, 0, sizeof(info)); info.uapi_version = requested;
                CHECK_EQ(do_get_info(&info), 0); CHECK_EQ(info.uapi_version, requested);
            }
        }
    }
    CHECK_EQ(executable.refs, 1); CHECK_EQ(exe_gets, exe_puts);
    current->mm = NULL; daemon_uapi_version = 0;
}
static void case_uapi_metadata_rcu(void)
{
    ksu_register_manager_with_uapi(75536, KSU_SIG_KSUNEXT, 4);
    ksu_register_manager_with_uapi(7 * PER_USER_RANGE + 75536, KSU_SIG_OFFICIAL, 5);
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(75536), KSU_SIG_KSUNEXT);
    CHECK_EQ(ksu_get_manager_uapi_by_appid(75536), 4);
    remove_at_unlock = 75536;
    CHECK_EQ(ksu_get_manager_uapi_by_appid(75536), 4);
    CHECK_EQ(ksu_get_manager_uapi_by_appid(75536), 0);
    CHECK_EQ(ksu_get_manager_signature_index_by_appid(75536), -ENODATA);
    CHECK_EQ(ksu_get_manager_appid(), UINT32_MAX);
}
static void case_feature_translation(void)
{
    const int families[] = { 0, 1, 2, 3, 4, 5, 6, 7, 252, 253, 254, 255, -ENODATA };
    const u32 fina_ids[] = { 10010, 10003, 6, 10011, 10012, 10013 };
    for (unsigned i = 0; i + 1 < ARRAY_SIZE(families); i++) ksu_register_manager(10000 + i, families[i]);
    for (unsigned i = 0; i < ARRAY_SIZE(families); i++) {
        host_uid = 10000 + i;
        for (u32 id = 5; id <= 10; id++)
            CHECK_EQ(translate_feature_id_for_caller(id),
                     families[i] == 3 || families[i] == 252 ? fina_ids[id - 5] : id);
        CHECK_EQ(translate_feature_id_for_caller(10003),
                 families[i] == 2 || families[i] == 5 || families[i] == 7 ? 10004 : 10003);
        CHECK_EQ(translate_feature_id_for_caller(UINT32_MAX), UINT32_MAX);
    }
    struct file executable = { .refs = 1 }; struct mm_struct mm = { .exe = &executable };
    host_uid = 0; current->mm = &mm; daemon_signature = 3;
    const u32 early_ids[] = { 0, 1, 2, 3, 4, 11, 10004, 10010, 10011, 10012, 10013, UINT32_MAX };
    for (unsigned i = 0; i < ARRAY_SIZE(early_ids); i++)
        CHECK_EQ(translate_feature_id_for_caller(early_ids[i]), early_ids[i]);
    CHECK_EQ(daemon_calls, 0);
    for (u32 id = 5; id <= 10; id++) CHECK_EQ(translate_feature_id_for_caller(id), fina_ids[id - 5]);
    CHECK_EQ(daemon_calls, 6); CHECK(daemon_examined == &executable);
    daemon_signature = 5; CHECK_EQ(translate_feature_id_for_caller(10003), 10004);
    daemon_signature = -ENODATA; CHECK_EQ(translate_feature_id_for_caller(6), 6);
    CHECK_EQ(exe_gets, exe_puts); CHECK_EQ(executable.refs, 1); current->mm = NULL;
}
#ifdef HOST_FEATURE_TESTS
static u64 shell_value;
static int shell_get(u64 *value) { *value = shell_value; return 0; }
static int shell_set(u64 value) { shell_value = value; return 0; }
static const struct ksu_feature_handler shell_handler = {
    .feature_id = KSU_FEATURE_SHELL_SU_ADB_ONLY, .name = "host-shell",
    .get_handler = shell_get, .set_handler = shell_set,
};
static bool full_avc_enabled(void)
{
#ifdef CONFIG_KSU_SUSFS
    return static_key_enabled(&ksu_avc_log_spoof_full_enabled);
#else
    return false;
#endif
}
static void reset_features(void)
{
    memset(forced_mask, 0, sizeof(forced_mask));
    memset(forced_pending, 0, sizeof(forced_pending));
    memset(forced_values, 0, sizeof(forced_values));
    susfs_ksu_sid = 111; susfs_priv_app_sid = 222; shell_value = 0;
    susfs_is_avc_log_spoofing_enabled.enabled = false;
#ifdef CONFIG_KSU_SUSFS
    ksu_avc_log_spoof_full_enabled.enabled = false;
#endif
    ksu_feature_init(); CHECK_EQ(ksu_register_feature_handler(&shell_handler), 0);
}
static void case_features(void)
{
    reset_features(); case_feature_translation();
    host_uid = 10003;
    struct ksu_set_feature_cmd set = { .feature_id = 6, .value = 1 };
    CHECK_EQ(do_set_feature(&set), 0); CHECK_EQ(set.feature_id, 6); CHECK_EQ(shell_value, 0);
    CHECK(!full_avc_enabled()); CHECK(susfs_is_avc_log_spoofing_enabled.enabled);
    struct ksu_get_feature_cmd get = { .feature_id = 6, .value = 999, .supported = 255 };
    CHECK_EQ(do_get_feature(&get), 0); CHECK_EQ(get.feature_id, 6);
    CHECK_EQ(get.value, 1); CHECK_EQ(get.supported, KSU_FEATURE_FLAG_SUPPORTED);
    set.feature_id = 7; CHECK_EQ(do_set_feature(&set), 0); CHECK_EQ(shell_value, 1);
    get.feature_id = 7; CHECK_EQ(do_get_feature(&get), 0); CHECK_EQ(get.feature_id, 7);
    CHECK_EQ(get.value, 1);
    set.feature_id = 6; set.value = 0; CHECK_EQ(do_set_feature(&set), 0); CHECK_EQ(shell_value, 1);
    host_uid = 10005; set.feature_id = 10003; set.value = 1;
    CHECK_EQ(do_set_feature(&set), 0); CHECK_EQ(set.feature_id, 10003);
    CHECK(full_avc_enabled()); CHECK(susfs_is_avc_log_spoofing_enabled.enabled);
    get.feature_id = 10003; CHECK_EQ(do_get_feature(&get), 0);
    CHECK_EQ(get.feature_id, 10003); CHECK_EQ(get.value, 1);
    const u32 native_uids[] = { 10000, 10005 };
    for (unsigned i = 0; i < ARRAY_SIZE(native_uids); i++) {
        set.feature_id = 6; set.value = 0;
        host_uid = native_uids[i]; CHECK_EQ(do_set_feature(&set), 0); CHECK_EQ(shell_value, 0);
        CHECK(full_avc_enabled()); CHECK(susfs_is_avc_log_spoofing_enabled.enabled);
        get.feature_id = 6; CHECK_EQ(do_get_feature(&get), 0); CHECK_EQ(get.feature_id, 6);
        CHECK_EQ(get.value, 0); CHECK_EQ(get.supported, KSU_FEATURE_FLAG_SUPPORTED);
    }
    host_uid = 10003; set.feature_id = 6; set.value = 1; CHECK_EQ(do_set_feature(&set), 0);
    CHECK(!full_avc_enabled()); CHECK(susfs_is_avc_log_spoofing_enabled.enabled);
    set_bit(feature_slot(6), forced_mask);
    get.feature_id = 7; CHECK_EQ(do_get_feature(&get), 0); CHECK_EQ(get.feature_id, 7);
    CHECK_EQ(get.supported, KSU_FEATURE_FLAG_SUPPORTED | KSU_FEATURE_FLAG_FORCED);
    set.feature_id = 7; CHECK_EQ(do_set_feature(&set), -EPERM);
    get.feature_id = 6; CHECK_EQ(do_get_feature(&get), 0);
    CHECK_EQ(get.supported, KSU_FEATURE_FLAG_SUPPORTED);
    set.feature_id = 6; CHECK_EQ(do_set_feature(&set), 0);
    clear_bit(feature_slot(6), forced_mask);
    host_uid = 10000; CHECK_EQ(ksu_unregister_feature_handler(6), 0);
    get.feature_id = 6; CHECK_EQ(do_get_feature(&get), 0); CHECK_EQ(get.supported, 0);
    CHECK_EQ(get.value, 0); CHECK_EQ(do_set_feature(&set), -EOPNOTSUPP);
    get.feature_id = UINT32_MAX; CHECK_EQ(do_get_feature(&get), 0);
    CHECK_EQ(get.feature_id, UINT32_MAX); CHECK_EQ(get.supported, 0);
    from_fault = true; CHECK_EQ(do_get_feature(&get), -EFAULT);
    CHECK_EQ(do_set_feature(&set), -EFAULT); from_fault = false;
    to_fault = true; CHECK_EQ(do_get_feature(&get), -EFAULT); to_fault = false;
}
static void case_avc(void)
{
    u64 value = 99; bool supported = false;
    ksu_feature_init();
    CHECK(KSU_FEATURE_AVC_SPOOF >= 10003); CHECK(KSU_FEATURE_MAX < KSU_FEATURE_AVC_SPOOF);
    CHECK_EQ(ksu_get_feature(10003, NULL, &supported), -EINVAL);
    CHECK_EQ(ksu_get_feature(10003, &value, NULL), -EINVAL);
    CHECK_EQ(ksu_get_feature(10003, &value, &supported), 0);
#ifdef CONFIG_KSU_SUSFS
    CHECK(supported); CHECK_EQ(value, 0);
    CHECK_EQ(ksu_set_feature(10003, 1), 0);
    CHECK_EQ(ksu_get_feature(10003, &value, &supported), 0); CHECK_EQ(value, 1);
    CHECK_EQ(ksu_set_feature(10003, 0), 0);
    CHECK_EQ(ksu_set_feature(10003, 2), -EINVAL);
    CHECK_EQ(ksu_set_feature(10003, UINT64_MAX), -EINVAL);
    CHECK_EQ(ksu_get_feature(10003, &value, &supported), 0); CHECK_EQ(value, 0);
#if IS_BUILTIN(CONFIG_KSU)
    CHECK_EQ(ksu_get_feature(10004, &value, &supported), 0); CHECK(supported); CHECK_EQ(value, 0);
    CHECK_EQ(ksu_set_feature(10004, 1), 0); CHECK(full_avc_enabled());
    CHECK_EQ(ksu_get_feature(10003, &value, &supported), 0); CHECK_EQ(value, 1);
    CHECK_EQ(ksu_get_feature(10004, &value, &supported), 0); CHECK_EQ(value, 1);
    CHECK_EQ(ksu_set_feature(10003, 1), 0); CHECK(!full_avc_enabled());
    CHECK_EQ(ksu_get_feature(10004, &value, &supported), 0); CHECK_EQ(value, 0);
    CHECK_EQ(ksu_set_feature(10004, 2), -EINVAL);
    CHECK_EQ(ksu_set_feature(10004, UINT64_MAX), -EINVAL);
    CHECK_EQ(ksu_set_feature(10004, 0), 0);
#else
    CHECK_EQ(ksu_get_feature(10004, &value, &supported), 0); CHECK(!supported);
    CHECK_EQ(ksu_set_feature(10004, 1), -EOPNOTSUPP);
#endif
#else
    CHECK(!supported); CHECK_EQ(value, 0); CHECK_EQ(ksu_set_feature(10003, 1), -EOPNOTSUPP);
    CHECK_EQ(ksu_get_feature(10004, &value, &supported), 0); CHECK(!supported);
    CHECK_EQ(ksu_set_feature(10004, 1), -EOPNOTSUPP);
#endif
}
static void case_avc_sids(void)
{
    reset_features();
    const u32 bad_pairs[][2] = { {0, 222}, {111, 0}, {111, 111}, {0, 0} };
    for (unsigned i = 0; i < ARRAY_SIZE(bad_pairs); i++) {
        susfs_ksu_sid = bad_pairs[i][0]; susfs_priv_app_sid = bad_pairs[i][1];
        for (u32 id = 10003; id <= 10004; id++) {
            CHECK_EQ(ksu_set_feature(id, 2), -EINVAL);
            CHECK_EQ(ksu_set_feature(id, 0), 0);
            CHECK_EQ(ksu_set_feature(id, 1), -EOPNOTSUPP);
            CHECK(!susfs_is_avc_log_spoofing_enabled.enabled); CHECK(!full_avc_enabled());
        }
    }
    susfs_ksu_sid = 111; susfs_priv_app_sid = 222;
    CHECK_EQ(ksu_set_feature(10004, 1), 0); CHECK(full_avc_enabled());
    susfs_priv_app_sid = 111;
    CHECK_EQ(ksu_set_feature(10003, 1), -EOPNOTSUPP);
    CHECK(susfs_is_avc_log_spoofing_enabled.enabled); CHECK(full_avc_enabled());
    CHECK_EQ(ksu_set_feature(10003, 0), 0);
    CHECK(!susfs_is_avc_log_spoofing_enabled.enabled); CHECK(!full_avc_enabled());
}
static int capability_get(u64 *value) { *value = 1; return 0; }
static void case_sparse_slots(void)
{
    ksu_feature_init();
    const u32 ids[] = { 0, 1, 2, 3, 4, 5, 6, 10003, 10004, 10010, 10011, 10012, 10013 };
    CHECK_EQ(KSU_FEATURE_SLOT_COUNT, 13); CHECK_EQ(KSU_FEATURE_MAX, 7);
    CHECK_EQ(ARRAY_SIZE(feature_handlers), 13); CHECK_EQ(ARRAY_SIZE(feature_ids), 13);
    CHECK_EQ(ARRAY_SIZE(forced_values), 13); CHECK_EQ(ARRAY_SIZE(feature_names), 13);
    for (unsigned i = 0; i < ARRAY_SIZE(ids); i++) {
        CHECK_EQ(feature_ids[i], ids[i]); CHECK_EQ(feature_slot(ids[i]), i);
        for (unsigned j = i + 1; j < ARRAY_SIZE(ids); j++) CHECK(ids[i] != ids[j]);
    }
    const u32 absent[] = { 7, 8, 9, 10, 10000, 10002, 10005, 10009, 10014, UINT32_MAX };
    for (unsigned i = 0; i < ARRAY_SIZE(absent); i++) {
        u64 value = 99; bool supported = true;
        CHECK_EQ(feature_slot(absent[i]), -EINVAL);
        CHECK_EQ(ksu_get_feature(absent[i], &value, &supported), -EINVAL);
        CHECK_EQ(value, 0); CHECK(!supported); CHECK(!ksu_feature_is_forced(absent[i]));
        CHECK_EQ(ksu_set_feature(absent[i], 1), -EINVAL);
    }
    CHECK(feature_handlers[feature_slot(10003)] != NULL);
    CHECK(feature_handlers[feature_slot(10004)] != NULL);
    CHECK_EQ(ksu_register_feature_handler(NULL), -EINVAL);
    struct ksu_feature_handler invalid = { .feature_id = 10000, .get_handler = capability_get };
    CHECK_EQ(ksu_register_feature_handler(&invalid), -EINVAL);
    invalid.feature_id = 10013; invalid.get_handler = NULL;
    CHECK_EQ(ksu_register_feature_handler(&invalid), -EINVAL);
    CHECK_EQ(ksu_unregister_feature_handler(UINT32_MAX), -EINVAL);
    CHECK_EQ(ksu_unregister_feature_handler(10013), -ENOENT);
}
static void case_capability_routing(void)
{
    /* Backend capabilities are fixtures, not proof of the forthcoming port. */
    static const struct ksu_feature_handler dynamic = { .feature_id = 10010, .name = "host-capability", .get_handler = capability_get };
    static const struct ksu_feature_handler grants = { .feature_id = 10011, .name = "host-grants", .get_handler = capability_get };
    reset_features(); CHECK_EQ(ksu_register_feature_handler(&dynamic), 0);
    CHECK_EQ(ksu_register_feature_handler(&grants), 0);
    ksu_register_manager(10003, 3); ksu_register_manager(11252, 252);
    const u32 uids[] = {10003, 11252};
    for (unsigned i = 0; i < ARRAY_SIZE(uids); i++) {
        host_uid = uids[i];
        const u32 features[] = {5, 8};
        for (unsigned j = 0; j < ARRAY_SIZE(features); j++) {
            struct ksu_get_feature_cmd get = { .feature_id = features[j] };
            struct ksu_set_feature_cmd set = { .feature_id = features[j], .value = 1 };
            CHECK_EQ(do_get_feature(&get), 0); CHECK_EQ(get.feature_id, features[j]);
            CHECK_EQ(get.value, 1); CHECK_EQ(get.supported, KSU_FEATURE_FLAG_SUPPORTED);
            CHECK_EQ(do_set_feature(&set), -EOPNOTSUPP); CHECK_EQ(set.feature_id, features[j]);
        }
    }
}
static void case_force_parser(void)
{
    reset_features(); u32 slot = UINT32_MAX;
    const char *names[] = { "10003", "AVC_SPOOF", "10004", "AvC_SpOoF_FuLl", "10010", "DyNaMiC_MaNaGeR",
                            "10011", "DYNAMIC_MANAGER_GRANTS", "10012", "UTS_VIEW", "10013", "MOUNT_VIEW_FILTER" };
    const u32 slots[] = {7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12};
    for (unsigned i = 0; i < ARRAY_SIZE(names); i++) {
        CHECK_EQ(parse_feature_id(names[i], &slot), 0); CHECK_EQ(slot, slots[i]);
    }
    CHECK_EQ(parse_feature_id("10005", &slot), -EINVAL);
    CHECK_EQ(parse_feature_id("missing", &slot), -EINVAL);
    alloc_fail_after = 0;
    CHECK_EQ(force_feature_param_set(NULL, NULL), 0);
    CHECK_EQ(force_feature_param_set(",,invalid:1,10005:1,sulog:-1,", NULL), 0);
    CHECK_EQ(forced_mask[0], 0);
    CHECK_EQ(force_feature_param_set("AVC_SPOOF_FULL:1,avc_spoof:0,avc_spoof:1,ShElL_sU_AdB_OnLy:1", NULL), 0);
    alloc_fail_after = -1;
    CHECK_EQ(forced_values[7], 1); CHECK_EQ(forced_values[8], 1);
    CHECK(test_bit(7, forced_mask)); CHECK(test_bit(8, forced_mask)); CHECK(test_bit(6, forced_mask));
    CHECK(ksu_feature_is_forced(10003)); CHECK(ksu_feature_is_forced(10004)); CHECK(ksu_feature_is_forced(6));
    ksu_feature_apply_forced(); CHECK(full_avc_enabled()); CHECK_EQ(shell_value, 1);
    CHECK(!test_bit(7, forced_pending)); CHECK(!test_bit(8, forced_pending)); CHECK(!test_bit(6, forced_pending));
    CHECK_EQ(ksu_set_feature(10003, 0), -EPERM); CHECK_EQ(ksu_set_feature(10004, 0), -EPERM);
    reset_features(); CHECK_EQ(force_feature_param_set("avc_spoof:1", NULL), 0);
    CHECK(ksu_feature_is_forced(10004)); CHECK(!ksu_feature_is_forced(6));
    susfs_ksu_sid = 0; ksu_feature_apply_forced(); CHECK(test_bit(7, forced_pending));
    CHECK(!susfs_is_avc_log_spoofing_enabled.enabled);
    susfs_ksu_sid = 111; ksu_feature_apply_forced(); CHECK(!test_bit(7, forced_pending));
    CHECK(susfs_is_avc_log_spoofing_enabled.enabled); CHECK(!full_avc_enabled());
    ksu_register_manager(10000, 0); ksu_register_manager(10003, 3); host_uid = 10003;
    struct ksu_get_feature_cmd get = { .feature_id = 6 };
    CHECK_EQ(do_get_feature(&get), 0); CHECK_EQ(get.feature_id, 6);
    CHECK_EQ(get.supported, KSU_FEATURE_FLAG_SUPPORTED | KSU_FEATURE_FLAG_FORCED);
    struct ksu_set_feature_cmd set = { .feature_id = 7, .value = 1 };
    CHECK_EQ(do_set_feature(&set), 0); CHECK_EQ(shell_value, 1);
    host_uid = 10000; get.feature_id = 6; CHECK_EQ(do_get_feature(&get), 0);
    CHECK_EQ(get.supported, KSU_FEATURE_FLAG_SUPPORTED);
    set.feature_id = 6; set.value = 0; CHECK_EQ(do_set_feature(&set), 0);
    CHECK_EQ(shell_value, 0); CHECK(susfs_is_avc_log_spoofing_enabled.enabled);
}
#endif /* HOST_FEATURE_TESTS */
static void reset_audit_keys(void)
{
    susfs_ksu_sid = 111; susfs_priv_app_sid = 222;
    susfs_is_avc_log_spoofing_enabled.enabled = false;
#ifdef CONFIG_KSU_SUSFS
    ksu_avc_log_spoof_full_enabled.enabled = false;
#endif
}
static void check_audit(u32 source, u32 target, u32 expected_source, u32 expected_target, bool auxiliary)
{
    struct selinux_state state = { .marker = 0xabcdef0123456789ULL };
    struct selinux_state original = state;
    struct common_audit_data data = { .type = LSM_AUDIT_DATA_IPC, .u.ipc_id = 12345 };
    unsigned previous = observed_audit_calls;
    CHECK_EQ(slow_avc_audit(&state, source, target, 1, 0xa501, 0x8000, 0x0400, -EACCES,
                           auxiliary ? &data : NULL), 0);
    CHECK_EQ(observed_audit_calls, previous + 1);
    CHECK_EQ(observed_audit.ssid, expected_source); CHECK_EQ(observed_audit.tsid, expected_target);
    CHECK_EQ(observed_audit.tclass, 1); CHECK_EQ(observed_audit.requested, 0xa501);
    CHECK_EQ(observed_audit.audited, 0x8000); CHECK_EQ(observed_audit.denied, 0x0400);
    CHECK_EQ(observed_audit.result, -EACCES); CHECK(observed_audit.state == &state);
    CHECK(!memcmp(&state, &original, sizeof(state)));
    CHECK_EQ(observed_audit_type, auxiliary ? LSM_AUDIT_DATA_IPC : LSM_AUDIT_DATA_NONE);
    if (auxiliary) {
        CHECK_EQ(observed_auxiliary, 12345); CHECK_EQ(data.type, LSM_AUDIT_DATA_IPC); CHECK_EQ(data.u.ipc_id, 12345);
    }
}
static void case_audit_target(void)
{
    reset_audit_keys(); susfs_is_avc_log_spoofing_enabled.enabled = true;
    check_audit(111, 111, 111, 222, true);
    check_audit(333, 111, 333, 222, false);
    check_audit(111, 333, 111, 333, true);
    check_audit(333, 444, 333, 444, false);
}
static void case_audit_full(void)
{
    reset_audit_keys();
#ifdef CONFIG_KSU_SUSFS
    susfs_is_avc_log_spoofing_enabled.enabled = true;
    ksu_avc_log_spoof_full_enabled.enabled = true;
#if IS_BUILTIN(CONFIG_KSU)
    check_audit(111, 111, 222, 222, true);
    check_audit(111, 333, 222, 333, false);
    check_audit(333, 111, 333, 222, true);
    ksu_avc_log_spoof_full_enabled.enabled = false;
    check_audit(111, 111, 111, 222, false);
#else
    check_audit(111, 111, 111, 222, true);
    check_audit(111, 333, 111, 333, false);
#endif
#else
    check_audit(111, 111, 111, 111, false);
#endif
}
static void case_audit_disabled(void)
{
    reset_audit_keys(); check_audit(111, 111, 111, 111, false);
#ifdef CONFIG_KSU_SUSFS
    ksu_avc_log_spoof_full_enabled.enabled = true;
#endif
    check_audit(111, 111, 111, 111, true);
    unsigned calls = observed_audit_calls;
    struct selinux_state state = {0};
    CHECK_EQ(slow_avc_audit(&state, 111, 111, 0, 1, 1, 1, -EACCES, NULL), -EINVAL);
    CHECK_EQ(slow_avc_audit(&state, 111, 111, ARRAY_SIZE(secclass_map), 1, 1, 1, -EACCES, NULL), -EINVAL);
    CHECK_EQ(slow_avc_audit(&state, 111, 111, UINT16_MAX, 1, 1, 1, -EACCES, NULL), -EINVAL);
    CHECK_EQ(observed_audit_calls, calls);
}
static void case_audit_invalid_sids(void)
{
    reset_audit_keys();
#ifdef CONFIG_KSU_SUSFS
    susfs_is_avc_log_spoofing_enabled.enabled = true;
    ksu_avc_log_spoof_full_enabled.enabled = true;
#endif
    const u32 pairs[][2] = { {0, 222}, {111, 0}, {111, 111}, {0, 0} };
    for (unsigned i = 0; i < ARRAY_SIZE(pairs); i++) {
        susfs_ksu_sid = pairs[i][0]; susfs_priv_app_sid = pairs[i][1];
        check_audit(pairs[i][0], pairs[i][0], pairs[i][0], pairs[i][0], i % 2);
        check_audit(333, pairs[i][0], 333, pairs[i][0], false);
    }
}
#ifdef HOST_FEATURE_TESTS
static void case_policy_audit(void)
{
    reset_features(); CHECK_EQ(ksu_set_feature(10004, 1), 0);
    check_audit(111, 111, 222, 222, true);
    CHECK_EQ(ksu_set_feature(10003, 1), 0);
    check_audit(111, 111, 111, 222, false);
    CHECK_EQ(ksu_set_feature(10003, 0), 0);
    check_audit(111, 111, 111, 111, true);
}
#endif
static void case_abi(void)
{
    CHECK_EQ(sizeof(struct ksu_get_info_cmd), 16); CHECK_EQ(offsetof(struct ksu_get_info_cmd, uapi_version), 12);
    CHECK_EQ(sizeof(struct ksu_get_info_legacy_cmd), 12);
    CHECK_EQ(KSU_IOCTL_GET_INFO, 0x80104b02U); CHECK_EQ(KSU_IOCTL_GET_INFO_LEGACY, 0x80004b02U);
    CHECK_EQ(sizeof(struct ksu_lookup_symbols_cmd), 24); CHECK_EQ(_Alignof(struct ksu_lookup_symbols_cmd), 8);
    CHECK_EQ(offsetof(struct ksu_lookup_symbols_cmd, names), 0);
    CHECK_EQ(offsetof(struct ksu_lookup_symbols_cmd, addrs), 8);
    CHECK_EQ(offsetof(struct ksu_lookup_symbols_cmd, count), 16);
    CHECK_EQ(offsetof(struct ksu_lookup_symbols_cmd, flags), 20);
    CHECK_EQ(KSU_IOCTL_LOOKUP_SYMBOLS, 0x40184b16U); CHECK_EQ(KSU_LOOKUP_SYMBOLS_MAX, 1024);
    CHECK_EQ(_IOC(_IOC_WRITE, 'K', 22, 0), 0x40004b16U);
    CHECK(KSU_IOCTL_LOOKUP_SYMBOLS != _IOC(_IOC_WRITE, 'K', 22, 0));
    CHECK_EQ(sizeof(struct ksu_get_managers_cmd), 4); CHECK_EQ(sizeof(struct ksu_manager_entry), 5);
    bool lookup_registered = false;
    for (unsigned i = 0; ksu_ioctl_handlers[i].handler; i++) {
        if (ksu_ioctl_handlers[i].cmd == KSU_IOCTL_LOOKUP_SYMBOLS) {
            CHECK(ksu_ioctl_handlers[i].handler == do_lookup_symbols);
            CHECK(ksu_ioctl_handlers[i].perm_check == only_root); lookup_registered = true;
        }
        for (unsigned j = i + 1; ksu_ioctl_handlers[j].handler; j++)
            CHECK(ksu_ioctl_handlers[i].cmd != ksu_ioctl_handlers[j].cmd);
    }
    CHECK(lookup_registered);
    CHECK_EQ(ksu_supercall_handle_ioctl(NULL, _IOR('K', 2, struct ksu_get_info_legacy_cmd), NULL), -ENOTTY);
    CHECK_EQ(ksu_supercall_handle_ioctl(NULL, _IOR('K', 22, struct ksu_lookup_symbols_cmd), NULL), -ENOTTY);
    resolver_calls = 0;
    ksu_supercall_handle_ioctl(NULL, 0x40004b16U, NULL); CHECK_EQ(resolver_calls, 0);
}
static void case_controller_abi(void)
{
    CHECK_EQ(sizeof(struct ksu_finasu_dynamic_manager_sign), 76);
    CHECK_EQ(offsetof(struct ksu_finasu_dynamic_manager_sign, hash), 8);
    CHECK_EQ(sizeof(struct ksu_finasu_dynamic_manager_cmd), 16);
    CHECK_EQ(offsetof(struct ksu_finasu_dynamic_manager_cmd, signs), 8);
    CHECK_EQ(sizeof(struct ksu_finasu_dynamic_manager_app), 8);
    CHECK_EQ(sizeof(struct ksu_finasu_get_dynamic_managers_cmd), 16);
    CHECK_EQ(offsetof(struct ksu_finasu_get_dynamic_managers_cmd, apps), 8);
    CHECK_EQ(sizeof(struct ksu_finasu_dynamic_manager_grants_cmd), 16);
    CHECK_EQ(offsetof(struct ksu_finasu_dynamic_manager_grants_cmd, appids), 8);
    CHECK_EQ(KSU_FINASU_IOCTL_SET_DYNAMIC_MANAGERS, 0x40004b16U);
    CHECK_EQ(KSU_FINASU_IOCTL_GET_DYNAMIC_MANAGERS, 0xc0104b17U);
    CHECK_EQ(KSU_FINASU_IOCTL_SET_DYNAMIC_MANAGER_GRANTS, 0x40004b18U);
    CHECK(KSU_FINASU_IOCTL_SET_DYNAMIC_MANAGERS != KSU_IOCTL_LOOKUP_SYMBOLS);
    CHECK_EQ(sizeof(struct ksu_finasu_netisolate_config), 1040);
    CHECK_EQ(offsetof(struct ksu_finasu_netisolate_config, uids), 16);
    CHECK_EQ(sizeof(struct ksu_finasu_netisolate_policy), 8);
    CHECK_EQ(sizeof(struct ksu_finasu_netisolate_policies), 2064);
    CHECK_EQ(offsetof(struct ksu_finasu_netisolate_policies, policies), 16);
    CHECK_EQ(sizeof(struct ksu_finasu_netisolate_event), 40);
    CHECK_EQ(offsetof(struct ksu_finasu_netisolate_event, uid), 8);
    CHECK_EQ(offsetof(struct ksu_finasu_netisolate_event, port), 12);
    CHECK_EQ(offsetof(struct ksu_finasu_netisolate_event, address), 16);
    CHECK_EQ(offsetof(struct ksu_finasu_netisolate_event, reserved), 32);
    CHECK_EQ(sizeof(struct ksu_finasu_netisolate_events), 2576);
    CHECK_EQ(offsetof(struct ksu_finasu_netisolate_events, events), 16);
    CHECK_EQ(sizeof(struct ksu_uts_view_config), 972);
    CHECK_EQ(offsetof(struct ksu_uts_view_config, sysname), 64);
    CHECK_EQ(offsetof(struct ksu_uts_view_config, target_count), 456);
    CHECK_EQ(offsetof(struct ksu_uts_view_config, target_uids), 460);
    CHECK_EQ(KSU_FINASU_IOCTL_GET_UTS_VIEW_CONFIG, 0xc3cc4b19U);
    CHECK_EQ(KSU_FINASU_IOCTL_SET_UTS_VIEW_CONFIG, 0x43cc4b1aU);
    CHECK_EQ(KSU_FINASU_IOCTL_GET_NETISOLATE_CONFIG, 0xc4104b1bU);
    CHECK_EQ(KSU_FINASU_IOCTL_SET_NETISOLATE_CONFIG, 0x44104b1cU);
    CHECK_EQ(KSU_FINASU_IOCTL_GET_NETISOLATE_POLICIES, 0xc8104b1dU);
    CHECK_EQ(KSU_FINASU_IOCTL_SET_NETISOLATE_POLICIES, 0x48104b1eU);
    CHECK_EQ(KSU_FINASU_IOCTL_GET_NETISOLATE_EVENTS, 0xca104b1fU);
    CHECK_EQ(KSU_FINASU_IOCTL_CLEAR_NETISOLATE_EVENTS, 0x4a104b20U);
    CHECK_EQ(_IOC_NR(KSU_FINASU_IOCTL_GET_NETISOLATE_POLICIES), _IOC_NR(KSU_IOCTL_FINASU_GET_FULL_VERSION));
    CHECK(KSU_FINASU_IOCTL_GET_NETISOLATE_POLICIES != KSU_IOCTL_FINASU_GET_FULL_VERSION);
    CHECK_EQ(sizeof(struct ksu_finasu_get_try_umount_cmd), 16);
    CHECK_EQ(offsetof(struct ksu_finasu_get_try_umount_cmd, entries), 8);
    CHECK_EQ(sizeof(struct ksu_finasu_try_umount_entry), 264);
    CHECK_EQ(offsetof(struct ksu_finasu_try_umount_entry, flags), 256);
    CHECK_EQ(offsetof(struct ksu_finasu_try_umount_entry, reserved), 260);
    CHECK_EQ(KSU_IOCTL_FINASU_GET_TRY_UMOUNT, 0xc0104b21U);
}
static void case_controller_map(void)
{
    const unsigned commands[] = { KSU_FINASU_IOCTL_SET_DYNAMIC_MANAGERS, KSU_FINASU_IOCTL_GET_DYNAMIC_MANAGERS,
        KSU_FINASU_IOCTL_SET_DYNAMIC_MANAGER_GRANTS, KSU_FINASU_IOCTL_GET_UTS_VIEW_CONFIG, KSU_FINASU_IOCTL_SET_UTS_VIEW_CONFIG,
        KSU_FINASU_IOCTL_GET_NETISOLATE_CONFIG, KSU_FINASU_IOCTL_SET_NETISOLATE_CONFIG,
        KSU_FINASU_IOCTL_GET_NETISOLATE_POLICIES, KSU_FINASU_IOCTL_SET_NETISOLATE_POLICIES,
        KSU_FINASU_IOCTL_GET_NETISOLATE_EVENTS, KSU_FINASU_IOCTL_CLEAR_NETISOLATE_EVENTS,
        KSU_IOCTL_FINASU_GET_TRY_UMOUNT };
    unsigned missing = 0;
    for (u8 i = 0; i < 8; i++) ksu_register_manager(10000 + i, i);
    for (u8 i = 0; i < 4; i++) ksu_register_manager(11252 + i, 252 + i);
    for (unsigned c = 0; c < ARRAY_SIZE(commands); c++) {
        const struct ksu_ioctl_cmd_map *entry = NULL;
        for (unsigned i = 0; ksu_ioctl_handlers[i].handler; i++)
            if (ksu_ioctl_handlers[i].cmd == commands[c]) entry = &ksu_ioctl_handlers[i];
        if (!entry) { fprintf(stderr, "Missing controller integration: cmd=0x%08x\n", commands[c]); missing++; continue; }
        CHECK(entry->perm_check); CHECK(!entry->allow_su_session);
        bool root_only = commands[c] == KSU_FINASU_IOCTL_SET_DYNAMIC_MANAGERS ||
                         commands[c] == KSU_FINASU_IOCTL_SET_DYNAMIC_MANAGER_GRANTS;
        CHECK(entry->perm_check == (root_only ? only_root : finasu_or_root));
        const u32 allowed[] = {0, 10003, 11252};
        for (unsigned i = 0; i < ARRAY_SIZE(allowed); i++) {
            host_uid = allowed[i]; unsigned previous = unrelated_calls;
            CHECK_EQ(ksu_supercall_handle_ioctl(NULL, commands[c], NULL), root_only && host_uid ? -EPERM : -EOPNOTSUPP);
            CHECK_EQ(unrelated_calls, previous + (root_only && host_uid ? 0 : 1));
        }
        const u32 denied[] = {10000, 10001, 10002, 10004, 10005, 10006, 10007, 11253, 11254, 11255, 19999};
        struct file session = { .su_session = true };
        for (unsigned i = 0; i < ARRAY_SIZE(denied); i++) {
            host_uid = denied[i]; unsigned previous = unrelated_calls;
            CHECK_EQ(ksu_supercall_handle_ioctl(&session, commands[c], NULL), -EPERM);
            CHECK_EQ(unrelated_calls, previous);
        }
        host_uid = 0;
        CHECK_EQ(ksu_supercall_handle_ioctl(NULL, commands[c] ^ (1U << _IOC_SIZESHIFT), NULL), -ENOTTY);
    }
    for (unsigned i = 0; ksu_ioctl_handlers[i].handler; i++) {
        const struct ksu_ioctl_cmd_map *entry = &ksu_ioctl_handlers[i];
        if (entry->name && strstr(entry->name, "DYNAMIC") && strstr(entry->name, "SET")) {
            CHECK(entry->perm_check == only_root); CHECK(!entry->allow_su_session);
            host_uid = 10003; CHECK_EQ(ksu_supercall_handle_ioctl(NULL, entry->cmd, NULL), -EPERM);
        }
    }
    CHECK_EQ(missing, 0);
}
static void case_lookup(unsigned fault_mode)
{
    char overlong[KSYM_NAME_LEN + 1]; memset(overlong, 'x', sizeof(overlong)); overlong[KSYM_NAME_LEN] = 0;
    const char *strings[] = { "known", "missing", "", overlong, "second" };
    u64 names[5], addrs[5];
    for (unsigned i = 0; i < 5; i++) { names[i] = (uintptr_t)strings[i]; addrs[i] = UINT64_MAX; }
    struct ksu_lookup_symbols_cmd cmd = { .names = (uintptr_t)names, .addrs = (uintptr_t)addrs, .count = 5 };
    struct ksu_lookup_symbols_cmd original = cmd;
    if (fault_mode >= 2) {
        if (fault_mode == 2) cmd.names = 0; else cmd.addrs = 0;
        alloc_fail_after = 0;
        cmd.count = 0; CHECK_EQ(do_lookup_symbols(&cmd), -EINVAL);
        cmd.count = 1025; CHECK_EQ(do_lookup_symbols(&cmd), -EINVAL);
        cmd.count = 5; cmd.flags = 1; CHECK_EQ(do_lookup_symbols(&cmd), -EINVAL); cmd.flags = 0;
        CHECK_EQ(do_lookup_symbols(&cmd), -EFAULT);
        alloc_fail_after = -1;
        return;
    }
    CHECK_EQ(ksu_supercall_handle_ioctl(NULL, KSU_IOCTL_LOOKUP_SYMBOLS, &cmd), 2);
    CHECK_EQ(addrs[0], 0xffff000012340000ULL); CHECK_EQ(addrs[4], 0xffff000023450000ULL);
    CHECK_EQ(addrs[1], 0); CHECK_EQ(addrs[2], 0); CHECK_EQ(addrs[3], 0);
    CHECK(!memcmp(&cmd, &original, sizeof(cmd)));
    if (!fault_mode) {
        cmd.count = 0; CHECK_EQ(do_lookup_symbols(&cmd), -EINVAL);
        cmd.count = 1025; CHECK_EQ(do_lookup_symbols(&cmd), -EINVAL);
        cmd.count = 5; cmd.flags = 1; CHECK_EQ(do_lookup_symbols(&cmd), -EINVAL); cmd.flags = 0;
        ksu_register_manager(10003, KSU_SIG_FINASU); host_uid = 10003;
        CHECK_EQ(ksu_supercall_handle_ioctl(NULL, KSU_IOCTL_LOOKUP_SYMBOLS, &cmd), -EPERM);
        struct file session = { .su_session = true };
        CHECK_EQ(ksu_supercall_handle_ioctl(&session, KSU_IOCTL_LOOKUP_SYMBOLS, &cmd), -EPERM);
        host_uid = 0;
        u64 *many_names = calloc(1024, sizeof(u64)), *many_addrs = calloc(1024, sizeof(u64));
        CHECK(many_names && many_addrs);
        for (unsigned i = 0; i < 1024; i++) many_names[i] = (uintptr_t)(i % 2 ? "" : "known");
        cmd.names = (uintptr_t)many_names; cmd.addrs = (uintptr_t)many_addrs; cmd.count = 1024;
        CHECK_EQ(do_lookup_symbols(&cmd), 512);
        for (unsigned i = 0; i < 1024; i++) CHECK_EQ(many_addrs[i], i % 2 ? 0 : 0xffff000012340000ULL);
        free(many_names); free(many_addrs);
        return;
    }
    from_fault = true; CHECK_EQ(do_lookup_symbols(&cmd), -EFAULT); from_fault = false;
    get_fault = true; CHECK_EQ(do_lookup_symbols(&cmd), -EFAULT); get_fault = false;
    put_fault = true; CHECK_EQ(do_lookup_symbols(&cmd), -EFAULT); put_fault = false;
    string_fault = true; CHECK_EQ(do_lookup_symbols(&cmd), -EFAULT); string_fault = false;
    for (int i = 0; i <= 2; i++) {
        alloc_fail_after = i; CHECK_EQ(do_lookup_symbols(&cmd), -ENOMEM);
    }
    alloc_fail_after = -1; resolver_error = -EIO;
    CHECK_EQ(do_lookup_symbols(&cmd), -EIO); resolver_error = 0;
}
static void case_reply(unsigned command, size_t width)
{
    /* Large guard area records the actual copy width without hiding overwrites. */
    unsigned char guarded[512]; memset(guarded, 0xa5, sizeof(guarded));
    CHECK_EQ(ksu_supercall_handle_ioctl(NULL, command, guarded + 16), 0);
    CHECK_EQ(last_copy_size, width); CHECK(guarded[16]); CHECK(memchr(guarded + 16, 0, width));
    for (unsigned i = 0; i < 16; i++) CHECK_EQ(guarded[i], 0xa5);
    for (unsigned i = 16 + width; i < sizeof(guarded); i++) CHECK_EQ(guarded[i], 0xa5);
    to_fault = true; CHECK_EQ(ksu_supercall_handle_ioctl(NULL, command, guarded + 16), -EFAULT); to_fault = false;
}
static struct file load_fixture(const char *path)
{
    FILE *stream = fopen(path, "rb"); CHECK(stream);
    CHECK_EQ(fseek(stream, 0, SEEK_END), 0); long size = ftell(stream); CHECK(size >= 0);
    rewind(stream); unsigned char *data = size ? malloc(size) : NULL; CHECK(!size || data);
    if (size) CHECK_EQ(fread(data, 1, size, stream), size);
    CHECK_EQ(fclose(stream), 0);
    return (struct file){ .inode = { .size = size }, .data = data, .size = size, .refs = 1 };
}
int main(int argc, char **argv)
{
    CHECK(argc >= 2);
    const char *mode = argv[1];
    if (!strcmp(mode, "asan-control")) {
        unsigned char *p = malloc(8); CHECK(p); free(p);
        volatile unsigned char value = *p; return value;
    }
    if (!strcmp(mode, "ubsan-control")) { volatile int x = INT_MAX; return x + 1; }
    if (!strcmp(mode, "zip") || !strcmp(mode, "apk") || !strcmp(mode, "range")) {
        CHECK(argc >= 3); struct file apk = load_fixture(argv[2]); apk_file = &apk;
        if (!strcmp(mode, "zip")) {
            loff_t offset = -1, end = -1;
            bool valid = get_zip_central_directory(&apk, apk.inode.size, &offset, &end);
            printf("%d %lld %lld\n", valid, (long long)offset, (long long)end);
        } else {
            CHECK(argc >= 5); struct file exe = load_fixture(argv[3]);
            struct file extracted = {0}; bool present = strcmp(argv[4], "-") != 0;
            if (present) { extracted = load_fixture(argv[4]); extracted_file = &extracted; }
            bool matched;
            if (!strcmp(mode, "range")) {
                CHECK(argc >= 7);
                matched = executable_matches_range(&apk, strtoll(argv[5], NULL, 10), strtoll(argv[6], NULL, 10), &exe);
            } else {
                short_read = argc > 5 && !strcmp(argv[5], "short");
                alloc_fail_after = argc > 5 && !strcmp(argv[5], "nomem") ? 0 : -1;
                if (argc > 5 && !strncmp(argv[5], "alloc", 5)) alloc_fail_after = atoi(argv[5] + 5);
                inflate_init_fault = argc > 5 && !strcmp(argv[5], "inflate-init-fault");
                matched = ksu_manager_apk_matches_executable("/data/app/test/base.apk", &exe);
            }
            printf("%d\n", matched);
            CHECK_EQ(exe.refs, 1); free(exe.data);
            if (present) { CHECK_EQ(extracted.refs, 1); free(extracted.data); }
        }
        CHECK_EQ(apk.refs, 1); CHECK_EQ(native_metadata_boundary_calls, 0); free(apk.data); return 0;
    }
    if (!strcmp(mode, "lifecycle")) case_lifecycle();
    else if (!strcmp(mode, "appid-width")) case_appid_width();
    else if (!strcmp(mode, "dynamic-denied")) case_dynamic_denied();
    else if (!strcmp(mode, "version-metadata")) case_version_metadata();
    else if (!strcmp(mode, "uapi-metadata")) case_uapi_metadata();
    else if (!strcmp(mode, "uapi-metadata-rcu")) case_uapi_metadata_rcu();
    else if (!strcmp(mode, "census")) case_census();
    else if (!strcmp(mode, "rcu")) case_rcu();
    else if (!strcmp(mode, "identity")) case_identity();
    else if (!strcmp(mode, "info")) case_info();
    else if (!strcmp(mode, "feature-translation")) case_feature_translation();
#ifdef HOST_FEATURE_TESTS
    else if (!strcmp(mode, "features")) case_features();
    else if (!strcmp(mode, "avc")) case_avc();
    else if (!strcmp(mode, "avc-sids")) case_avc_sids();
    else if (!strcmp(mode, "sparse-slots")) case_sparse_slots();
    else if (!strcmp(mode, "capability-routing")) case_capability_routing();
    else if (!strcmp(mode, "force-parser")) case_force_parser();
    else if (!strcmp(mode, "policy-audit")) case_policy_audit();
#endif
    else if (!strcmp(mode, "audit-target")) case_audit_target();
    else if (!strcmp(mode, "audit-full")) case_audit_full();
    else if (!strcmp(mode, "audit-disabled")) case_audit_disabled();
    else if (!strcmp(mode, "audit-invalid-sids")) case_audit_invalid_sids();
    else if (!strcmp(mode, "abi")) case_abi();
    else if (!strcmp(mode, "controller-abi")) case_controller_abi();
    else if (!strcmp(mode, "controller-map")) case_controller_map();
    else if (!strcmp(mode, "lookup")) case_lookup(0);
    else if (!strcmp(mode, "lookup-faults")) case_lookup(1);
    else if (!strcmp(mode, "lookup-null-names")) case_lookup(2);
    else if (!strcmp(mode, "lookup-null-addrs")) case_lookup(3);
    else if (!strcmp(mode, "legacy-hook")) case_reply(0x80004b62U, 16);
    else if (!strcmp(mode, "legacy-version")) case_reply(0x80004b63U, 32);
    else if (!strcmp(mode, "fina-version")) case_reply(0x80404b1dU, 64);
    else if (!strcmp(mode, "native-strings")) {
        case_reply(KSU_IOCTL_HOOK_TYPE, 32); case_reply(KSU_IOCTL_GET_FULL_VERSION, 255);
    } else { fprintf(stderr, "Unknown case: %s\n", mode); return 2; }
    reset_registry(); CHECK_EQ(rcu_depth, 0); CHECK_EQ(deferred_count, 0);
#ifndef HOST_FEATURE_TESTS
    CHECK_EQ(unused_feature_api_calls, 0);
#endif
    CHECK_EQ(native_metadata_boundary_calls, 0);
    printf("PASS %s (%u assertions)\n", mode, checks); return 0;
}
"""


class HostRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "posix":
            raise RuntimeError("Run this script through native WSL, not Windows Python")
        cls.kernel = Path(OPTIONS.kernel).resolve()
        cls.clang = Path(OPTIONS.clang).resolve()
        version = subprocess.run([str(cls.clang), "--version"], text=True, capture_output=True, check=True).stdout
        if not all(marker in version for marker in ("Android", "clang version 17.", "r487747c")):
            raise RuntimeError("Only Google AOSP Clang17 r487747c is allowed")
        cls.temp_context = tempfile.TemporaryDirectory(prefix="ksu-manager-host-", dir="/root")
        cls.addClassCleanup(cls.temp_context.cleanup)
        cls.temp = Path(cls.temp_context.name)
        cls.sources = {name: (cls.kernel / name).read_text(encoding="utf-8") for name in SOURCES}
        # Snapshot newly integrated, namespaced controller headers as well.
        cls.controller_headers = set(name for name in SOURCES if name.startswith("kernel/feature/finasu"))
        for owner in ("kernel/supercall/dispatch.c", "kernel/policy/feature.c", "kernel/manager/manager.c"):
            for include in re.findall(r'^\s*#include\s+"(feature/finasu[^"\n]+\.h)"', cls.sources[owner], re.M):
                name = "kernel/" + include
                cls.controller_headers.add(name)
                if name not in cls.sources:
                    cls.sources[name] = (cls.kernel / name).read_text(encoding="utf-8")
        cls.env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        cls.base_flags = ["-std=gnu11", "-O1", "-g", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie", "-Wall", "-Wextra", "-Werror",
                          "-Wno-unused-function", "-Wno-unused-variable", "-Wno-unused-parameter", "-Wno-unused-but-set-variable",
                          "-Wno-sign-compare"]
        cls.sanitize_flags = []
        cls.sanitizers = "none"
        probe = cls.temp / "sanitizer-probe.c"
        probe.write_text("int main(void) { return 0; }\n", encoding="ascii")
        diagnostics = []
        for names in ("address,undefined", "address", "undefined"):
            flags = [f"-fsanitize={names}", "-fno-sanitize-recover=all"]
            binary = cls.temp / "sanitizer-probe"
            build = subprocess.run([str(cls.clang), *cls.base_flags, *flags, str(probe), "-o", str(binary)], capture_output=True, text=True)
            run = subprocess.run([str(binary)], capture_output=True, text=True, env=cls.env) if not build.returncode else build
            if not run.returncode:
                cls.sanitize_flags = flags
                cls.sanitizers = names
                break
            diagnostics.append(f"{names}: {(build.stderr + run.stderr).strip()[:500]}")
        print(f"\nCompiler: {version.splitlines()[0]}", flush=True)
        print(f"Sanitizers: {cls.sanitizers}", flush=True)
        for diagnostic in diagnostics:
            print(f"Sanitizer probe unavailable: {diagnostic}", flush=True)
        print("Sources: read-only snapshot; temporary fixtures/harnesses under /root", flush=True)
        for name, text in cls.sources.items():
            print(f"  {name}: sha256 {hashlib.sha256(text.encode()).hexdigest()[:16]}", flush=True)
        print("Dynamic authorization/version and controller implementations are programmed boundary spies, not backend verification", flush=True)
        cls.builtin_defines = ["-DCONFIG_KSU=1", "-DCONFIG_SECURITY_SELINUX=1", "-DCONFIG_KSU_MULTI_MANAGER_SUPPORT",
                               "-DCONFIG_KSU_SUSFS", "-DCONFIG_KSU_MANUAL_HOOK"]
        cls.harness = cls.make_harness(with_features=True)
        cls.core_harness = cls.make_harness(with_features=False)
        cls.binary = cls.compile("manager-host", cls.core_harness, cls.builtin_defines)
        cls.feature_binary, cls.feature_compile_error = None, None

    @classmethod
    def whole(cls, name):
        text = cls.sources[name]
        return source_fragment(cls.kernel / name, text) + without_includes(text)

    @classmethod
    def function(cls, name, function):
        text = cls.sources[name]
        start, body = extract_function(text, function)
        return source_fragment(cls.kernel / name, text, start) + body

    @classmethod
    def definition(cls, name, expression):
        text = cls.sources[name]
        start, body = extract_block(text, expression)
        return source_fragment(cls.kernel / name, text, start) + body

    @classmethod
    def make_harness(cls, with_features):
        headers = ("uapi/app_profile.h", "uapi/feature.h", "uapi/selinux.h", "kernel/manager/manager_sign.h",
                   "kernel/manager/manager_identity.h", "kernel/manager/throne_tracker.h",
                   "kernel/manager/apk_sign.h", "kernel/policy/feature.h")
        source = HOST_STUBS + ZLIB_SHIM + "".join(cls.whole(name) for name in headers)
        # Activate the actual API declarations, not handwritten copies of them.
        source += "\n#define __KERNEL__\n" + "".join(cls.whole(name) for name in sorted(cls.controller_headers)) + "\n#undef __KERNEL__\n"
        source += cls.whole("uapi/supercall.h") + cls.whole("kernel/supercall/supercall.h")
        source += DYNAMIC_BOUNDARY_SPIES
        source += cls.whole("kernel/manager/manager.c")
        if with_features:
            source += cls.whole("kernel/policy/feature.c")
        else:
            policy = cls.sources["kernel/policy/feature.c"]
            key = re.search(r"^DEFINE_STATIC_KEY_FALSE\(ksu_avc_log_spoof_full_enabled\);", policy, re.M)
            if not key:
                raise ValueError("Missing actual AVC full-mode key definition")
            source += "\n#ifdef CONFIG_KSU_SUSFS\n" + source_fragment(cls.kernel / "kernel/policy/feature.c", policy, key.start()) + key[0] + "\n#endif\n"
            # These boundaries must never be called by independent core cases.
            source += '\n#line 1 "unused-core-feature-spies.c"\n'
            source += "static unsigned unused_feature_api_calls;\n"
            source += "int ksu_get_feature(u32 id, u64 *value, bool *supported) { (void)id; unused_feature_api_calls++; *value = 0; *supported = false; return -EOPNOTSUPP; }\n"
            source += "int ksu_set_feature(u32 id, u64 value) { (void)id; (void)value; unused_feature_api_calls++; return -EOPNOTSUPP; }\n"
            source += "bool ksu_feature_is_forced(u32 id) { (void)id; unused_feature_api_calls++; return false; }\n"
        source += "\nstruct path { struct vfsmount *mnt; struct dentry *dentry; };\n"
        source += cls.definition("../security/selinux/include/avc.h", r"^struct selinux_audit_data\s*\{")
        source += cls.definition("../include/linux/lsm_audit.h", r"^struct common_audit_data\s*\{")
        source += AUDIT_STUBS + cls.function("../security/selinux/avc.c", "slow_avc_audit")
        apk = "kernel/manager/apk_sign.c"
        for name in ("zip_entry_header", "zip_central_header", "zip_eocd"):
            source += cls.definition(apk, r"^struct " + name + r"\s*\{")
        for name in ("read_exact", "get_zip_central_directory", "executable_matches_range", "executable_matches_deflated_range"):
            source += cls.function(apk, name)
        # Keep the REAL scanner; ELF metadata is a separate, asserted-unused seam.
        _, metadata = extract_function(cls.sources[apk], "native_payload_uapi")
        signature = metadata[:mask_c(metadata).index("{")]
        source += '\n#line 1 "unused-native-metadata-boundary-spy.c"\nstatic unsigned native_metadata_boundary_calls;\n'
        source += signature + "{ native_metadata_boundary_calls++; return -ENODATA; }\n"
        source += cls.function(apk, "scan_apk_native_payloads")
        source += cls.function(apk, "ksu_manager_apk_matches_executable")
        dispatch = "kernel/supercall/dispatch.c"
        table = cls.definition(dispatch, r"^static const struct ksu_ioctl_cmd_map ksu_ioctl_handlers\[\]\s*=\s*\{")
        source += cls.whole("kernel/supercall/perm.c")
        wanted = {"get_caller_manager_info", "get_caller_signature_index", "do_get_info", "do_get_info_legacy", "do_get_manager_appid",
                  "translate_feature_id_for_caller", "do_get_feature", "do_set_feature", "do_get_managers", "do_lookup_symbols"}
        # Reply helpers are extracted too, including pending dedicated legacy handlers.
        candidates = set(re.findall(r"\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{", mask_c(cls.sources[dispatch])))
        wanted.update(name for name in candidates if re.search(r"version|hook_(?:type|mode)", name))
        permissions = set(re.findall(r"\.perm_check\s*=\s*(\w+)", table)) - {"NULL"}
        wanted.update(permissions & candidates)
        definitions = [(extract_function(cls.sources[dispatch], name)[0], name) for name in wanted]
        for _, name in sorted(definitions):
            source += cls.function(dispatch, name)
        handlers = set(re.findall(r"\.handler\s*=\s*(\w+)", table)) - wanted - {"NULL"}
        # Unrelated commands retain the real map but not out-of-scope backends.
        source += '\n#line 1 "unrelated-handler-stubs.c"\n'
        source += "static unsigned unrelated_calls;\n"
        for handler in sorted(handlers):
            source += f"int {handler}(void *arg) {{ (void)arg; unrelated_calls++; return -EOPNOTSUPP; }}\n"
        source += table + cls.function(dispatch, "ksu_supercall_handle_ioctl") + HOST_CASES
        return source

    @classmethod
    def compile(cls, name, source, defines=()):
        c_file, binary = cls.temp / f"{name}.c", cls.temp / name
        c_file.write_text(source, encoding="utf-8")
        command = [str(cls.clang), *cls.base_flags, *cls.sanitize_flags, *defines, str(c_file), "-o", str(binary), "-lz"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise AssertionError(f"Clang failed ({name}):\n{result.stdout}{result.stderr}")
        return binary

    @classmethod
    def feature_executable(cls):
        if cls.feature_binary is None and cls.feature_compile_error is None:
            try:
                cls.feature_binary = cls.compile("manager-features", cls.harness, [*cls.builtin_defines, "-DHOST_FEATURE_TESTS"])
            except AssertionError as error:
                cls.feature_compile_error = str(error)
                print("\nFeature harness failed to compile; independent real-function cases still run:\n" + str(error), flush=True)
        return cls.feature_binary

    def run_host(self, *arguments, binary=None):
        feature_cases = {"features", "avc", "avc-sids", "sparse-slots", "capability-routing", "force-parser", "policy-audit"}
        if binary is None and arguments and arguments[0] in feature_cases:
            binary = self.feature_executable()
            if self.feature_compile_error is not None:
                self.fail("Real feature.c did not compile; see the Clang diagnostic printed above")
        result = subprocess.run([str(binary or self.binary), *map(str, arguments)], capture_output=True, text=True, env=self.env, timeout=30)
        label = arguments[0] if arguments else Path(binary or self.binary).name
        self.assertEqual(result.returncode, 0, f"Host case {label} failed:\n{result.stdout}{result.stderr}")
        return result.stdout.strip()

    def fixture(self, name, data):
        path = self.temp / name
        path.write_bytes(data)
        return path

    @staticmethod
    def make_zip(entries, comment=b"", descriptor=False):
        class NonSeekable(io.BytesIO):
            def seekable(self):
                return False

            def seek(self, *args):
                raise io.UnsupportedOperation("data-descriptor fixture")

        stream = NonSeekable() if descriptor else io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.comment = comment
            for name, data, compression in entries:
                info = zipfile.ZipInfo(name)
                info.compress_type = compression
                info.extra = struct.pack("<HH4s", 0xCAFE, 4, b"test")
                info.comment = b"entry comment"
                archive.writestr(info, data)
        return stream.getvalue()

    def match_apk(self, apk, executable, expected, extracted=None, mode=""):
        apk_path = self.fixture("fixture.apk", apk)
        exe_path = self.fixture("fixture-executable", executable)
        fallback = self.fixture("fixture-extracted", extracted) if extracted is not None else "-"
        output = self.run_host("apk", apk_path, exe_path, fallback, mode)
        self.assertEqual(output, str(int(expected)), "Executable identity did not match the expected fixture result")

    def test_certificate_pins_and_designated_table_variants(self):
        header = self.sources["kernel/manager/manager_sign.h"]
        enums = {name: int(value) for name, value in re.findall(r"KSU_SIG_(\w+)\s*=\s*(\d+)", header)}
        self.assertEqual(enums, {name: index for name, index, _, _ in CERTIFICATES})
        sizes = {name: int(value, 0) for name, value in re.findall(r"#define EXPECTED_SIZE_(\w+)\s+(0x[\da-fA-F]+|\d+)", header)}
        hashes = dict(re.findall(r'#define EXPECTED_HASH_(\w+)\s+"([^"]+)"', header))
        self.assertEqual(sizes, {name: size for name, _, size, _ in CERTIFICATES}, "Stale or changed certificate-size definitions")
        self.assertEqual(hashes, {name: digest for name, _, _, digest in CERTIFICATES}, "Stale or changed certificate hashes")
        table = self.definition("kernel/manager/apk_sign.c", r"^static apk_sign_key_t apk_sign_keys\[\]\s*=\s*\{")
        self.assertEqual(re.findall(r"\[(KSU_SIG_\w+)\]\s*=", table), [f"KSU_SIG_{name}" for name, _, _, _ in CERTIFICATES])
        for multi, custom, pr in ((False, False, False), (False, True, True), (True, False, False),
                                  (True, True, False), (True, False, True), (True, True, True)):
            with self.subTest(multi=multi, custom=custom, pr=pr):
                defines = ["-DCONFIG_KSU_MULTI_MANAGER_SUPPORT"] if multi else []
                if custom:
                    defines += ["-DEXPECTED_SIZE=0x321", '-DEXPECTED_HASH="' + "1" * 64 + '"']
                if pr:
                    defines += ["-DEXPECTED_PR_BUILD_SIZE=0x322", '-DEXPECTED_PR_BUILD_HASH="' + "2" * 64 + '"']
                expected = 8 + custom + pr if multi else 1
                body = f"int main(void) {{ CHECK_EQ(ARRAY_SIZE(apk_sign_keys), {expected}); CHECK(ARRAY_SIZE(apk_sign_keys) < 252);\n"
                for name, index, size, digest in CERTIFICATES:
                    body += f"CHECK_EQ(KSU_SIG_{name}, {index});\n"
                    if multi or not index:
                        body += f'CHECK_EQ(apk_sign_keys[{index}].size, {size}); CHECK(!strcmp(apk_sign_keys[{index}].sha256, "{digest}"));\n'
                for index, enabled, size, digit in ((8, multi and custom, 0x321, "1"), (8 + custom, multi and pr, 0x322, "2")):
                    if enabled:
                        body += f'CHECK_EQ(apk_sign_keys[{index}].size, {size}); CHECK(!strcmp(apk_sign_keys[{index}].sha256, "{digit * 64}"));\n'
                body += 'puts("PASS certificate table"); return 0; }\n'
                prefix = HOST_STUBS[:HOST_STUBS.index("/* Fault injection")]
                source = prefix + self.whole("kernel/manager/manager_sign.h") + table + body
                binary = self.compile(f"cert-{int(multi)}-{int(custom)}-{int(pr)}", source, defines)
                self.run_host(binary=binary)

    def test_manager_selection_removal_reinstall_and_specials(self):
        self.run_host("lifecycle")

    def test_full_width_appid_75536_cannot_alias_10000(self):
        self.run_host("appid-width")

    def test_denied_252_central_permissions_and_raw_duplicate_preservation(self):
        self.run_host("dynamic-denied")

    def test_version_metadata_override_only_for_live_fina_managers(self):
        self.run_host("version-metadata")

    def test_detected_manager_and_daemon_uapi_metadata_and_explicit_precedence(self):
        self.run_host("uapi-metadata")

    def test_manager_uapi_metadata_preserves_duplicates_and_survives_rcu_unlock(self):
        self.run_host("uapi-metadata-rcu")

    def test_manager_zero_count_truncation_and_copy_faults(self):
        self.run_host("census")

    def test_rcu_signature_and_snapshot_survive_removal_at_unlock(self):
        self.run_host("rcu")

    def test_caller_uid_vs_pinned_root_executable(self):
        self.run_host("identity")
        for name in ("get_caller_signature_index", "get_caller_manager_info"):
            _, body = extract_function(self.sources["kernel/supercall/dispatch.c"], name)
            self.assertNotRegex(mask_c(body), r"current\s*->\s*comm|ksu_last_manager_appid|ksu_get_manager_appid|MOV|RET")

    def test_get_info_family_mapping_explicit_requests_and_native_default(self):
        self.run_host("info")

    def test_feature_routing_preserves_ids_and_uses_translated_forced_flag(self):
        self.run_host("features")

    def test_actual_family_feature_id_matrix_and_fast_root_paths(self):
        self.run_host("feature-translation")

    def test_sparse_avc_boolean_backend(self):
        self.run_host("avc")

    def test_sparse_slots_are_bounded_and_ids_are_unique(self):
        self.run_host("sparse-slots")

    def test_avc_modes_reject_zero_equal_sids_and_invalid_values(self):
        self.run_host("avc-sids")

    def test_fina_capability_read_only_fixture_routing(self):
        self.run_host("capability-routing")

    def test_forced_sparse_parser_aliases_conflicts_and_pending_readiness(self):
        self.run_host("force-parser")

    def test_sparse_avc_without_susfs(self):
        defines = [define for define in self.builtin_defines if define != "-DCONFIG_KSU_SUSFS"]
        binary = self.compile("manager-no-susfs", self.harness, [*defines, "-DHOST_FEATURE_TESTS"])
        self.run_host("avc", binary=binary)
        self.run_host("audit-disabled", binary=binary)

    def test_module_avc_is_target_only_and_full_handler_unavailable(self):
        defines = [define for define in self.builtin_defines if define != "-DCONFIG_KSU=1"]
        binary = self.compile("manager-module", self.harness, [*defines, "-DCONFIG_KSU=0", "-DMODULE", "-DHOST_FEATURE_TESTS"])
        self.run_host("avc", binary=binary)
        self.run_host("audit-full", binary=binary)
        self.run_host("info", binary=binary)

    def test_module_slow_audit_never_rewrites_source_metadata(self):
        defines = [define for define in self.builtin_defines if define != "-DCONFIG_KSU=1"]
        binary = self.compile("audit-module", self.core_harness, [*defines, "-DCONFIG_KSU=0", "-DMODULE"])
        self.run_host("audit-full", binary=binary)
        self.run_host("audit-disabled", binary=binary)

    def test_real_slow_audit_target_only_metadata(self):
        self.run_host("audit-target")

    def test_real_slow_audit_full_source_and_target_metadata(self):
        self.run_host("audit-full")

    def test_real_slow_audit_disabled_stale_source_key_and_invalid_classes(self):
        self.run_host("audit-disabled")

    def test_real_slow_audit_ignores_zero_and_equal_cached_sids(self):
        self.run_host("audit-invalid-sids")

    def test_audit_post_callback_has_no_independent_text_spoof(self):
        _, body = extract_function(self.sources["../security/selinux/avc.c"], "avc_audit_post_callback")
        self.assertNotRegex(mask_c(body), r"\bsusfs_\w+|\bksu_avc_log_spoof_full_enabled\b")
        self.assertNotIn('"u:r:priv_app:', body)

    def test_actual_policy_setters_drive_actual_audit_metadata(self):
        self.run_host("policy-audit")

    def test_ioctl_layouts_full_command_map_and_lookup_registration(self):
        self.run_host("abi")

    def test_fina_controller_wire_layouts_and_exact_commands(self):
        self.run_host("controller-abi")

    def test_fina_controller_map_registration_auth_and_root_dynamic_setters(self):
        self.run_host("controller-map")

    def test_lookup_symbol_limit_root_permissions_and_missing_names(self):
        self.run_host("lookup")

    def test_lookup_copy_allocation_and_resolver_faults(self):
        self.run_host("lookup-faults")

    def test_lookup_null_names_returns_efault_without_undefined_arithmetic(self):
        self.run_host("lookup-null-names")

    def test_lookup_null_addrs_returns_efault_without_undefined_arithmetic(self):
        self.run_host("lookup-null-addrs")

    def test_legacy_hook_reply_is_exactly_16_bytes(self):
        self.run_host("legacy-hook")

    def test_legacy_version_reply_is_exactly_32_bytes(self):
        self.run_host("legacy-version")

    def test_fina_sized_full_version_reply_is_exactly_64_bytes(self):
        self.run_host("fina-version")

    def test_native_hook_and_full_version_reply_widths(self):
        self.run_host("native-strings")

    def test_sanitizer_negative_controls(self):
        for sanitizer, mode, marker in (("address", "asan-control", "heap-use-after-free"),
                                         ("undefined", "ubsan-control", "signed integer overflow")):
            with self.subTest(sanitizer=sanitizer):
                if sanitizer not in self.sanitizers:
                    continue
                result = subprocess.run([str(self.binary), mode], capture_output=True, text=True, env=self.env, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(marker, result.stderr, "Sanitizer must detect its deliberately invalid host-only control")
        if self.sanitizers == "none":
            self.skipTest("AOSP compiler sanitizer runtimes unavailable; tests ran unsanitized")

    def test_zip_stored_exact_bytes_sizes_and_later_pages(self):
        for size in (1, 4095, 4096, 4097, 8192, 8193, 16387):
            payload = bytes((i * 31 + 7) % 256 for i in range(size))
            apk = self.make_zip([("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_STORED)])
            with self.subTest(size=size):
                self.match_apk(apk, payload, True)
                self.match_apk(apk, payload + b"x", False)
                self.match_apk(apk, payload[:-1], False)
                changed = bytearray(payload); changed[-1] ^= 0xFF
                self.match_apk(apk, changed, False)

    def test_zip_unrelated_libraries_and_entry_order(self):
        payload = b"\x7fELF" + b"real daemon" * 1100
        different = b"\x7fELF" + b"other code!" * 1100
        unrelated = [("classes.dex", payload, zipfile.ZIP_STORED),
                     ("lib/armeabi-v7a/libksud.so", payload, zipfile.ZIP_STORED),
                     ("lib/arm64-v8a/libother.so", different, zipfile.ZIP_STORED)]
        self.match_apk(self.make_zip(unrelated), payload, False)
        daemon = ("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_STORED)
        self.match_apk(self.make_zip(unrelated + [daemon]), payload, True)
        self.match_apk(self.make_zip([daemon] + unrelated), payload, True)

    def test_zip_deflated_payload_ignores_untrusted_extracted_file(self):
        payload = b"\x7fELF" + b"compressed daemon payload" * 700
        apk = self.make_zip([("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_DEFLATED)])
        self.match_apk(apk, payload, True)
        self.match_apk(apk, payload, True, extracted=payload)
        self.match_apk(apk, payload, True, extracted=payload[:-1])
        changed = bytearray(payload); changed[5000] ^= 1
        self.match_apk(apk, payload, True, extracted=changed)
        self.match_apk(apk, changed, False, extracted=changed)

    def test_zip_renamed_jni_libraries_stored_and_deflated(self):
        payload = b"\x7fELF" + b"hidden manager daemon" * 800
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                apk = self.make_zip([("lib/arm64-v8a/libq7p9r2x.so", payload, compression)])
                self.match_apk(apk, payload, True)

    def test_zip_deflate_stream_integrity_and_multiple_input_chunks(self):
        payload = b"\x7fELF" + hashlib.shake_256(b"deterministic incompressible daemon").digest(25000)
        apk = self.make_zip([("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_DEFLATED)])
        self.match_apk(apk, payload, True)
        eocd = len(apk) - 22
        central = struct.unpack_from("<I", apk, eocd + 16)[0]
        data_offset = 30 + struct.unpack_from("<H", apk, 26)[0] + struct.unpack_from("<H", apk, 28)[0]
        compressed_size = struct.unpack_from("<I", apk, central + 20)[0]
        self.assertGreater(compressed_size, 4096)
        cases = []
        for delta in (-1, 1):
            changed = bytearray(apk)
            struct.pack_into("<I", changed, central + 20, compressed_size + delta)
            cases.append((f"compressed-length-{delta}", changed))
        for offset in (data_offset, data_offset + 5000, data_offset + compressed_size - 1):
            changed = bytearray(apk); changed[offset] ^= 0xFF
            cases.append((f"stream-byte-{offset}", changed))
        changed = bytearray(payload); changed[8193] ^= 1
        self.match_apk(apk, changed, False)
        self.match_apk(apk, payload[:-1], False)
        for name, corrupt in cases:
            with self.subTest(case=name):
                self.match_apk(corrupt, payload, False)

    def test_zip_bit3_data_descriptors(self):
        payload = b"\x7fELF" + b"descriptor payload" * 600
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                apk = self.make_zip([("lib/arm64-v8a/libksud.so", payload, compression)], descriptor=True)
                self.assertTrue(struct.unpack_from("<H", apk, 6)[0] & 8)
                self.match_apk(apk, payload, True)
                if compression == zipfile.ZIP_DEFLATED:
                    self.match_apk(apk, payload, True, extracted=payload)

    def test_zip_normal_maximum_and_embedded_magic_comments(self):
        payload = b"comment fixture" * 500
        for comment in (b"", b"normal APK comment", b"APK PK\x05\x06 comment", b"x" * 65535):
            with self.subTest(comment_length=len(comment)):
                apk = self.make_zip([("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_STORED)], comment=comment)
                path = self.fixture("comment.apk", apk)
                valid, offset, end = map(int, self.run_host("zip", path).split())
                eocd = len(apk) - 22 - len(comment)
                self.assertEqual(valid, 1)
                self.assertEqual(offset, struct.unpack_from("<I", apk, eocd + 16)[0])
                self.assertEqual(end, eocd)
                self.match_apk(apk, payload, True)

    def corrupt_zip_cases(self, apk):
        central, eocd = apk.index(b"PK\x01\x02"), len(apk) - 22
        cases = [("missing-eocd", apk[:-22]), ("tiny", b"PK"), ("empty", b"")]
        patches = (
            ("central-offset", eocd + 16, "I", len(apk) + 100),
            ("central-length", eocd + 12, "I", len(apk) + 100),
            ("multi-disk", eocd + 4, "H", 1),
            ("central-disk", eocd + 6, "H", 1),
            ("entry-count", eocd + 8, "H", 2),
            ("comment-length", eocd + 20, "H", 1),
            ("central-signature", central, "I", 0),
            ("central-name-length", central + 28, "H", 65535),
            ("central-extra-length", central + 30, "H", 65535),
            ("central-comment-length", central + 32, "H", 65535),
            ("local-offset", central + 42, "I", 0xFFFFFFF0),
            ("compressed-length", central + 20, "I", 0xFFFFFFFF),
            ("uncompressed-length", central + 24, "I", 0xFFFFFFFF),
            ("local-signature", 0, "I", 0),
            ("local-name-length", 26, "H", 1),
            ("local-extra-length", 28, "H", 65535),
            ("central-encrypted", central + 8, "H", 1),
            ("local-encrypted", 6, "H", 1),
            ("local-compression", 8, "H", 8),
        )
        for name, offset, fmt, value in patches:
            changed = bytearray(apk); struct.pack_into("<" + fmt, changed, offset, value)
            cases.append((name, bytes(changed)))
        changed = bytearray(apk); changed[30] ^= 1
        cases.append(("local-name-content", bytes(changed)))
        return cases

    def test_zip_corrupt_offsets_lengths_headers_and_truncation(self):
        payload = b"\x7fELF" + b"offset boundary fixture" * 500
        apk = self.make_zip([("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_STORED)])
        for name, corrupt in self.corrupt_zip_cases(apk):
            with self.subTest(case=name):
                self.match_apk(corrupt, payload, False)

    def test_zip_fallback_does_not_accept_absent_or_corrupt_daemon_entry(self):
        payload = b"\x7fELF" + b"fail closed fixture" * 500
        unrelated = self.make_zip([("classes.dex", payload, zipfile.ZIP_STORED)])
        with self.subTest(case="no-daemon-entry"):
            self.match_apk(unrelated, payload, False, extracted=payload)
        apk = self.make_zip([("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_STORED)])
        for name, corrupt in self.corrupt_zip_cases(apk):
            with self.subTest(case=name):
                self.match_apk(corrupt, payload, False, extracted=payload)

    def test_zip_short_reads_allocation_failure_and_empty_daemon(self):
        payload = b"\x7fELF" + b"I/O fault fixture" * 500
        apk = self.make_zip([("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_STORED)])
        self.match_apk(apk, payload, False, mode="short")
        self.match_apk(apk, payload, False, mode="nomem")
        deflated = self.make_zip([("lib/arm64-v8a/libksud.so", payload, zipfile.ZIP_DEFLATED)])
        self.match_apk(deflated, payload, False, mode="nomem")
        self.match_apk(deflated, payload, False, mode="alloc1")
        self.match_apk(deflated, payload, False, mode="inflate-init-fault")
        empty = self.make_zip([("lib/arm64-v8a/libksud.so", b"", zipfile.ZIP_STORED)])
        self.match_apk(empty, b"", False)

    def test_executable_range_bounds_and_complete_comparison(self):
        payload = b"\x7fELF" + b"range fixture" * 700
        raw = self.fixture("range-source", b"prefix!" + payload + b"suffix")
        exe = self.fixture("range-exe", payload)
        for start, size, expected in ((7, len(payload), True), (-1, len(payload), False),
                                      (7, 0, False), (7, -1, False), (8, len(payload), False),
                                      (7, len(payload) + 1, False), (len(payload) + 20, 1, False),
                                      (2**63 - 1, 1, False), (7, 2**63 - 1, False)):
            with self.subTest(start=start, size=size):
                self.assertEqual(self.run_host("range", raw, exe, "-", start, size), str(int(expected)))

    def test_zz_source_snapshot_did_not_change_during_run(self):
        changed = [name for name, text in self.sources.items() if (self.kernel / name).read_text(encoding="utf-8") != text]
        self.assertEqual(changed, [], "Main edited source during this snapshot run; rerun against the new source")


def main():
    global OPTIONS
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kernel", default=DEFAULT_KERNEL, help="Native KernelSU source directory")
    parser.add_argument("--clang", default=DEFAULT_CLANG, help="Google AOSP Clang17 r487747c executable")
    OPTIONS, test_args = parser.parse_known_args()
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
    result = unittest.main(argv=[sys.argv[0], *test_args], testRunner=runner, exit=False).result
    if hasattr(HostRegression, "temp"):
        if HostRegression.temp.exists():
            print(f"ERROR: temporary fixture context was not cleaned: {HostRegression.temp}", flush=True)
            return 1
        print("\nTemporary fixtures: cleaned", flush=True)
    print("\nCoverage limit: host stubs and system-zlib shim do not verify Android execution, real RCU concurrency, kernel zlib internals, APK cryptography, ELF ABI decoding, real policy/SID lookup/audit emission, or kernel boot. Controller/dynamic authorization/version backends, shell feature, daemon scanner and symbol resolver are spies; map/capability-fixture tests do not prove backend implementation or Kbuild integration. Legacy ZIP tests assert the ELF metadata boundary is unused.", flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
