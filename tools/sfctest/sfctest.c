// sfctest: read (and optionally volatile-write) the SPI NOR status registers through the
// kernel's own SFC driver, via spi-mem. Loads, prints to dmesg, exits with ENODEV.
//   insmod sfctest.ko            -> read ID, SR1, SR2, SR3
//   insmod sfctest.ko sr1=0x18 sr2=0x03 -> 50h + 01h [sr1 sr2], then read back
#include <linux/module.h>
#include <linux/spi/spi.h>
#include <linux/spi/spi-mem.h>
#include <linux/delay.h>
static int sr1 = -1, sr2 = -1, wren = 0x50;
module_param(sr1, int, 0444);
module_param(wren, int, 0444);
module_param(sr2, int, 0444);
static char *devname = "spi5.0";
module_param(devname, charp, 0444);

static int rd(struct spi_mem *m, u8 opcode, u8 *buf, int n)
{
	struct spi_mem_op op = SPI_MEM_OP(SPI_MEM_OP_CMD(opcode, 1), SPI_MEM_OP_NO_ADDR,
					  SPI_MEM_OP_NO_DUMMY, SPI_MEM_OP_DATA_IN(n, buf, 1));
	return spi_mem_exec_op(m, &op);
}
static int wr(struct spi_mem *m, u8 opcode, const u8 *buf, int n)
{
	struct spi_mem_op op = SPI_MEM_OP(SPI_MEM_OP_CMD(opcode, 1), SPI_MEM_OP_NO_ADDR,
					  SPI_MEM_OP_NO_DUMMY, SPI_MEM_OP_DATA_OUT(n, buf, 1));
	if (!n) op.data.dir = SPI_MEM_NO_DATA;
	return spi_mem_exec_op(m, &op);
}
static u8 *b;	/* kmalloc'd: spi-mem refuses stack buffers */
static void dump(struct spi_mem *m, const char *tag)
{
	memset(b, 0, 8);
	rd(m, 0x9f, b, 3); rd(m, 0x05, b + 3, 1); rd(m, 0x35, b + 4, 1); rd(m, 0x15, b + 5, 1);
	pr_info("sfctest: %s id=%02x%02x%02x SR1=%#04x SR2=%#04x SR3=%#04x\n", tag, b[0], b[1], b[2], b[3], b[4], b[5]);
}
static int __init sfctest_init(void)
{
	struct device *d = bus_find_device_by_name(&spi_bus_type, NULL, devname);
	struct spi_mem mem = {};
	u8 *buf, *s1;
	int i, ret;
	if (!d) { pr_err("sfctest: %s not found\n", devname); return -ENODEV; }
	b = kzalloc(16, GFP_KERNEL); buf = b + 8; s1 = b + 12;
	mem.spi = to_spi_device(d);
	dump(&mem, "before");
	if (sr1 >= 0 && sr2 >= 0) {
		buf[0] = sr1; buf[1] = sr2;
		ret = wr(&mem, wren, NULL, 0);				/* 50h: write enable for the volatile status register; 06h: normal */
		pr_info("sfctest: %02xh -> %d\n", wren, ret);
		ret = wr(&mem, 0x01, buf, 2);				/* WRSR: SR1, SR2 */
		pr_info("sfctest: 01h [%02x %02x] -> %d\n", buf[0], buf[1], ret);
		for (i = 0; i < 100; i++) { rd(&mem, 0x05, s1, 1); if (!(*s1 & 1)) break; udelay(100); }
		dump(&mem, "after ");
	}
	put_device(d);
	kfree(b);
	return -ENODEV;
}
module_init(sfctest_init);
MODULE_LICENSE("GPL");
