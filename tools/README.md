# tools

Out-of-tree kernel modules (`make -C /usr/lib/modules/$(uname -r)/build M=$PWD modules`):

- `teeload/`: hands `/lib/firmware/optee/tee.bin` to a BL31 built with
  `OPTEE_ALLOW_SMC_LOAD=1`; `tee-experiment.sh IMAGE` wraps it with the
  hardware watchdog and cycles cpu1-7 so the dispatcher initialises them.
  `systemd/` is the production form of that (`optee-load.service`,
  `/etc/optee/load.sh`), `dkms.conf` keeps the modules built across kernels
  (`/usr/src/optee-tools-1.0`).
- `tee-sign.py`: keygen / sign / verify for the signed SMC load
  (`OPTEE_SMC_LOAD_SIGNED`); `tee-sign-selftest.sh <tf-a src> <tee-v2.bin>`
  compiles BL31's verifier natively and checks what it accepts and rejects.
- `check-secp256k1.sh`: generate, sign, import on the token with secp256k1,
  verified against OpenSSL (`PIN=... check-secp256k1.sh` on the board).
- `readcon/`: `/proc/readcon`, the OP-TEE RAM console (`pa=0x9300000`).
- `readmark/`: `/proc/readmark`, one 64-bit word at a physical address, plus
  `poller.py` to log it once a second. Loading a module while cpu0 sits in the
  secure world hangs (the kernel waits for all CPUs), so load readers first.
- `smcprobe/`: prints the raw reply to the OP-TEE UID SMC and BL31's
  breadcrumb (what the SPL passed as BL32/BL33 entry).
