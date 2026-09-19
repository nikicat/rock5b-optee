// readcon: expose OP-TEE's RAM console (struct ramcon at physical address pa) as /proc/readcon.
#include <linux/module.h>
#include <linux/io.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#define RAMCON_SIZE 16384
static unsigned long pa; module_param(pa, ulong, 0444);
static void __iomem *m;
static int show(struct seq_file *s, void *v)
{
	u64 magic = readq(m), head = readq(m + 8); u64 start = head > RAMCON_SIZE ? head - RAMCON_SIZE : 0, i;
	seq_printf(s, "magic=%#llx head=%llu\n", magic, head);
	for (i = start; i < head; i++) seq_putc(s, readb(m + 16 + (i % RAMCON_SIZE)));
	return 0;
}
static int __init readcon_init(void)
{
	m = ioremap(pa & ~0xfffUL, 0x1000 * 6); if (!m) return -ENOMEM;
	m += (pa & 0xfff); proc_create_single("readcon", 0444, NULL, show); return 0;
}
static void __exit readcon_exit(void) { remove_proc_entry("readcon", NULL); iounmap((void __iomem *)((unsigned long)m & ~0xfffUL)); }
module_init(readcon_init); module_exit(readcon_exit);
MODULE_LICENSE("GPL"); MODULE_DESCRIPTION("read OP-TEE RAM console");
