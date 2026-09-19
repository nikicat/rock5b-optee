// readmark: map a physical address once at load and expose its 8 bytes via /proc/readmark.
// Reading the proc file needs no cross-CPU sync, so it works while CPU0 is stuck in secure world.
#include <linux/module.h>
#include <linux/io.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
static unsigned long pa;
module_param(pa, ulong, 0444);
static void __iomem *m;
static int show(struct seq_file *s, void *v)
{
	seq_printf(s, "%#llx\n", (unsigned long long)readq(m + (pa & 0xfff)));
	return 0;
}
static int __init readmark_init(void)
{
	m = ioremap(pa & ~0xfffUL, 0x1000);
	if (!m) return -ENOMEM;
	proc_create_single("readmark", 0444, NULL, show);
	pr_info("readmark: mapped %#lx, read /proc/readmark\n", pa);
	return 0;
}
static void __exit readmark_exit(void) { remove_proc_entry("readmark", NULL); iounmap(m); }
module_init(readmark_init);
module_exit(readmark_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("expose a physical address via procfs");
