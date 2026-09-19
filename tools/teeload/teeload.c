// teeload: hand /lib/firmware/optee/tee.bin to TF-A's OP-TEE dispatcher via
// OPTEE_SMC_CALL_LOAD_IMAGE (needs a BL31 built with OPTEE_ALLOW_SMC_LOAD=1).
// The SMC returns only after OP-TEE finished its init, so a hang stays in here.
#include <linux/module.h>
#include <linux/firmware.h>
#include <linux/slab.h>
#include <linux/arm-smccc.h>

#define OPTEE_SMC_CALLS_UID       0xbf00ff01
#define OPTEE_SMC_CALL_LOAD_IMAGE 0xbf000002
/* OPTEE_MSG_IMAGE_LOAD_UID, what BL31 answers while it is willing to load */
#define LOAD_UID0 0xa3fbeab1

static int __init teeload_init(void)
{
	const struct firmware *fw;
	struct arm_smccc_res r;
	void *buf; phys_addr_t pa; u64 sz; int rc;

	arm_smccc_smc(OPTEE_SMC_CALLS_UID, 0, 0, 0, 0, 0, 0, 0, &r);
	pr_info("teeload: UID before load a0=%#lx a1=%#lx a2=%#lx a3=%#lx\n", r.a0, r.a1, r.a2, r.a3);
	if (r.a0 != LOAD_UID0) {
		pr_err("teeload: BL31 is not in image-load state, refusing\n");
		return -ENODEV;
	}
	rc = request_firmware(&fw, "optee/tee.bin", NULL);
	if (rc) { pr_err("teeload: request_firmware: %d\n", rc); return rc; }
	buf = kmemdup(fw->data, fw->size, GFP_KERNEL | GFP_DMA);
	sz = fw->size; release_firmware(fw);
	if (!buf) return -ENOMEM;
	pa = virt_to_phys(buf);
	pr_info("teeload: loading %llu bytes from pa %pa\n", sz, &pa);
	arm_smccc_smc(OPTEE_SMC_CALL_LOAD_IMAGE, upper_32_bits(sz), lower_32_bits(sz),
		      upper_32_bits(pa), lower_32_bits(pa), 0, 0, 0, &r);
	pr_info("teeload: LOAD_IMAGE returned a0=%#lx\n", r.a0);
	kfree(buf);
	arm_smccc_smc(OPTEE_SMC_CALLS_UID, 0, 0, 0, 0, 0, 0, 0, &r);
	pr_info("teeload: UID after load a0=%#lx a1=%#lx a2=%#lx a3=%#lx\n", r.a0, r.a1, r.a2, r.a3);
	return -ENODEV; /* one-shot, never stays loaded */
}
module_init(teeload_init);
MODULE_LICENSE("GPL");
