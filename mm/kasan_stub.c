// SPDX-License-Identifier: GPL-2.0
/*
 * kasan_stub.c - keep the KASAN static key exported when KASAN is compiled out.
 *
 * Several prebuilt MediaTek vendor modules (cfg80211, mali_kbase_mt6897_r44,
 * system_heap, mtk-mml, drm_dma_helper, ...) import the exported static key
 * "kasan_flag_enabled", which the in-tree runtime only defines when
 * CONFIG_KASAN_HW_TAGS is enabled. Without this stub, disabling CONFIG_KASAN
 * leaves those modules with an unresolved symbol and they fail to load, which
 * is why KASAN could not previously be turned off.
 *
 * Those modules reference only the flag itself: none of the 533 extracted
 * vendor modules import any __asan instrumentation hook or kasan_check /
 * kasan_report helper, so a permanently-false static key is sufficient and
 * unconditionally correct.
 */
#include <linux/export.h>
#include <linux/jump_label.h>

#if !IS_ENABLED(CONFIG_KASAN)
DEFINE_STATIC_KEY_FALSE(kasan_flag_enabled);
EXPORT_SYMBOL(kasan_flag_enabled);
#endif
