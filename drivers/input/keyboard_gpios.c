// XXXX-License-Identifier: GPL
/*
 * set keyboard 3.3V voltage enable/disable .
 */
#include <linux/export.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/bitops.h>
#include <linux/pinctrl/consumer.h>
#include <linux/module.h>
#include <linux/types.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/slab.h>
#include <linux/device.h>
#include <linux/platform_device.h>
#include <linux/io.h>
#include <linux/gpio/consumer.h>


#define KEYBOARD_GPIO_DEVICES "keyboard_gpio"
/* Static local state */
static struct pinctrl *kb_gpio;
static struct platform_driver kb_gpio_driver;
static struct pinctrl_state *_kb_gpio_penable_mode;
static struct pinctrl_state *_kb_gpio_pdisable_mode;

//static int __init keyboard_gpio_init(void);
//static void __init keyboard_gpio_exit(void);
static int _keyboard_gpio_probe(struct platform_device *pdev);
//static int _keyboard_gpio_remove(struct platform_device *pdev);

static const struct of_device_id _kb_gpio_of_idss[] = {
	{.compatible = "mediatek,keyboard_gpio",},
	{},
};

static struct platform_driver kb_gpio_driver = {
	.probe = _keyboard_gpio_probe,
//        .remove = _keyboard_gpio_remove,
	.driver = {
		   .name = KEYBOARD_GPIO_DEVICES,
		   .owner = THIS_MODULE,
		   .of_match_table = _kb_gpio_of_idss,
		   },
};

int kb_power33_enable(void)
{
	printk("keyboard power enable in \n");
	pinctrl_select_state(kb_gpio,_kb_gpio_penable_mode);
	printk("keyboard power enable out \n");
	return 0;
}
EXPORT_SYMBOL(kb_power33_enable);

int kb_power33_disable(void)
{
	printk("keyboard power disable in \n");
	pinctrl_select_state(kb_gpio,_kb_gpio_pdisable_mode);
	printk("keyboard power disable out \n");
	return 0;
}
EXPORT_SYMBOL(kb_power33_disable);

static int _keyboard_gpio_probe(struct platform_device *pdev)
{
	int ret;
	struct device *dev = &pdev->dev;
	printk("[ %s]  start !  \n",__func__);

	kb_gpio = devm_pinctrl_get(dev);
	if(IS_ERR(kb_gpio))
	{
		ret = PTR_ERR(kb_gpio);
		printk("cannot find kb_gpio! \n");
		return ret;
	}

//pintrcl-names = "state_kb_en33_ouput0","state_kb_en33_ouput1";

	_kb_gpio_pdisable_mode = pinctrl_lookup_state(kb_gpio,"state_kb_en33_ouput0");
	if(IS_ERR(_kb_gpio_pdisable_mode))
	{
		ret = PTR_ERR(_kb_gpio_pdisable_mode);
		printk("cannot find _kb_gpio_pdisable_mode! \n");
		return ret;
	}

	_kb_gpio_penable_mode = pinctrl_lookup_state(kb_gpio,"state_kb_en33_ouput1");
	if(IS_ERR(_kb_gpio_penable_mode))
	{
		ret = PTR_ERR(_kb_gpio_penable_mode);
		printk("cannot find _kb_gpio_penable_mode! \n");
		return ret;
	}

	return 0;
}
/*
static int __init _keyboard_gpio_remove(struct platform_device *pdev)
{
	return 0;
}
*/
static int __init keyboard_gpio_init(void)
{
	int err;

	err = platform_driver_register(&kb_gpio_driver);

	if (err) {
		printk("failed to add keyboard gpio driver \n");
		goto err_driver;
	}

	printk("finished\n");

err_driver:

	return err;
}

static void __exit keyboard_gpio_exit(void)
{
	platform_driver_unregister(&kb_gpio_driver);
}

module_init(keyboard_gpio_init);
module_exit(keyboard_gpio_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("XXXXXXXXXX>");
MODULE_DESCRIPTION("configurable gpio for keyboard driver");
