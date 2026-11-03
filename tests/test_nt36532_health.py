"""Extracted-C health/admission tests; injected frame evidence is not an IRQ test."""

import errno
import re
import unittest

from test_nt36532_recovery import HostTests, extract_defines, masked_c


class HealthTests(HostTests):
    source_file = "nt36xxx.c"
    needs_health = True
    functions = ("nvt_begin_recovery_locked", "nvt_fw_update_complete", "nvt_health_proc_show",
                 "nvt_ic_probe_locked", "nvt_health_check_func", "nvt_health_start",
                 "nvt_fault_window", "nvt_handle_fw_fault")

    @classmethod
    def support(cls, source):
        main = (source / "nt36xxx.c").read_text()
        commands = (source / "nt36xxx_ext_proc.c").read_text()
        match = re.search(r"static const struct proc_ops nvt_health_fops\s*=\s*\{[^}]*\};",
                          masked_c(commands))
        if match is None:
            raise AssertionError("Missing production health proc operations")
        return (super().support(source) + "\n" + extract_defines(main, (
            "NVT_HEALTH_PERIOD_MS", "NVT_HEALTH_COOLDOWN_MS", "NVT_HEALTH_MAX_RECOVER",
            "NVT_FAULT_GAP_MS", "NVT_HEALTH_HEALTHY_MS"))
            + cls.proc_mocks + commands[match.start():match.end()] + "\n")

    proc_mocks = r"""
#include <stdarg.h>
struct seq_file { char text[4096]; size_t used; };
static struct seq_file proc_output;
static long long nvt_irq_count = 123, nvt_pm_timeouts = 7;
static long long atomic64_read(long long *value) { return *value; }
static unsigned int jiffies_to_msecs(unsigned long ticks) { return ticks * 4; }
static void seq_printf(struct seq_file *m, const char *format, ...)
{
    lockdep_assert_held(&ts->lock);
    va_list args;
    va_start(args, format);
    int count = vsnprintf(m->text + m->used, sizeof(m->text) - m->used, format, args);
    va_end(args);
    if (count < 0 || (size_t)count >= sizeof(m->text) - m->used) exit(3);
    m->used += count;
}
static void seq_puts(struct seq_file *m, const char *text) { seq_printf(m, "%s", text); }
struct proc_ops { void *proc_open, *proc_read, *proc_lseek, *proc_release, *proc_write; };
static void nvt_health_proc_open(void) {}
static void seq_read(void) {}
static void seq_lseek(void) {}
static void single_release(void) {}
"""
    setup = r"""
#define time_before(a, b) ((long)((a) - (b)) < 0)
#define time_after(a, b) time_before(b, a)
#define time_after_eq(a, b) (!time_before(a, b))
#define time_before_eq(a, b) (!time_after(a, b))
static struct delayed_work nvt_health_work;
static struct workqueue_struct firmware_queue, *nvt_fwu_wq;
static int gpio_184, show_unchanged = 1;
static bool schedule_delayed_work(struct delayed_work *work, unsigned long delay)
{ record("health_timer", delay, NULL, 0); if (work != &nvt_health_work) exit(3); return true; }
static void nvt_queue_fw_update(unsigned int ms) { record("queue", ms, NULL, 0); }
static void nvt_sw_reset_idle(void) { record("sw_reset", 0, NULL, 0); }
static void nvt_clear_aci_error_flag(void) { record("aci", 0, NULL, 0); }
static void nvt_read_fw_history_all(void) { record("history", 0, NULL, 0); }
static int nvt_update_firmware(char *name)
{
    record("update", 0, (uint8_t *)name, strlen(name));
    int ret = option("update_error", 0);
    ts->fw_update_stat = ret ? 0 : 1;
    return ret;
}
static void snapshot(int ret)
{
    uint8_t data[] = { nvt_health_recoveries, nvt_health_bad, nvt_diag.handshake_streak,
                      nvt_diag.wdt_streak, nvt_health_qualifying, nvt_fw_retries };
    record("result", ret, data, sizeof(data));
}
"""
    entry = r"""
static int run_case(const char *op)
{
    (void)op;
    jiffies = unsigned_option("now", 2500);
    nvt_health_armed = option("armed", 1);
    nvt_health_activity = option("activity", 1);
    nvt_health_recoveries = option("budget", 0);
    nvt_health_cooldown_until = unsigned_option("cooldown", 0);
    nvt_health_last_recovery = unsigned_option("last_recovery", 0);
    nvt_health_bad = option("bad", 0);
    nvt_raw_users = option("raw", 0);
    nvt_health_qualifying = option("qualifying", 0);
    nvt_healthy_since = unsigned_option("since", 0);
    nvt_diag.handshake_streak = option("hs", 0);
    nvt_diag.wdt_streak = option("wdt", 0);
    nvt_diag.last_fault = unsigned_option("last_fault", 0);
    nvt_diag.last_valid = unsigned_option("last_valid", 0);
    nvt_diag.last_probe = unsigned_option("last_probe", 0);
    nvt_diag.touch_frames = option("frames", 0);
    nvt_diag.last_fw_state = 0x55;
    nvt_fwu_wq = option("have_queue", 1) ? &firmware_queue : NULL;
    gpio_184 = option("panel", 0);
    char *script = strdup(option_text("script", "q"));
    int ret = 0;
    for (char *s = strtok(script, ";"); s; s = strtok(NULL, ";")) {
        if (*s == 't') { jiffies = strtoul(s + 1, NULL, 0); continue; }
        if (*s == 's') { mock_fw_state = strtol(s + 1, NULL, 0); continue; }
        if (*s == 'g') { ts->fw_update_stat = strtol(s + 1, NULL, 0); continue; }
        /* The full IRQ parser is not compiled: supply already-validated frame evidence. */
        if (*s == 'v') { nvt_diag.touch_frames++; nvt_diag.last_valid = jiffies; continue; }
        if (*s == 'p') {
            nvt_health_check_func(NULL);
            ret = 0;
        } else if (*s == 'z') {
            struct nvt_diagnostics saved;
            memcpy(&saved, &nvt_diag, sizeof(saved));
            unsigned int budget = nvt_health_recoveries, bad = nvt_health_bad;
            bool qualifying = nvt_health_qualifying;
            ret = nvt_health_proc_show(&proc_output, NULL);
            show_unchanged &= !memcmp(&saved, &nvt_diag, sizeof(saved)) &&
                budget == nvt_health_recoveries && bad == nvt_health_bad &&
                qualifying == nvt_health_qualifying && nvt_irq_count == 123 && nvt_pm_timeouts == 7;
        } else {
            mutex_lock(&ts->lock);
            switch (*s) {
            case 'q': ret = nvt_ic_probe_locked(); break;
            case 'a': ret = nvt_begin_recovery_locked(strtol(s + 1, NULL, 0)); break;
            case 'r': nvt_reset_health_evidence(); ret = 0; break;
            case 'w': nvt_health_start(); ret = 0; break;
            case 'c': nvt_fw_update_complete(strtol(s + 1, NULL, 0)); ret = 0; break;
            case 'f': {
                uint8_t packet[7] = {0};
                if (strlen(s + 1) != 12) exit(3);
                for (int i = 0; i < 6; i++) {
                    char byte[3] = { s[1 + 2*i], s[2 + 2*i], 0 };
                    packet[i + 1] = strtoul(byte, NULL, 16);
                }
                ret = nvt_handle_fw_fault(packet);
                break;
            }
            default: exit(3);
            }
            mutex_unlock(&ts->lock);
        }
        snapshot(ret);
    }
    free(script);
    return ret;
}
"""
    report = r"""
static void report_extra(void)
{
    printf(",\"health\":{\"budget\":%u,\"bad\":%u,\"raw\":%u,\"armed\":%u,"
           "\"qualifying\":%u,\"since\":%lu,\"cooldown\":%lu,\"last_recovery\":%lu,"
           "\"checks\":%llu,\"failures\":%llu,\"recoveries\":%llu,\"blocked\":%llu,"
           "\"hs\":%u,\"wdt\":%u,\"hs_frames\":%llu,\"wdt_frames\":%llu,"
           "\"state\":%u,\"state_read\":%u,\"last_ret\":%d,\"reason\":%u,"
           "\"fw_ok\":%llu,\"fw_failed\":%llu,\"fw_ret\":%d,\"unchanged\":%d,\"writable\":%d},\"proc\":[",
           nvt_health_recoveries, nvt_health_bad, nvt_raw_users, nvt_health_armed,
           nvt_health_qualifying, nvt_healthy_since, nvt_health_cooldown_until, nvt_health_last_recovery,
           nvt_diag.health_checks, nvt_diag.health_failures, nvt_diag.recoveries, nvt_diag.recovery_blocked,
           nvt_diag.handshake_streak, nvt_diag.wdt_streak, nvt_diag.handshake_frames, nvt_diag.wdt_frames,
           nvt_diag.last_fw_state, nvt_diag.fw_state_read, nvt_diag.last_health_ret, nvt_diag.last_reason,
           nvt_diag.fw_successes, nvt_diag.fw_failures, nvt_diag.last_fw_ret, show_unchanged,
           nvt_health_fops.proc_write != NULL);
    for (size_t i = 0; i < proc_output.used; i++) printf("%s%u", i ? "," : "", (uint8_t)proc_output.text[i]);
    printf("]");
}
"""

    def play(self, *steps, **options):
        return self.run_case("script", script=";".join(steps), **options)

    def fault_steps(self, signature, times):
        return [step for now in times for step in (f"t{now}", "f" + signature)]

    def test_passive_state_probe_range_and_single_read(self):
        for state in [0, 0xa0, 0xa1, 0xb0, 0xff, *range(0xa2, 0xb0)]:
            with self.subTest(state=state):
                result = self.play("q", state=state)
                expected = 0 if 0xa2 <= state <= 0xaf else -errno.EAGAIN
                self.assertEqual(result["ret"], expected)
                self.assertEqual([e["op"] for e in result["events"]], ["lock", "page", "read", "unlock", "result"])
                self.assertEqual(self.events(result, "read")[0]["data"], [0x60, 0])
                self.assertEqual(result["health"]["state"], state)
                self.assertEqual(result["health"]["state_read"], 1)
                self.assertEqual(result["health"]["checks"], 1)

    def test_passive_probe_preserves_transport_error_and_read_validity(self):
        for stage, error, reads in (("page", -errno.ENXIO, 0), ("read", -errno.EIO, 1)):
            with self.subTest(stage=stage):
                result = self.play("q", **{stage + "_error": error})
                self.assertEqual(result["ret"], error)
                self.assertEqual(len(self.events(result, "read")), reads)
                self.assertEqual((result["health"]["state_read"], result["health"]["last_ret"],
                                  result["health"]["failures"]), (0, error, 1))
                self.assertFalse(self.events(result, "write") + self.events(result, "sleep"))

    def test_shared_gate_debits_once_and_quiesces_each_reason(self):
        for reason in (1, 2, 3):
            with self.subTest(reason=reason):
                result = self.play(f"a{reason}", f"a{reason}", irq=1, bad=1, hs=2, wdt=5, qualifying=1)
                self.assertEqual([e["value"] for e in self.events(result, "result")], [1, 0])
                self.assertEqual((result["health"]["budget"], result["health"]["recoveries"],
                                  result["health"]["reason"], result["health"]["cooldown"]), (1, 1, reason, 17500))
                self.assertEqual((result["ready"], result["irq"], result["contacts"]), (0, 0, 0))
                self.assertEqual(len(self.events(result, "release")), 1)
                self.assertTrue(all(e["held"] == 1 for e in self.events(result, "irq") + self.events(result, "release")))

    def test_denied_gate_does_not_change_readiness_or_hardware(self):
        for options in ({"awake": 0}, {"armed": 0}, {"ready": 0}, {"suspended": 1},
                        {"raw": 1}, {"have_queue": 0}, {"budget": 3}, {"budget": 1, "cooldown": 2501}):
            with self.subTest(options=options):
                result = self.play("a1", irq=1, **options)
                self.assertEqual(result["ret"], 0)
                self.assertEqual((result["ready"], result["irq"], result["contacts"]), (options.get("ready", 1), 1, 3))
                self.assertEqual(result["health"]["budget"], options.get("budget", 0))
                self.assertEqual([e["op"] for e in result["events"]], ["lock", "unlock", "result"])

    def test_budget_survives_success_health_start_and_evidence_reset(self):
        result = self.play("a1", "g1", "c0", "w", "r", "t17500", "a2", "g1", "c0",
                           "w", "t32500", "a3", "g1", "c0", "r", "t47500", "a1")
        self.assertEqual((result["health"]["budget"], result["health"]["recoveries"],
                          result["health"]["fw_ok"], result["health"]["blocked"]), (3, 3, 3, 1))
        self.assertEqual(result["ready"], 1)

    def test_completion_resets_transient_evidence_not_incident_budget(self):
        result = self.play("c-5", "c-5", "c-5", budget=2, bad=1, hs=2, wdt=8, qualifying=1)
        self.assertEqual([e["value"] for e in self.events(result, "queue")], [1000, 1000])
        self.assertEqual((result["health"]["budget"], result["health"]["bad"], result["health"]["hs"],
                          result["health"]["wdt"], result["health"]["qualifying"], result["health"]["fw_failed"]),
                         (2, 0, 0, 0, 0, 3))

    def test_cooldown_wrap_and_zero_sentinel_use_incident_history(self):
        for now in (-75000, 2**32 - 75000):
            with self.subTest(now=now):
                self.assertEqual(self.play("a1", now=now)["ret"], 1)
        self.assertEqual(self.play("a1", now=-1, budget=1, cooldown=0)["ret"], 0)
        self.assertEqual(self.play("a1", now=0, budget=1, cooldown=0)["ret"], 1)

    def test_first_bad_poll_waits_second_queues_after_admission(self):
        result = self.play("s0", "p", "t3250", "p")
        self.assertEqual([e["data"][:2] for e in self.events(result, "result")], [[0, 1], [1, 0]])
        self.assertEqual([e["value"] for e in self.events(result, "queue")], [0])
        self.assertEqual((result["health"]["checks"], result["health"]["reason"]), (2, 1))
        for event in self.events(result, "page") + self.events(result, "read") + self.events(result, "queue"):
            self.assertEqual(event["held"], 1)

    def test_idle_and_inactive_health_poll_never_recover(self):
        for options in ({"activity": 0}, {"awake": 0}, {"armed": 0}, {"raw": 1},
                        {"ready_at_lock": 0}, {"suspended_at_lock": 1}):
            with self.subTest(options=options):
                result = self.play("p", "p", state=0, **options)
                self.assert_no_io(result)
                self.assertFalse(self.events(result, "queue"))
        result = self.play("p", "t3250", "p", frames=0, state=0xa3)
        self.assertEqual(result["health"]["recoveries"], 0)

    def healthy_steps(self, frame="fresh", gap=0, fault=None, count=201):
        steps = []
        for index in range(count):
            now = 1000 + index * 750 + (gap if index >= 100 else 0)
            steps.append(f"t{now}")
            if frame == "fresh" or (frame == "old" and index == 0):
                steps.append("v")
            if index == 100 and fault:
                steps.extend(fault)
            steps.append("p")
        return steps

    def test_rearm_requires_full_continuous_interval_and_current_frame(self):
        for frame, count, expected in (("fresh", 201, 0), ("fresh", 200, 3), ("old", 201, 3), ("none", 201, 3)):
            with self.subTest(frame=frame, count=count):
                result = self.play(*self.healthy_steps(frame, count=count), budget=3, last_fault=1, last_recovery=1)
                self.assertEqual(result["health"]["budget"], expected)
                self.assertFalse(self.events(result, "queue"))

    def test_poll_gap_over_two_periods_restarts_healthy_qualification(self):
        for gap, expected in ((750, 0), (751, 3)):
            with self.subTest(gap=gap):
                result = self.play(*self.healthy_steps(gap=gap), budget=3, last_fault=1, last_recovery=1)
                self.assertEqual(result["health"]["budget"], expected)

    def test_rearm_frame_freshness_boundary_is_one_health_period(self):
        for frame_time, expected in ((150250, 0), (150249, 3)):
            with self.subTest(frame_time=frame_time):
                steps = self.healthy_steps(frame="none", count=199)
                steps.extend((f"t{frame_time}", "v", "t150250", "p", "t151000", "p"))
                result = self.play(*steps, budget=3, last_fault=1, last_recovery=1)
                self.assertEqual(result["health"]["budget"], expected)

    def test_fault_restarts_healthy_qualification(self):
        for fault in (("f" + "77" * 6,), ("s0", "p", "s162")):
            with self.subTest(fault=fault):
                result = self.play(*self.healthy_steps(fault=fault), budget=3, last_fault=1, last_recovery=1)
                self.assertEqual(result["health"]["budget"], 3)

    def test_handshake_window_is_first_to_third_not_interpacket_gap(self):
        for times, admitted in (((0, 225, 450), 0), ((0, 125, 250), 1)):
            with self.subTest(times=times):
                result = self.play(*self.fault_steps("77" * 6, times))
                self.assertEqual([e["value"] for e in self.events(result, "result")], [1, 1, 1])
                self.assertEqual(result["health"]["recoveries"], admitted)
                self.assertEqual(len(self.events(result, "queue")), admitted)

    def test_overlapping_fault_windows_retain_the_recent_suffix(self):
        for signature, milliseconds, action in (
                ("77" * 6, (0, 900, 1100, 1200), "queue"),
                ("fe" * 6, (0, 900, 910, 920, 930, 940, 950, 960, 970, 980, 1100, 1110), "update")):
            with self.subTest(signature=signature):
                ticks = [(ms + 3) // 4 for ms in milliseconds]
                result = self.play(*self.fault_steps(signature, ticks))
                self.assertEqual(result["health"]["recoveries"], 1)
                self.assertEqual(len(self.events(result, action)), 1)

    def test_fault_recognition_consumes_isolated_and_mixed_watchdog_packets(self):
        for signature, consumed in (("77" * 6, 1), ("fdfe" * 3, 1), ("00" * 6, 0),
                                    ("77" * 5 + "76", 0), ("77fd" * 3, 0)):
            with self.subTest(signature=signature):
                result = self.play("f" + signature)
                self.assertEqual(result["ret"], consumed)
                self.assertFalse(self.events(result, "queue") + self.events(result, "update"))

    def test_normal_packet_and_evidence_reset_break_fault_streaks(self):
        for interruption in ("f" + "00" * 6, "r", "w"):
            with self.subTest(interruption=interruption):
                result = self.play("f" + "77" * 6, "f" + "77" * 6, interruption, "f" + "77" * 6)
                self.assertEqual(result["health"]["hs"], 1)
                self.assertFalse(self.events(result, "queue"))

    def test_fault_packets_are_consumed_without_reset_when_gate_denies(self):
        for signature, count in (("77" * 6, 3), ("fe" * 6, 11)):
            for options in ({"awake": 0}, {"raw": 1}, {"suspended": 1}, {"budget": 3},
                            {"budget": 1, "cooldown": 2600}):
                with self.subTest(signature=signature, options=options):
                    result = self.play(*(["f" + signature] * (count + 2)), irq=1, **options)
                    self.assertTrue(all(e["value"] == 1 for e in self.events(result, "result")))
                    self.assertEqual((result["ready"], result["irq"], result["contacts"]), (1, 1, 3))
                    self.assertEqual(result["health"]["hs" if count == 3 else "wdt"], count)
                    self.assertFalse(self.events(result, "sw_reset") + self.events(result, "queue") + self.events(result, "update"))

    def test_watchdog_eleven_sample_threshold_and_fe_order(self):
        for signature in ("fe" * 6, "fdfe" * 3):
            for panel in (0, 1):
                with self.subTest(signature=signature, panel=panel):
                    before = self.play(*self.fault_steps(signature, range(0, 250, 25)))
                    self.assertFalse(self.events(before, "update"))
                    result = self.play(*self.fault_steps(signature, range(0, 251, 25)), panel=panel)
                    operations = [e["op"] for e in result["events"] if e["op"] not in ("lock", "unlock", "result")]
                    prelude = ["sw_reset", "aci"] if signature.startswith("fe") else []
                    self.assertEqual(operations, ["irq", "release", *prelude, "history", "update", "irq", "restore"])
                    firmware = "novatek_ts_fw_boe.bin" if panel == 0 else "novatek_ts_fw_tm.bin"
                    self.assertEqual(bytes(self.events(result, "update")[0]["data"]).decode(), firmware)
                    self.assertEqual((result["health"]["budget"], result["health"]["fw_ok"]), (1, 1))

    def test_watchdog_slow_span_does_not_trigger_and_failure_uses_outer_retry(self):
        slow = self.play(*self.fault_steps("fe" * 6, range(0, 501, 50)))
        self.assertFalse(self.events(slow, "update"))
        failed = self.play(*(["f" + "fe" * 6] * 11), update_error=-errno.EIO)
        self.assertEqual([e["value"] for e in self.events(failed, "queue")], [1000])
        self.assertEqual((failed["ready"], failed["health"]["budget"], failed["health"]["fw_ret"]), (0, 1, -errno.EIO))

    def test_readonly_diagnostics_use_cached_data_without_resets_or_io(self):
        result = self.play("z", "z", raw=2, budget=2, cooldown=2600, bad=1, hs=2, wdt=4, qualifying=1)
        self.assertEqual((result["health"]["unchanged"], result["health"]["writable"]), (1, 0))
        self.assertEqual([e["op"] for e in result["events"]], ["lock", "unlock", "result"] * 2)
        text = bytes(result["proc"]).decode()
        self.assertIn("raw_sessions=2", text)
        self.assertIn("irq_entries=123 pm_timeouts=7", text)
        self.assertIn("budget_used=2 budget_max=3 cooldown_ms=400", text)

    def test_readonly_diagnostics_lock_interruption_has_no_side_effect(self):
        result = self.play("z", lock_error=-512, budget=2, hs=2)
        self.assertEqual(result["ret"], -512)
        self.assertEqual(result["proc"], [])
        self.assertEqual(result["health"]["unchanged"], 1)
        self.assertEqual([e["op"] for e in result["events"]], ["lock", "result"])


if __name__ == "__main__":
    unittest.main()
