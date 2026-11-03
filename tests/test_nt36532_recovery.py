"""Host behavior tests of extracted driver C, not hardware/kernel validation.

Run with Linux/WSL Python and cc (or NT36532_CC=clang). The bundled driver is
used by default; NT36532_SOURCE_DIR selects an alternate source directory.
Generated C and executables use temporary directories and are removed.
Run with python3 -B to avoid pycache. Kernel interfaces are mocked.
"""

import errno
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "driver"
EVENT_BASE = 0x123400


def masked_c(text):
    # Keep offsets/newlines, but ignore braces and fake declarations in comments/strings.
    return re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.S)


def extract_function(text, name, optional=False):
    masked = masked_c(text)
    match = re.search(r"(?m)^[ \t]*(?:static\s+)?(?:int32_t|int|void|bool|ssize_t)\s+"
                      + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", masked)
    if match is None:
        if optional:
            return ""
        raise AssertionError("Missing production function: " + name)
    depth = 1
    for end in range(match.end(), len(masked)):
        depth += (masked[end] == "{") - (masked[end] == "}")
        if depth == 0:
            return text[match.start():end + 1]
    raise AssertionError("Unbalanced production function: " + name)


def extract_defines(text, names):
    pieces = []
    for name in names:
        match = re.search(r"(?m)^[ \t]*#define[ \t]+" + name + r"\b[^\n]*", masked_c(text))
        if match is None:
            raise AssertionError("Missing production constant: " + name)
        pieces.append(text[match.start():match.end()])
    return "\n".join(pieces)


def health_support(text):
    declarations = []
    for kind, name in (("enum", "nvt_recovery_reason"), ("struct", "nvt_diagnostics")):
        match = re.search(kind + r"\s+" + name + r"\s*\{[^}]*\};", masked_c(text))
        if match:
            declarations.append(text[match.start():match.end()])
    if declarations:
        declarations.insert(0, extract_defines(text, ("NVT_HANDSHAKE_CONFIRM", "NVT_WDT_CONFIRM")))
        declarations.append("static struct nvt_diagnostics nvt_diag;")
    declarations.append("""
static bool nvt_health_armed, nvt_health_qualifying;
static unsigned int nvt_health_bad, nvt_health_recoveries, nvt_raw_users;
static unsigned long jiffies, nvt_health_cooldown_until, nvt_health_last_recovery, nvt_healthy_since;
""")
    # The v2 negative baseline predates this helper; never supply a replacement body.
    declarations.append(extract_function(text, "nvt_reset_health_evidence", optional=True))
    return "\n".join(declarations)


def extract_constants(header, commands):
    pieces = []
    for name in ("RST_COMPLETE_STATE", "SPI_EVENT_MAP", "NVT_SPI_RW"):
        match = re.search(r"typedef\s+enum\s*\{[^}]*\}\s*" + name + r"\s*;",
                          masked_c(header))
        if match is None:
            raise AssertionError("Missing production enum: " + name)
        pieces.append(header[match.start():match.end()])
    for text, names in ((header, ("NVT_PM_WAIT_BUS_RESUME_COMPLETE", "BOOT_UPDATE_FIRMWARE",
                                  "NVT_TOUCH_ESD_PROTECT", "NVT_SUPPORT_PEN",
                                  "NVT_TOUCH_WDT_RECOVERY", "DUMMY_BYTES", "NVT_TRANSFER_LEN",
                                  "NVT_READ_LEN", "NVT_XBUF_LEN", "SPI_READ_MASK", "SPI_WRITE_MASK",
                                  "BOOT_UPDATE_FIRMWARE_NAME_BOE", "BOOT_UPDATE_FIRMWARE_NAME_TIANMA",
                                  "USB_DETECT_IN", "USB_DETECT_OUT", "CMD_CHARGER_ON",
                                  "CMD_CHARGER_OFF", "TOUCH_DEFAULT_MAX_WIDTH",
                                  "TOUCH_DEFAULT_MAX_HEIGHT", "TOUCH_KEY_NUM")),
                        (commands, ("NVT_EXT_CMD", "NVT_EXT_CMD_EDGE_GRID_ZONE",
                                    "GAME_MODE_PALM_CMD", "GAME_MODE_NORMAL",
                                    "GAME_MODE_REMOVE", "GAME_MODE_ENHANCE",
                                    "NORMAL_MODE", "TEST_MODE_2"))):
        pieces.append(extract_defines(text, names))
    return "\n".join(pieces)


MOCKS = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/resource.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef unsigned long long u64;
#define ERESTARTSYS 512
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, value) ((x) = (value))
#define unlikely(x) (x)
#define NVT_LOG(...) ((void)0)
#define NVT_ERR(...) ((void)0)
#define pr_err_ratelimited(...) ((void)0)

struct mutex { int held; };
struct spi_device { int unused; };
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
struct workqueue_struct { int unused; };
struct nvt_ts_mem_map { uint32_t EVENT_BUF_ADDR, BASELINE_ADDR, BASELINE_BTN_ADDR; };
struct nvt_ts_data {
    struct mutex lock, xbuf_lock;
    struct spi_device *client;
    const struct nvt_ts_mem_map *mmap;
    int fw_update_stat;
    bool dev_pm_suspend, irq_enabled, pen_support;
    uint8_t fw_ver, x_num, y_num, max_button_num, x_gang_num, y_gang_num;
    uint8_t hw_crc, probe_state;
    uint8_t game_mode_state, pen_state, fw_pen_state;
    uint8_t *rbuf, *xbuf;
    uint16_t nvt_pid, abs_x_max, abs_y_max;
    struct delayed_work nvt_fwu_work, charger_notify_work;
    struct workqueue_struct *nvt_charger_notify_wq;
};
static struct nvt_ts_data device, *ts = &device;
static const struct nvt_ts_mem_map memory_map = { 0x123400, 0x234500, 0x345600 };
static uint8_t bTouchIsAwake;
static bool need_write_charger_state_flag;
static unsigned int nvt_fw_retries;
static unsigned long nvt_health_activity;
static int contacts, lock_errors, pages, writes, reads, argc_saved;
static int mock_fw_state;
static char **argv_saved;

static const char *option_text(const char *name, const char *fallback)
{
    size_t length = strlen(name);
    for (int i = 2; i < argc_saved; i++)
        if (!strncmp(argv_saved[i], name, length) && argv_saved[i][length] == '=')
            return argv_saved[i] + length + 1;
    return fallback;
}
static int option(const char *name, int fallback)
{ const char *s = option_text(name, NULL); return s ? (int)strtol(s, NULL, 0) : fallback; }
static unsigned long unsigned_option(const char *name, unsigned long fallback)
{ const char *s = option_text(name, NULL); return s ? strtoul(s, NULL, 0) : fallback; }

static struct event {
    const char *op;
    int held, pending, ready, value, length;
    uint8_t data[64];
} events[8192];
static unsigned int event_count;

static void record(const char *op, int value, const uint8_t *data, int length)
{
    if (event_count == 8192 || length > 64) {
        fputs("mock event budget exceeded\n", stderr);
        exit(2);
    }
    struct event *e = &events[event_count++];
    *e = (struct event){ .op = op, .held = ts->lock.held,
        .pending = need_write_charger_state_flag, .ready = ts->fw_update_stat,
        .value = value, .length = length };
    if (length) memcpy(e->data, data, length);
}

static void lockdep_assert_held(struct mutex *lock)
{
    if ((lock != &ts->lock && lock != &ts->xbuf_lock) || lock->held != 1) lock_errors++;
}

static int acquire(struct mutex *lock, int error)
{
    record(lock == &ts->xbuf_lock ? "xlock" : "lock", error, NULL, 0);
    if (error) return error;
    if ((lock != &ts->lock && lock != &ts->xbuf_lock) || lock->held) lock_errors++;
    lock->held++;
    if (lock == &ts->xbuf_lock) return 0;
    /* Inject a lifecycle change while the caller was waiting for ts->lock. */
    bTouchIsAwake = option("awake_at_lock", bTouchIsAwake);
    ts->fw_update_stat = option("ready_at_lock", ts->fw_update_stat);
    ts->dev_pm_suspend = option("suspended_at_lock", ts->dev_pm_suspend);
    return 0;
}
static int mutex_lock_interruptible(struct mutex *lock)
{ return acquire(lock, option("lock_error", 0)); }
static void mutex_lock(struct mutex *lock) { (void)acquire(lock, 0); }
static void mutex_unlock(struct mutex *lock)
{
    record(lock == &ts->xbuf_lock ? "xunlock" : "unlock", 0, NULL, 0);
    lockdep_assert_held(lock);
    lock->held--;
}

static int nvt_set_page(uint32_t address)
{
    record("page", address, NULL, 0);
    return ++pages == option("fail_at", 1) ? option("page_error", 0) : 0;
}
#ifndef HOST_REAL_SPI
static int CTP_SPI_WRITE(struct spi_device *client, uint8_t *buf, uint16_t length)
{
    (void)client;
    record("write", 0, buf, length);
    /* Real SPI helpers mutate the direction bit of the address byte. */
    buf[0] |= 0x80;
    return ++writes == option("fail_at", 1) ? option("write_error", 0) : 0;
}
static int CTP_SPI_READ(struct spi_device *client, uint8_t *buf, uint16_t length)
{
    (void)client;
    record("read", 0, buf, length);
    reads++;
    buf[0] &= 0x7f;
    memset(buf + 1, 0, length - 1);
    if (buf[0] == 0x50)
        buf[1] = reads >= option("ack_after", 1) ? 0 : 0xfe;
    else if (buf[0] == 0x60)
        buf[1] = reads >= option("ready_after", 1) ? mock_fw_state
                                                    : option("initial_state", 0xa1);
    else if (buf[0] == 0x78 && length >= 39) {
        buf[1] = 0x42;
        buf[2] = reads >= option("info_after", 1) ? 0xbd : 0;
        buf[3] = 60; buf[4] = 40; buf[11] = 0;
        buf[35] = 0x34; buf[36] = 0x12; buf[37] = 30; buf[38] = 20;
    }
    /* Even plausible bytes must not turn a transport error into success. */
    return reads == option("fail_at", 1) ? option("read_error", 0) : 0;
}
#endif
static void msleep(unsigned int ms) { record("sleep", ms * 1000, NULL, 0); }
static void usleep_range(unsigned long low, unsigned long high)
{ (void)high; record("sleep", low, NULL, 0); }
/* Mock the target's 250-Hz clock without any wall-clock delays. */
static unsigned long msecs_to_jiffies(unsigned int ms) { return ((unsigned long)ms + 3) / 4; }
static void nvt_irq_enable(bool enabled)
{ record("irq", enabled, NULL, 0); ts->irq_enabled = enabled; }
static void nvt_release_contacts(void)
{ record("release", 0, NULL, 0); contacts = 0; }
static void nvt_schedule_restore_cmd(void) { record("restore", 0, NULL, 0); }
"""


MAIN = r"""
int main(int argc, char **argv)
{
    if (argc < 2) return 2;
    struct rlimit no_core = {0, 0};
    if (setrlimit(RLIMIT_CORE, &no_core)) return 3;
    argc_saved = argc; argv_saved = argv;
    ts->mmap = &memory_map;
    ts->fw_update_stat = option("ready", 1);
    ts->dev_pm_suspend = option("suspended", 0);
    ts->irq_enabled = option("irq", 0);
    ts->pen_support = option("pen", 1);
    ts->probe_state = option("probe", 1);
    ts->hw_crc = option("crc", 0);
    mock_fw_state = option("state", 0xa2);
    ts->fw_ver = 0xee; ts->x_num = 9; ts->y_num = 8;
    ts->max_button_num = 7; ts->nvt_pid = 0xbeef;
    ts->x_gang_num = 6; ts->y_gang_num = 5;
    ts->abs_x_max = 100; ts->abs_y_max = 200;
    bTouchIsAwake = option("awake", 1);
    need_write_charger_state_flag = option("pending", 1);
    nvt_fw_retries = option("retries", 0);
    contacts = 3;
    int ret = run_case(argv[1]);
    printf("{\"ret\":%d,\"held\":%d,\"lock_errors\":%d,\"pending\":%d,"
           "\"ready\":%d,\"irq\":%d,\"retries\":%u,\"health\":%lu,\"contacts\":%d,\"probe\":%u,"
           "\"info\":[%u,%u,%u,%u,%u,%u,%u,%u,%u],\"events\":[",
           ret, ts->lock.held, lock_errors, need_write_charger_state_flag,
           ts->fw_update_stat, ts->irq_enabled, nvt_fw_retries, nvt_health_activity,
           contacts, ts->probe_state, ts->fw_ver, ts->x_num, ts->y_num, ts->max_button_num,
           ts->nvt_pid, ts->x_gang_num, ts->y_gang_num, ts->abs_x_max, ts->abs_y_max);
    for (unsigned int i = 0; i < event_count; i++) {
        struct event *e = &events[i];
        printf("%s{\"op\":\"%s\",\"held\":%d,\"pending\":%d,\"ready\":%d,"
               "\"value\":%d,\"data\":[", i ? "," : "", e->op, e->held,
               e->pending, e->ready, e->value);
        for (int j = 0; j < e->length; j++) printf("%s%u", j ? "," : "", e->data[j]);
        printf("]}");
    }
    printf("]");
    report_extra();
    puts("}");
    return 0;
}
"""


class HostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not sys.platform.startswith("linux"):
            raise unittest.SkipTest("Run the host C harness with Linux/WSL Python")
        source = Path(os.environ.get("NT36532_SOURCE_DIR", DEFAULT_SOURCE)).resolve()
        if not source.is_dir() and "NT36532_SOURCE_DIR" not in os.environ:
            raise unittest.SkipTest("Set NT36532_SOURCE_DIR to the production driver directory")
        compiler = shlex.split(os.environ.get("NT36532_CC", "cc"))
        if not compiler or not shutil.which(compiler[0]):
            raise RuntimeError("Host compiler unavailable: " + repr(compiler))
        header = (source / "nt36xxx.h").read_text()
        commands = (source / "nt36xxx_ext_proc.c").read_text()
        text = (source / cls.source_file).read_text()
        functions = [extract_function(text, name, optional=name in cls.optional)
                     for name in cls.functions]
        temporary = tempfile.TemporaryDirectory(prefix="nt36532-host-", dir="/tmp")
        cls.addClassCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        if directory.is_relative_to(source):
            raise AssertionError("Harness output must be outside the production source")
        generated = directory / "harness.c"
        generated.write_text(cls.preamble + MOCKS + "\n" + extract_constants(header, commands)
                             + "\n" + cls.support(source) + cls.setup + "\n\n".join(functions)
                             + "\n" + cls.entry + cls.report + MAIN)
        cls.executable = directory / "harness"
        result = subprocess.run(compiler + ["-std=gnu11", "-O0", "-Wall", "-Wextra",
                                "-Werror=implicit-function-declaration", "-Werror=return-type",
                                "-Wno-unused-function", "-Wno-unused-variable", str(generated),
                                "-o", str(cls.executable)], cwd=directory, text=True,
                                capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError("Extracted production C did not compile:\n" + result.stderr)

    optional = ()
    setup = ""
    preamble = ""
    needs_health = False
    report = "\nstatic void report_extra(void) {}\n"

    @classmethod
    def support(cls, source):
        return health_support((source / "nt36xxx.c").read_text()) if cls.needs_health else ""

    def run_case(self, operation, **options):
        result = subprocess.run([str(self.executable), operation]
                                + [f"{key}={value}" for key, value in options.items()],
                                cwd=self.executable.parent, text=True, capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual((observed["held"], observed["lock_errors"]), (0, 0), observed)
        return observed

    def events(self, observed, operation):
        return [event for event in observed["events"] if event["op"] == operation]

    def assert_protected(self, observed):
        self.assertEqual(len(self.events(observed, "lock")), 1, observed)
        self.assertEqual(len(self.events(observed, "unlock")), 1, observed)
        for event in observed["events"]:
            if event["op"] not in ("lock", "sleep"):
                self.assertEqual(event["held"], 1, event)

    def assert_no_io(self, observed):
        self.assertFalse([e for e in observed["events"]
                          if e["op"] in ("page", "write", "read")], observed)


class CommandTests(HostTests):
    source_file = "nt36xxx_ext_proc.c"
    # The optional helper is absent in the original baseline; public C is never replaced.
    optional = ("nvt_host_cmd_locked",)
    functions = ("nvt_host_cmd_locked", "nvt_cmd_store", "nvt_ext_cmd_store_locked",
                 "nvt_ext_cmd_store", "nvt_edge_grid_zone_set", "nvt_set_charger",
                 "nvt_game_mode_set")
    entry = r"""
static int run_case(const char *op)
{
    if (!strcmp(op, "simple")) return nvt_cmd_store(0xba);
    if (!strcmp(op, "ext")) return nvt_ext_cmd_store(0x7b, 0x02);
    if (!strcmp(op, "edge")) return nvt_edge_grid_zone_set(3, 2,
                                        option("y1", 0x1234), option("y2", 0xabcd));
    if (!strcmp(op, "charger")) return nvt_set_charger(option("plug", 1));
    if (!strcmp(op, "game")) return nvt_game_mode_set(option("mode", 2));
    if (!strcmp(op, "ext_locked")) {
        mutex_lock(&ts->lock);
        int ret = nvt_ext_cmd_store_locked(0x7b, 0x02);
        mutex_unlock(&ts->lock);
        return ret;
    }
    return -EINVAL;
}
"""
    payloads = {"simple": [0x50, 0xba], "ext": [0x50, 0x7b, 2],
                "edge": [0x50, 0x7f, 1, 3, 2, 0x34, 0x12, 0xcd, 0xab],
                "charger": [0x50, 0x53]}

    def test_edge_grid_transaction_and_little_endian_payload(self):
        for y1, y2 in ((0x1234, 0xabcd), (0, 0xffff), (0x8001, 0x0100)):
            with self.subTest(y1=y1, y2=y2):
                result = self.run_case("edge", y1=y1, y2=y2)
                self.assertEqual(result["ret"], 0)
                self.assert_protected(result)
                self.assertEqual([e["op"] for e in result["events"]],
                                 ["lock", "page", "write", "sleep", "read", "unlock"])
                self.assertEqual(self.events(result, "page")[0]["value"] & ~0x7f, EVENT_BASE)
                self.assertEqual(self.events(result, "write")[0]["data"],
                                 [0x50, 0x7f, 1, 3, 2, y1 & 255, y1 >> 8, y2 & 255, y2 >> 8])
                self.assertEqual(self.events(result, "read")[0]["data"], [0x50, 0xff])

    def test_commands_do_no_io_when_inactive_including_after_lock_wait(self):
        for operation in (*self.payloads, "ext_locked"):
            for name, value in (("awake", 0), ("ready", 0), ("ready", 2), ("suspended", 1)):
                for suffix in ("", "_at_lock"):
                    with self.subTest(operation=operation, state=name + suffix, value=value):
                        result = self.run_case(operation, **{name + suffix: value})
                        self.assertEqual(result["ret"], -errno.EAGAIN)
                        self.assert_no_io(result)
                        self.assert_protected(result)

    def test_mutex_interruption_does_not_touch_controller(self):
        for operation in self.payloads:
            with self.subTest(operation=operation):
                result = self.run_case(operation, lock_error=-512)
                self.assertEqual(result["ret"], -512)
                self.assertEqual([e["op"] for e in result["events"]], ["lock"])
                self.assertEqual(result["pending"], 1)

    def test_transport_errors_are_propagated_and_stop_transaction(self):
        for operation in self.payloads:
            for stage, error, counts in (("page", -errno.ENXIO, (1, 0, 0)),
                                          ("write", -errno.EPIPE, (1, 1, 0)),
                                          ("read", -errno.EIO, (1, 1, 1))):
                with self.subTest(operation=operation, stage=stage):
                    result = self.run_case(operation, **{stage + "_error": error})
                    self.assertEqual(result["ret"], error)
                    self.assertEqual(tuple(len(self.events(result, s))
                                           for s in ("page", "write", "read")), counts)
                    self.assert_protected(result)

    def test_transport_errors_on_later_retry_are_not_swallowed(self):
        for operation in self.payloads:
            for stage in ("write", "read"):
                with self.subTest(operation=operation, stage=stage):
                    result = self.run_case(operation, ack_after=99, fail_at=2,
                                           **{stage + "_error": -errno.EIO})
                    self.assertEqual(result["ret"], -errno.EIO)
                    self.assertEqual(len(self.events(result, "write")), 2)
                    self.assertEqual(len(self.events(result, "read")), 1 if stage == "write" else 2)
                    self.assert_protected(result)

    def test_ack_retry_limit_delay_and_unmodified_payload(self):
        for operation, payload in self.payloads.items():
            for ack_after, expected in ((5, 0), (6, -errno.ETIMEDOUT)):
                with self.subTest(operation=operation, ack_after=ack_after):
                    result = self.run_case(operation, ack_after=ack_after)
                    self.assertEqual(result["ret"], expected)
                    self.assert_protected(result)
                    self.assertEqual([e["data"] for e in self.events(result, "write")], [payload] * 5)
                    self.assertEqual([e["data"] for e in self.events(result, "read")], [[0x50, 0xff]] * 5)
                    self.assertEqual([e["value"] for e in self.events(result, "sleep")], [20000] * 5)

    def test_locked_ext_helper_does_not_recursively_lock(self):
        result = self.run_case("ext_locked", ack_after=2)
        self.assertEqual(result["ret"], 0)
        self.assert_protected(result)
        self.assertEqual([e["data"] for e in self.events(result, "write")], [[0x50, 0x7b, 2]] * 2)

    def test_charger_pending_clears_only_after_ack_before_unlock(self):
        for plug, opcode in ((0, 0x51), (1, 0x53)):
            with self.subTest(plug=plug):
                result = self.run_case("charger", plug=plug, ack_after=3)
                self.assertEqual(result["ret"], 0)
                self.assertEqual(len(self.events(result, "read")), 3)
                self.assert_protected(result)
                self.assertEqual([e["data"] for e in self.events(result, "write")], [[0x50, opcode]] * 3)
                for event in result["events"][:-1]:
                    self.assertEqual(event["pending"], 1, event)
                self.assertEqual(self.events(result, "unlock")[0]["pending"], 0)
                self.assertEqual(result["pending"], 0)

    def test_charger_failure_marks_pending_before_unlock(self):
        for options in ({"page_error": -errno.EIO}, {"write_error": -errno.EIO},
                        {"read_error": -errno.EIO}, {"ack_after": 6},
                        {"awake": 0}, {"ready": 0}, {"suspended": 1}):
            with self.subTest(options=options):
                result = self.run_case("charger", pending=0, **options)
                self.assertLess(result["ret"], 0)
                self.assert_protected(result)
                self.assertEqual(self.events(result, "unlock")[0]["pending"], 1)
                self.assertEqual(result["pending"], 1)

    def test_invalid_charger_request_has_no_io(self):
        result = self.run_case("charger", plug=2)
        self.assertEqual(result["ret"], -errno.EINVAL)
        self.assert_no_io(result)

    def test_game_mode_keeps_legacy_palm_opcode_not_rek(self):
        for mode, subcommand in ((0, 0), (1, 2), (2, 1)):
            with self.subTest(mode=mode):
                result = self.run_case("game", mode=mode)
                self.assertEqual(result["ret"], 0)
                self.assertEqual([e["data"] for e in self.events(result, "write")],
                                 [[0x50, 0x79, subcommand]])
                self.assert_protected(result)


class FirmwareStateTests(HostTests):
    source_file = "nt36xxx.c"
    functions = ("nvt_check_fw_reset_state", "nvt_get_fw_info")
    entry = r"""
static int run_case(const char *op)
{
    mutex_lock(&ts->lock);
    int ret = !strcmp(op, "reset") ? nvt_check_fw_reset_state(option("requested", 0xa2))
                                   : nvt_get_fw_info();
    mutex_unlock(&ts->lock);
    return ret;
}
"""
    cached_info = [0xee, 9, 8, 7, 0xbeef, 6, 5, 100, 200]

    def test_reset_accepts_requested_through_max(self):
        for requested in (0xa0, 0xa2, 0xa3):
            for state in (requested, 0xaf):
                with self.subTest(requested=requested, state=state):
                    result = self.run_case("reset", requested=requested, state=state)
                    self.assertEqual(result["ret"], 0)
                    self.assertEqual(len(self.events(result, "read")), 1)
                    self.assertEqual(self.events(result, "page")[0]["value"] & ~0x7f, EVENT_BASE)
                    self.assertEqual(self.events(result, "read")[0]["data"][0], 0x60)
                    self.assertFalse(self.events(result, "sleep"))

    def test_reset_out_of_range_times_out_with_legacy_read_bound(self):
        for requested, retries in ((0xa0, 10), (0xa2, 50)):
            for state in (requested - 1, 0xb0, 0xff):
                with self.subTest(requested=requested, state=state):
                    result = self.run_case("reset", requested=requested, state=state)
                    self.assertEqual(result["ret"], -errno.ETIMEDOUT)
                    self.assertEqual(len(self.events(result, "read")), retries + 1)
                    self.assertEqual([e["value"] for e in self.events(result, "sleep")], [10000] * retries)
                    self.assertEqual(len(self.events(result, "page")), 1)
                    self.assertFalse(self.events(result, "write"))

    def test_reset_can_become_ready_on_last_permitted_read(self):
        for requested, bound in ((0xa0, 11), (0xa2, 51)):
            for ready_after, expected in ((bound, 0), (bound + 1, -errno.ETIMEDOUT)):
                with self.subTest(requested=requested, ready_after=ready_after):
                    result = self.run_case("reset", requested=requested, state=requested,
                                           initial_state=requested - 1, ready_after=ready_after)
                    self.assertEqual(result["ret"], expected)
                    self.assertEqual(len(self.events(result, "read")), bound)
                    self.assertEqual(len(self.events(result, "sleep")), bound - 1)

    def test_reset_propagates_page_and_read_errors_even_with_ready_bytes(self):
        for stage, fail_at, read_count in (("page", 1, 0), ("read", 1, 1), ("read", 2, 2)):
            with self.subTest(stage=stage, fail_at=fail_at):
                result = self.run_case("reset", fail_at=fail_at, ready_after=fail_at,
                                       **{stage + "_error": -errno.EIO})
                self.assertEqual(result["ret"], -errno.EIO)
                self.assertEqual(len(self.events(result, "read")), read_count)

    def test_fw_info_publishes_valid_fields_and_pid(self):
        result = self.run_case("info")
        self.assertEqual(result["ret"], 0)
        self.assertEqual(result["info"], [0x42, 60, 40, 0, 0x1234, 30, 20, 100, 200])
        self.assertEqual(self.events(result, "page")[0]["value"] & ~0x7f, EVENT_BASE)
        self.assertEqual(self.events(result, "read")[0]["data"][0], 0x78)
        self.assertEqual(len(self.events(result, "read")[0]["data"]), 39)

    def test_fw_info_transport_errors_do_not_publish_or_default_cache(self):
        for stage, error, reads in (("page", -errno.ENXIO, 0), ("read", -errno.EIO, 1)):
            with self.subTest(stage=stage):
                result = self.run_case("info", **{stage + "_error": error})
                self.assertEqual(result["ret"], error)
                self.assertEqual(result["info"], self.cached_info)
                self.assertEqual(len(self.events(result, "page")), 1)
                self.assertEqual(len(self.events(result, "read")), reads)

    def test_fw_info_complement_retry_bound_is_preserved(self):
        for info_after, expected in ((4, 0), (5, -1)):
            with self.subTest(info_after=info_after):
                result = self.run_case("info", info_after=info_after)
                self.assertEqual(result["ret"], expected)
                self.assertEqual(len(self.events(result, "read")), 4)
                self.assertEqual(len(self.events(result, "page")), 4)
                if expected:
                    self.assertEqual(result["info"][0], 0)
                    self.assertEqual(result["info"][-2:], [2944, 1840])


class DiagnosticTests(HostTests):
    source_file = "nt36xxx_ext_proc.c"
    functions = ("nvt_baseline_open",)
    # Only the diagnostic entry/cleanup control flow is under test here.
    setup = r"""
struct inode { int unused; };
struct file { int unused; };
static const int nvt_seq_ops;
static int nvt_clear_fw_status(void)
{ record("clear", 0, NULL, 0); return option("clear_error", 0); }
static int nvt_check_fw_status(void)
{ record("status", 0, NULL, 0); return option("status_error", 0); }
static int nvt_get_fw_info(void)
{ record("info", 0, NULL, 0); return option("info_error", 0); }
static void nvt_change_mode(uint8_t mode) { record("mode", mode, NULL, 0); }
static void nvt_read_mdata(uint32_t address, uint32_t buttons)
{ (void)buttons; record("mdata", address, NULL, 0); }
static int seq_open(struct file *file, const int *ops)
{ (void)file; (void)ops; record("seq", 0, NULL, 0); return 0; }
"""
    entry = r"""
static int run_case(const char *op)
{ (void)op; return nvt_baseline_open(NULL, NULL); }
"""

    def test_diagnostic_error_restores_normal_mode_before_unlock(self):
        for stage in ("clear", "status", "info"):
            with self.subTest(stage=stage):
                result = self.run_case("baseline", **{stage + "_error": -errno.EIO})
                self.assertEqual(result["ret"], -errno.EAGAIN)
                self.assert_protected(result)
                self.assertEqual([e["value"] for e in self.events(result, "mode")],
                                 [] if stage == "clear" else [0x22, 0])
                self.assertEqual(result["events"][-1]["op"], "unlock")
                if stage != "clear":
                    self.assertEqual(result["events"][-2]["op"], "mode")
                self.assertFalse(self.events(result, "mdata"))
                self.assertFalse(self.events(result, "seq"))

    def test_inactive_diagnostic_does_not_enter_test_mode(self):
        for name, value in (("awake", 0), ("ready", 0), ("suspended", 1)):
            for suffix in ("", "_at_lock"):
                with self.subTest(state=name + suffix):
                    result = self.run_case("baseline", **{name + suffix: value})
                    self.assertEqual(result["ret"], -errno.EAGAIN)
                    self.assertEqual([e["op"] for e in result["events"]], ["lock", "unlock"])

    def test_success_leaves_test_mode_before_opening_seq_file(self):
        result = self.run_case("baseline")
        self.assertEqual(result["ret"], 0)
        self.assertEqual([e["op"] for e in result["events"]],
                         ["lock", "clear", "mode", "status", "info", "mdata", "mode", "unlock", "seq"])
        self.assertEqual([e["value"] for e in self.events(result, "mode")], [0x22, 0])
        self.assertTrue(all(e["held"] == 1 for e in result["events"][1:-1]))
        self.assertEqual(result["events"][-1]["held"], 0)


class FirmwareCompletionTests(HostTests):
    needs_health = True
    source_file = "nt36xxx.c"
    functions = ("nvt_fw_update_complete",)
    setup = r"""
static void nvt_queue_fw_update(unsigned int ms) { record("queue", ms, NULL, 0); }
"""
    entry = r"""
static int run_case(const char *op)
{
    (void)op;
    mutex_lock(&ts->lock);
    for (int i = 0; i < option("repeat", 1); i++)
        nvt_fw_update_complete(option("result", 0));
    mutex_unlock(&ts->lock);
    return 0;
}
"""

    def test_verified_success_enables_irq_and_restore_and_resets_budget(self):
        result = self.run_case("complete", ready=1, retries=2)
        self.assert_protected(result)
        self.assertEqual((result["ready"], result["irq"], result["health"], result["retries"]), (1, 1, 1, 0))
        self.assertEqual([e["op"] for e in result["events"]], ["lock", "irq", "restore", "unlock"])
        self.assertEqual(self.events(result, "irq")[0]["value"], 1)
        self.assertEqual(result["contacts"], 3)

    def test_error_or_unverified_success_fails_closed(self):
        for ready, error in ((1, -errno.EIO), (0, 0), (2, 0)):
            with self.subTest(ready=ready, error=error):
                result = self.run_case("complete", ready=ready, result=error, irq=1)
                self.assert_protected(result)
                self.assertEqual((result["ready"], result["irq"], result["contacts"], result["health"]), (0, 0, 0, 0))
                self.assertEqual([e["op"] for e in result["events"]],
                                 ["lock", "irq", "release", "queue", "unlock"])
                self.assertTrue(all(e["ready"] == 0 for e in result["events"][1:]))
                self.assertEqual(self.events(result, "queue")[0]["value"], 1000)

    def test_failure_has_at_most_two_outer_retries(self):
        result = self.run_case("complete", result=-errno.EIO, repeat=4, irq=1)
        self.assert_protected(result)
        self.assertEqual([e["value"] for e in self.events(result, "queue")], [1000, 1000])
        self.assertFalse(self.events(result, "restore"))
        self.assertEqual([e["value"] for e in self.events(result, "irq")], [0] * 4)
        self.assertEqual((result["ready"], result["irq"], result["contacts"]), (0, 0, 0))

    def test_inactive_lifecycle_does_not_resume_or_retry(self):
        for inactive in ({"awake": 0}, {"suspended": 1}):
            for error in (0, -errno.EIO):
                with self.subTest(inactive=inactive, error=error):
                    result = self.run_case("complete", result=error, ready=1, retries=2, **inactive)
                    self.assert_protected(result)
                    self.assertEqual([e["op"] for e in result["events"]], ["lock", "unlock"])
                    self.assertEqual((result["ready"], result["irq"], result["health"],
                                      result["retries"], result["contacts"]), (1, 0, 0, 2, 3))


class FirmwareUpdateTests(HostTests):
    needs_health = True
    source_file = "nt36xxx_fw_update.c"
    functions = ("nvt_update_firmware", "Boot_Update_Firmware")
    # The parser/download algorithms are dependencies, not alternate updater implementations.
    setup = r"""
static int gpio_184, allocation;
static void *bin_map;
static struct workqueue_struct charger_queue;
#define IS_ERR_OR_NULL(p) (!(p) || (uintptr_t)(p) >= (uintptr_t)-4095)
static int update_firmware_request(char *name)
{
    record("request", 0, (const uint8_t *)name, strlen(name));
    int ret = option("request_error", 0);
    if (!ret) bin_map = &allocation;
    return ret;
}
static int nvt_download_init(void)
{ record("init", 0, NULL, 0); return option("init_error", 0); }
static int nvt_download_firmware(void)
{ record("download", 0, NULL, 0); return option("download_error", 0); }
static int nvt_download_firmware_hw_crc(void)
{ record("download", 1, NULL, 0); return option("download_error", 0); }
static int nvt_check_fw_reset_state(RST_COMPLETE_STATE state)
{ record("reset_state", state, NULL, 0); return option("reset_error", 0); }
static int nvt_get_fw_info(void)
{ record("fw_info", 0, NULL, 0); return option("info_error", 0); }
static void kfree(void *p) { record("free", p == &allocation, NULL, 0); }
static void update_firmware_release(void) { record("firmware_release", 0, NULL, 0); }
static bool queue_delayed_work(struct workqueue_struct *queue, struct delayed_work *work,
                               unsigned long delay)
{
    uint8_t identity[] = { queue == &charger_queue, work == &ts->charger_notify_work };
    record("charger_queue", delay, identity, sizeof(identity));
    return true;
}
static void get_tp_info(void) { record("tp_info", 0, NULL, 0); }
/* Its actual implementation is exercised by FirmwareCompletionTests. */
static void nvt_fw_update_complete(int ret) { record("complete", ret, NULL, 0); }
static int nvt_support_pen_set(uint8_t mode)
{ record("pen", mode, NULL, 0); return option("pen_error", 0); }
"""
    entry = r"""
static int run_case(const char *op)
{
    gpio_184 = option("panel", 0);
    ts->nvt_charger_notify_wq = option("charger_queue", 0) ? &charger_queue : NULL;
    if (!strcmp(op, "worker")) {
        for (int i = 0; i < option("repeat", 1); i++)
            Boot_Update_Firmware(&ts->nvt_fwu_work.work);
        return 0;
    }
    mutex_lock(&ts->lock);
    int ret = nvt_update_firmware("host-test.bin");
    mutex_unlock(&ts->lock);
    return ret;
}
"""

    def test_worker_skips_inactive_or_already_recovered_after_lock(self):
        for name, value in (("ready", 1), ("awake", 0), ("suspended", 1)):
            for suffix in ("", "_at_lock"):
                with self.subTest(state=name + suffix):
                    options = {"ready": 0, name + suffix: value}
                    result = self.run_case("worker", **options)
                    self.assertEqual([e["op"] for e in result["events"]], ["lock", "unlock"])
                    self.assertEqual((result["contacts"], result["probe"]), (3, 1))

    def test_worker_success_publishes_info_and_completes_before_unlocked_pen(self):
        for panel, firmware in ((0, "novatek_ts_fw_boe.bin"), (1, "novatek_ts_fw_tm.bin")):
            with self.subTest(panel=panel):
                result = self.run_case("worker", ready=0, pending=0, panel=panel, charger_queue=1)
                self.assertEqual(bytes(self.events(result, "request")[0]["data"]).decode(), firmware)
                self.assertEqual([e["op"] for e in result["events"]],
                                 ["lock", "request", "init", "release", "download", "reset_state",
                                  "fw_info", "page", "charger_queue", "free", "firmware_release",
                                  "tp_info", "complete", "unlock", "pen"])
                self.assertEqual(self.events(result, "reset_state")[0]["value"], 0xa2)
                self.assertEqual(self.events(result, "complete")[0]["value"], 0)
                self.assertTrue(all(e["held"] == 1 for e in result["events"][1:-1]))
                self.assertEqual((result["events"][-1]["held"], result["events"][-1]["value"]), (0, 0))
                self.assertEqual((result["ready"], result["pending"], result["probe"]), (1, 1, 0))
                self.assertEqual(self.events(result, "page")[0]["ready"], 0)
                queued = self.events(result, "charger_queue")[0]
                self.assertEqual((queued["ready"], queued["pending"], queued["value"], queued["data"]),
                                 (1, 1, 125, [1, 1]))

    def test_worker_propagates_actual_failure_to_locked_completion(self):
        for stage, error in (("request", -errno.ENOENT), ("init", -errno.ENOMEM),
                             ("download", -errno.EIO), ("reset", -errno.ETIMEDOUT),
                             ("info", -errno.EIO), ("page", -errno.ENXIO)):
            with self.subTest(stage=stage):
                result = self.run_case("worker", ready=0, **{stage + "_error": error})
                self.assert_protected(result)
                self.assertEqual([e["value"] for e in self.events(result, "complete")], [error])
                self.assertEqual([e["op"] for e in result["events"][-2:]], ["complete", "unlock"])
                self.assertFalse(self.events(result, "tp_info"))
                self.assertFalse(self.events(result, "pen"))
                self.assertFalse(self.events(result, "charger_queue"))
                self.assertEqual((result["ready"], result["probe"]), (0, 1))

    def test_worker_pen_is_one_time_and_stale_replay_does_not_update(self):
        for probe, pen_error, expected_probe, pen_calls in ((0, 0, 0, 0), (1, 0, 0, 1),
                                                           (1, -errno.EIO, 1, 1)):
            with self.subTest(probe=probe, pen_error=pen_error):
                result = self.run_case("worker", ready=0, probe=probe, pen_error=pen_error, repeat=2)
                self.assertEqual(len(self.events(result, "request")), 1)
                self.assertEqual(len(self.events(result, "complete")), 1)
                self.assertEqual(len(self.events(result, "pen")), pen_calls)
                self.assertEqual(result["probe"], expected_probe)
                self.assertEqual([e["op"] for e in result["events"][-2:]], ["lock", "unlock"])
                self.assertTrue(all(e["held"] == 0 for e in self.events(result, "pen")))

    def test_updater_pre_download_failures_preserve_previous_readiness(self):
        for ready in (0, 1):
            for stage, error in (("request", -errno.ENOENT), ("init", -errno.ENOMEM)):
                with self.subTest(ready=ready, stage=stage):
                    result = self.run_case("update", ready=ready, pending=0, **{stage + "_error": error})
                    self.assertEqual(result["ret"], error)
                    self.assert_protected(result)
                    self.assertTrue(all(e["ready"] == ready for e in result["events"]))
                    expected = ["lock", "request", "unlock"] if stage == "request" else [
                        "lock", "request", "init", "free", "firmware_release", "unlock"]
                    self.assertEqual([e["op"] for e in result["events"]], expected)
                    self.assertEqual((result["ready"], result["contacts"], result["pending"]), (ready, 3, 0))

    def test_inactive_updater_leaves_controller_and_readiness_untouched(self):
        for inactive in ({"awake": 0}, {"suspended": 1}):
            with self.subTest(inactive=inactive):
                result = self.run_case("update", ready=1, **inactive)
                self.assertEqual(result["ret"], -errno.EAGAIN)
                self.assertEqual([e["op"] for e in result["events"]], ["lock", "unlock"])
                self.assertEqual((result["ready"], result["contacts"]), (1, 3))

    def test_readiness_clears_immediately_before_destructive_download(self):
        for crc in (0, 1):
            with self.subTest(crc=crc):
                result = self.run_case("update", ready=1, crc=crc, download_error=-errno.EIO)
                self.assertEqual(result["ret"], -errno.EIO)
                self.assert_protected(result)
                self.assertEqual([e["op"] for e in result["events"]],
                                 ["lock", "request", "init", "release", "download", "free",
                                  "firmware_release", "unlock"])
                self.assertEqual([e["ready"] for e in result["events"]], [1, 1, 1, 0, 0, 0, 0, 0])
                self.assertEqual(self.events(result, "download")[0]["value"], crc)
                self.assertEqual((result["ready"], result["contacts"]), (0, 0))


class FirmwareQueueTests(HostTests):
    source_file = "nt36xxx.c"
    functions = ("nvt_queue_fw_update",)
    setup = r"""
static unsigned long clock_tick, nvt_boot_fw_deadline, scheduled_delay;
static unsigned int clock_reads;
static unsigned long clock_now(void)
{ unsigned long now = clock_tick; clock_reads++; clock_tick += option("advance", 0); return now; }
#define jiffies clock_now()
static struct workqueue_struct firmware_queue, *nvt_fwu_wq;
#define time_before(a, b) ((long)((a) - (b)) < 0)
#define max(a, b) ((a) > (b) ? (a) : (b))
static bool mod_delayed_work(struct workqueue_struct *queue, struct delayed_work *work,
                             unsigned long delay)
{
    uint8_t identity[] = { queue == &firmware_queue, work == &ts->nvt_fwu_work };
    scheduled_delay = delay;
    record("mod_work", delay, identity, sizeof(identity));
    return true;
}
"""
    entry = r"""
static int run_case(const char *op)
{
    (void)op;
    clock_tick = unsigned_option("now", 0);
    nvt_boot_fw_deadline = unsigned_option("deadline", 3500);
    nvt_fwu_wq = option("have_queue", 1) ? &firmware_queue : NULL;
    nvt_queue_fw_update(option("delay", 0));
    return 0;
}
"""

    report = r"""
static void report_extra(void)
{ printf(",\"clock_reads\":%u,\"scheduled_delay\":%lu", clock_reads, scheduled_delay); }
"""

    def assert_schedule(self, result, ticks):
        self.assertEqual(result["scheduled_delay"], ticks)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual((event["op"], event["value"], event["data"]), ("mod_work", ticks, [1, 1]))

    def test_cold_boot_deadline_survives_early_resume(self):
        for now, delay, ticks in ((0, 0, 3500), (50, 200, 3450), (1000, 200, 2500)):
            with self.subTest(now=now, delay=delay):
                self.assert_schedule(self.run_case("queue", now=now, delay=delay), ticks)

    def test_after_cold_deadline_resume_uses_only_requested_delay(self):
        for now in (3500, 3501, 4000):
            with self.subTest(now=now):
                self.assert_schedule(self.run_case("queue", now=now, delay=200), 50)

    def test_retry_uses_maximum_of_deadline_remaining_and_one_second(self):
        for now, ticks in ((3200, 300), (3300, 250), (4000, 250)):
            with self.subTest(now=now):
                self.assert_schedule(self.run_case("queue", now=now, delay=1000), ticks)

    def test_missing_firmware_queue_does_not_schedule(self):
        result = self.run_case("queue", have_queue=0, delay=200)
        self.assertEqual(result["events"], [])

    def test_queue_captures_clock_once_across_preemption(self):
        result = self.run_case("queue", now=3499, deadline=3500, advance=2)
        self.assert_schedule(result, 1)
        self.assertEqual(result["clock_reads"], 1)

    def test_zero_deadline_is_valid_across_unsigned_wrap(self):
        result = self.run_case("queue", now=-2, deadline=0)
        self.assert_schedule(result, 2)


class RawTransportTests(HostTests):
    source_file = "nt36xxx.c"
    preamble = "#define HOST_REAL_SPI\n"
    needs_health = True
    functions = ("CTP_SPI_READ", "CTP_SPI_WRITE", "nvt_flash_read", "nvt_flash_open", "nvt_flash_close")
    setup = r"""
#include <sys/types.h>
#define __user
#define GFP_KERNEL 0
#define GFP_DMA 0
struct inode { int unused; };
struct file { void *private_data; };
struct nvt_flash_data { int lock; };
#define rwlock_init(p) (*(p) = 0)
static uint8_t rx[NVT_READ_LEN], tx[NVT_XBUF_LEN], wire[65536], direct[65536];
static struct region { uint8_t *base; size_t size; bool owned; } regions[16];
static int alloc_calls, spi_calls, bad_copies;

static void add_region(void *base, size_t size, bool owned)
{
    for (int i = 0; i < 16; i++) if (!regions[i].base) {
        regions[i] = (struct region){base, size, owned};
        return;
    }
    exit(3);
}
static bool fits(const void *pointer, size_t length)
{
    uintptr_t address = (uintptr_t)pointer;
    for (int i = 0; i < 16; i++) {
        uintptr_t base = (uintptr_t)regions[i].base;
        if (base && address >= base && address - base <= regions[i].size)
            return length <= regions[i].size - (address - base);
    }
    return false;
}
static void *tracked_memcpy(void *to, const void *from, size_t length)
{
    record("memcpy", length, NULL, 0);
    /* Observe unsafe baseline copies without actually corrupting the host process. */
    if (!fits(to, length) || !fits(from, length)) { bad_copies++; return to; }
    return memcpy(to, from, length);
}
static void *mock_alloc(size_t size, int flags)
{
    (void)flags;
    record("alloc", size, NULL, 0);
    if (++alloc_calls == option("alloc_fail_at", 0)) return NULL;
    void *p = calloc(1, size);
    if (!p) exit(3);
    add_region(p, size, true);
    return p;
}
static void kfree(void *p)
{
    if (!p) return;
    for (int i = 0; i < 16; i++) if (regions[i].base == p && regions[i].owned) {
        regions[i].base = NULL;
        free(p);
        return;
    }
    exit(3);
}
static int copy_from_user(void *to, const void *from, size_t length)
{
    record("copy_from", length, NULL, 0);
    if (option("from_error", 0)) return 1;
    if (!fits(to, length) || !fits(from, length)) exit(3);
    memcpy(to, from, length);
    return 0;
}
static int copy_to_user(void *to, const void *from, size_t length)
{
    record("copy_to", length, NULL, 0);
    if (option("to_error", 0)) return 1;
    if (!fits(to, length) || !fits(from, length)) exit(3);
    memcpy(to, from, length);
    return 0;
}
static int spi_read_write(struct spi_device *client, uint8_t *buf, size_t length, NVT_SPI_RW direction)
{
    (void)client;
    uint8_t data[] = { direction, buf[0] };
    record("spi", length, data, sizeof(data));
    lockdep_assert_held(&ts->xbuf_lock);
    return ++spi_calls >= option("spi_success_at", 1) ? 0 : -EIO;
}
static void raw_mutex_unlock(struct mutex *lock)
{
    if (lock == &ts->lock) record("raw_unlock", nvt_raw_users, NULL, 0);
    mutex_unlock(lock);
}
#define mutex_unlock raw_mutex_unlock
#define kzalloc mock_alloc
#define kmalloc mock_alloc
#define memcpy tracked_memcpy
"""
    entry = r"""
static int run_case(const char *op)
{
    ts->rbuf = rx; ts->xbuf = tx;
    memset(rx, 0xa5, sizeof(rx));
    direct[0] = 0x50;
    add_region(rx, sizeof(rx), false); add_region(tx, sizeof(tx), false);
    add_region(wire, sizeof(wire), false); add_region(direct, sizeof(direct), false);
    nvt_health_recoveries = 2; nvt_health_bad = 1;
    if (!strcmp(op, "read") || !strcmp(op, "write")) {
        uint8_t *buf = option("null", 0) ? NULL : direct;
        return !strcmp(op, "read") ? CTP_SPI_READ(NULL, buf, option("length", 2)) :
                                     CTP_SPI_WRITE(NULL, buf, option("length", 2));
    }
    if (!strcmp(op, "sessions")) {
        struct file a = {0}, b = {0};
        int ret = nvt_flash_open(NULL, &a);
        record("users", nvt_raw_users, NULL, 0);
        if (ret) return ret;
        ret = nvt_flash_open(NULL, &b);
        record("users", nvt_raw_users, NULL, 0);
        nvt_flash_close(NULL, &a); record("users", nvt_raw_users, NULL, 0);
        nvt_flash_close(NULL, &b); record("users", nvt_raw_users, NULL, 0);
        return ret;
    }
    unsigned int length = option("length", 6);
    wire[0] = (option("direction", NVTREAD) << 7) | ((length >> 8) & 0x7f);
    wire[1] = length & 0xff;
    wire[2] = 0x60;
    return nvt_flash_read(NULL, (char *)wire, option("count", 8), NULL);
}
"""
    report = r"""
static void report_extra(void)
{
    int live = 0;
    for (int i = 0; i < 16; i++) live += regions[i].base && regions[i].owned;
    printf(",\"raw\":{\"users\":%u,\"budget\":%u,\"bad\":%u,\"xheld\":%d,"
           "\"bad_copies\":%d,\"live_allocations\":%d,\"first\":%u}",
           nvt_raw_users, nvt_health_recoveries, nvt_health_bad, ts->xbuf_lock.held,
           bad_copies, live, direct[0]);
}
"""

    def run_case(self, operation, **options):
        result = super().run_case(operation, **options)
        self.assertEqual((result["raw"]["xheld"], result["raw"]["bad_copies"],
                          result["raw"]["live_allocations"]), (0, 0, 0), result)
        return result

    def test_transport_rejects_null_zero_and_over_capacity_before_lock_or_copy(self):
        for operation, too_large in (("read", 2048), ("write", 64514)):
            for options in ({"null": 1, "length": 1}, {"length": 0}, {"length": too_large}, {"length": 65535}):
                with self.subTest(operation=operation, options=options):
                    result = self.run_case(operation, **options)
                    self.assertEqual(result["ret"], -errno.EINVAL)
                    self.assertEqual(result["events"], [])
                    self.assertEqual(result["raw"]["first"], 0x50)

    def test_transport_accepts_exact_capacity_and_single_byte(self):
        for operation, maximum, direction in (("read", 2047, 1), ("write", 64513, 0)):
            for length in (1, maximum):
                with self.subTest(operation=operation, length=length):
                    result = self.run_case(operation, length=length)
                    self.assertEqual(result["ret"], 0)
                    self.assertEqual([e["value"] for e in self.events(result, "spi")], [length])
                    self.assertEqual(self.events(result, "spi")[0]["data"], [direction, 0x50 if direction else 0xd0])

    def test_transport_preserves_five_attempt_bound(self):
        for operation in ("read", "write"):
            for succeeds, expected in ((5, 0), (6, -errno.EIO)):
                with self.subTest(operation=operation, succeeds=succeeds):
                    result = self.run_case(operation, spi_success_at=succeeds)
                    self.assertEqual(result["ret"], expected)
                    self.assertEqual(len(self.events(result, "spi")), 5)
                    self.assertEqual(len(self.events(result, "xlock")), 1)

    def test_raw_wire_length_is_checked_before_payload_copy_or_io(self):
        for options in ({"length": 0}, {"length": 7, "count": 8},
                        {"length": 32767, "count": 4, "direction": 0},
                        {"length": 2048, "count": 2050}, {"length": 32767, "count": 32769}):
            with self.subTest(options=options):
                result = self.run_case("raw", **options)
                self.assertEqual(result["ret"], -errno.EINVAL)
                self.assertFalse(self.events(result, "spi") + self.events(result, "memcpy") + self.events(result, "copy_to"))
                self.assertEqual(len(self.events(result, "copy_from")), 1)

    def test_raw_outer_count_rejection_precedes_user_copy(self):
        for count in (0, 2, 64516):
            with self.subTest(count=count):
                result = self.run_case("raw", count=count)
                self.assertEqual(result["ret"], -errno.EFAULT)
                self.assertEqual(result["events"], [])

    def test_raw_valid_transfer_holds_ts_lock_and_copies_out_after_unlock(self):
        for direction, length in ((1, 2047), (0, 32767)):
            with self.subTest(direction=direction):
                result = self.run_case("raw", direction=direction, length=length, count=length + 2)
                self.assertEqual(result["ret"], 0)
                self.assertEqual(len(self.events(result, "lock")), 1)
                self.assertTrue(all(e["held"] == 1 for e in self.events(result, "spi")))
                self.assertEqual([e["held"] for e in self.events(result, "copy_to")], [0] if direction else [])
                self.assertEqual((result["raw"]["budget"], result["raw"]["bad"]), (2, 0))

    def test_raw_lifecycle_and_mutex_rejection_do_not_copy_payload(self):
        for options, expected in (({"awake": 0}, -errno.EAGAIN), ({"ready": 0}, -errno.EAGAIN),
                                  ({"suspended": 1}, -errno.EAGAIN), ({"ready_at_lock": 0}, -errno.EAGAIN),
                                  ({"lock_error": -512}, -512)):
            with self.subTest(options=options):
                result = self.run_case("raw", **options)
                self.assertEqual(result["ret"], expected)
                self.assertFalse(self.events(result, "spi") + self.events(result, "memcpy") + self.events(result, "copy_to"))

    def test_raw_preserves_twenty_outer_and_five_inner_attempts(self):
        for succeeds, expected in ((100, 0), (101, -errno.EIO)):
            with self.subTest(succeeds=succeeds):
                result = self.run_case("raw", spi_success_at=succeeds)
                self.assertEqual(result["ret"], expected)
                self.assertEqual(len(self.events(result, "spi")), 100)
                self.assertEqual(len(self.events(result, "xlock")), 20)
                self.assertEqual(len(self.events(result, "copy_to")), int(expected == 0))

    def test_raw_usercopy_and_allocation_failures_clean_up(self):
        for options, expected, transfers in (({"from_error": 1}, -errno.EFAULT, 0),
                                             ({"to_error": 1}, -errno.EFAULT, 1),
                                             ({"alloc_fail_at": 1}, -errno.ENOMEM, 0),
                                             ({"alloc_fail_at": 2}, -errno.ENOMEM, 0)):
            with self.subTest(options=options):
                result = self.run_case("raw", **options)
                self.assertEqual(result["ret"], expected)
                self.assertEqual(len(self.events(result, "spi")), transfers)

    def test_raw_sessions_are_counted_under_lock_without_controller_commands(self):
        result = self.run_case("sessions")
        self.assertEqual(result["ret"], 0)
        self.assertEqual([e["value"] for e in self.events(result, "users")], [1, 2, 1, 0])
        self.assertEqual([e["value"] for e in self.events(result, "raw_unlock")], [1, 2, 1, 0])
        self.assertTrue(all(e["held"] == 1 for e in self.events(result, "raw_unlock")))
        self.assertFalse(self.events(result, "spi"))
        self.assertEqual((result["raw"]["budget"], result["raw"]["users"]), (2, 0))

    def test_raw_session_admission_failure_releases_allocation(self):
        for options, expected in (({"awake": 0}, -errno.EAGAIN), ({"ready": 0}, -errno.EAGAIN),
                                  ({"suspended": 1}, -errno.EAGAIN), ({"lock_error": -512}, -512),
                                  ({"alloc_fail_at": 1}, -errno.ENOMEM)):
            with self.subTest(options=options):
                result = self.run_case("sessions", **options)
                self.assertEqual(result["ret"], expected)
                self.assertEqual(result["raw"]["users"], 0)
                self.assertFalse(self.events(result, "spi"))


if __name__ == "__main__":
    unittest.main()
