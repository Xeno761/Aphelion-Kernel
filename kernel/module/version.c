// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Module version support - Custom permissive for TB373FU
 */

#include <linux/module.h>
#include <linux/string.h>
#include <linux/printk.h>
#include "internal.h"

int check_version(const struct load_info *info,
		  const char *symname,
			 struct module *mod,
			 const s32 *crc)
{
	return 1;
}

int check_modstruct_version(const struct load_info *info,
			    struct module *mod)
{
	return 1;
}

int same_magic(const char *amagic, const char *bmagic,
	       bool has_crcs)
{
	return 1;
}

void module_layout(struct module *mod,
		   struct modversion_info *ver,
		   struct kernel_param *kp,
		   struct kernel_symbol *ks,
		   struct tracepoint * const *tp)
{
}
EXPORT_SYMBOL(module_layout);
