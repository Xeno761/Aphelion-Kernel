#ifndef _APHELION_MTK_DISP_NOTIFY_H
#define _APHELION_MTK_DISP_NOTIFY_H

#include <linux/notifier.h>

#define MTK_DISP_EARLY_EVENT_BLANK	0x00
#define MTK_DISP_EVENT_BLANK		0x01

#define MTK_DISP_BLANK_UNBLANK		0x00
#define MTK_DISP_BLANK_POWERDOWN	0x01

int mtk_disp_notifier_register(const char *key, struct notifier_block *nb);
int mtk_disp_notifier_unregister(struct notifier_block *nb);

#endif /* _APHELION_MTK_DISP_NOTIFY_H */
