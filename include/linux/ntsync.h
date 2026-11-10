/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_NTSYNC_H
#define _LINUX_NTSYNC_H

#include <linux/fs.h>
#include <linux/types.h>

#ifdef CONFIG_NTSYNC
bool is_ntsync_device(const struct inode *inode);
bool is_ntsync_file(const struct file *file);
#else
static inline bool is_ntsync_device(const struct inode *inode) { return false; }
static inline bool is_ntsync_file(const struct file *file) { return false; }
#endif

#endif /* _LINUX_NTSYNC_H */
