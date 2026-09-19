// smcprobe: OP-TEE UID SMC + read the BL31 breadcrumb at 0x093ff000.
#include <linux/module.h>
#include <linux/arm-smccc.h>
#include <linux/io.h>
static int __init smcprobe_init(void)
{
	struct arm_smccc_res r;
	void __iomem *m;
	arm_smccc_smc(0xbf00ff01, 0, 0, 0, 0, 0, 0, 0, &r);
	pr_info("smcprobe: OPTEE_SMC_CALLS_UID -> a0=%#lx a1=%#lx a2=%#lx a3=%#lx\n", r.a0, r.a1, r.a2, r.a3);
	m = ioremap(0x093ff000, 0x40);
	if (m) {
		u64 v[4]; int i;
		for (i = 0; i < 4; i++) v[i] = readq(m + 8 * i);
		pr_info("smcprobe: breadcrumb magic=%#llx bl32_pc=%#llx params_version=%#llx bl33_pc=%#llx\n", v[0], v[1], v[2], v[3]);
		iounmap(m);
	}
	return -ENODEV;
}
module_init(smcprobe_init);
MODULE_LICENSE("GPL");
