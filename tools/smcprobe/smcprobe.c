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
	m = ioremap(0x093ff000, 0x80);
	if (m) {
		static const char *const name[12] = { "magic", "params_version", "bl32_pc", "bl32_spsr", "bl32_attr",
			"bl32_arg0", "bl32_arg1", "bl32_arg2", "bl32_arg3", "bl33_pc", "bl33_arg0", "bl33_arg1" };
		int i;
		for (i = 0; i < 12; i++)
			pr_info("smcprobe: breadcrumb %s=%#llx\n", name[i], readq(m + 8 * i));
		iounmap(m);
	}
	return -ENODEV;
}
module_init(smcprobe_init);
MODULE_LICENSE("GPL");
