# rock5b-optee

Upstream OP-TEE with a built-in PKCS#11 token on a Radxa ROCK 5B (RK3588) that
boots edk2-rk3588 UEFI. The goal: a key store whose private keys root cannot
read, with import, sign and no export. Physical attacks and secure-boot fusing
are out of scope; the known remaining hole is "root rewrites the SPI flash and
reboots", which only a fused secure boot closes.

Status: works (2026-09-20). Keys imported from outside sign inside the TEE,
OpenSSL verifies, keys are non-extractable, storage survives reboots.

## Layout

| dir      | what |
|----------|------|
| `tfa/`   | build script for BL31 from [nikicat/arm-trusted-firmware `rk3588-optee`](https://github.com/nikicat/arm-trusted-firmware/tree/rk3588-optee): the TF-A edk2-rk3588 ships (worproject fork) + BL32 entry fallback + firewall region, `SPD=opteed` |
| `optee/` | build script for OP-TEE from [nikicat/optee_os `rock5b`](https://github.com/nikicat/optee_os/tree/rock5b) (= upstream master + `rk3588-firewall-by-bl31` + `ramcon`), PKCS#11 as an early TA |
| `fit/`   | `fitrepack.py`: take an edk2-rk3588 image apart and rebuild it with our BL31/OP-TEE |
| `linux/` | kernel package (`linux-aarch64-tee`), UKI config, devicetree node, cmdline flag |
| `tools/` | runtime-load loader module, RAM-console reader, marker reader, SMC probe, watchdog-guarded experiment script |

The userspace side (`tee-supplicant`, `libteec`, `libckteec`) is the AUR
package `optee-client`. edk2-rk3588 gets a `--bl32` option on
[nikicat/edk2-rk3588 `optee`](https://github.com/nikicat/edk2-rk3588/tree/optee)
so its own build can produce the same image.

## What had to change, and why

1. **The SPL passes no BL32 entry point.** Rockchip's SPL (`rk3588_spl_v1.12`)
   loads the FIT's `optee` image but hands BL31 a zero entry. Upstream TF-A
   then never starts OP-TEE. `tfa/` patch: fall back to the FIT's fixed load
   address `0x08400000` when the SPL passes nothing
   ([branch](https://github.com/nikicat/arm-trusted-firmware/tree/rk3588-optee)).
2. **OP-TEE's firewall programming hangs the core.** Upstream OP-TEE for
   rk3588 writes the DDR/DSU firewall registers itself; from S-EL1 on this
   chain the write never returns. TF-A already programs region 0 for itself,
   so it now also programs region 1 for OP-TEE (0x84..0x93 MiB) and OP-TEE
   skips its own with `CFG_RK3588_FIREWALL_BY_BL31=y`
   ([branch](https://github.com/nikicat/optee_os/tree/rk3588-firewall-by-bl31)).
   Same arrangement as Rockchip's vendor BL31.
3. **Devicetree hand-off.** TF-A's runtime-load path passes OP-TEE a DT that
   lives in BL31's secure memory; OP-TEE maps an external DT as non-secure
   and hangs on the firewall. Built with `CFG_DT_ADDR=0`.
4. **Shared memory.** The Linux driver needs OP-TEE to advertise dynamic or
   reserved shared memory; with no DRAM registered it advertised neither and
   probe failed silently. Built with the board's two RAM ranges (below and
   above 4 GiB) and `CFG_CORE_LARGE_PHYS_ADDR=y`. Registering all of
   0..16 GiB does not work: it overlaps the MMIO windows OP-TEE maps.
5. **OTP clocks.** Linux gates the OTP controller clocks at the end of boot;
   OP-TEE started afterwards times out reading the hardware unique key and
   secure storage is unavailable (the PKCS#11 TA then panics on its first
   object open). `clk_ignore_unused` on the kernel command line while OP-TEE
   is loaded at runtime.

Two more that cost a day: edk2-rk3588 FITs align data to 512 bytes, stock
`dumpimage` extracts them shifted by 0x90 (`fit/fitrepack.py` exists because
of that), and secure-world writes after the MMU is on sit in secure cache
lines a non-secure reader cannot see until cleaned (`dc cvac`).

## Two ways to run it

**Boot-time (classic):** BL31 starts the FIT's `optee` image before UEFI.
Build with `tfa/build.sh tfa-out` and `optee/build.sh optee-out ta.pem`, then

    fit/fitrepack.py extract rock-5b_UEFI_Release_v1.1.img v11
    fit/fitrepack.py build --head rock-5b_UEFI_Release_v1.1.img --uefi v11/edk2.bin \
        --atf 0x40000:tfa-out/bl31_0x00040000.bin --atf 0xff100000:tfa-out/bl31_0xff100000.bin \
        --optee optee-out/tee-raw.bin --fdt v11/fdt.bin -o FINAL.img

**Runtime load:** BL31 built with `tfa/build.sh tfa-out smcload` waits
for Linux to hand it `tee-v2.bin` (`tools/teeload`). A hang resets the board
through the hardware watchdog in 44 s instead of bricking it, which is how
everything above was found without a UART. Trust boundary is the same as
boot-time as long as secure boot is not fused.

## Flashing and recovery

From Linux: `flashcp -v IMAGE /dev/mtd0` (dd to `/dev/mtdblock0` silently
never reaches the chip on this kernel). Images end before the UEFI variable
store at 0x7C0000, so boot entries survive. Recovery: Maskrom button, USB-C to
a PC, `rkdeveloptool db rk3588_spl_loader_v1.15.113.bin`, `rkdeveloptool wl 0
IMAGE`, `rkdeveloptool rl 0 N` to read back and compare.

## Reading OP-TEE's log without a UART

OP-TEE's `CFG_RAMCON` (fork branch `ramcon`) writes the console into a 16 KiB
ring at physical `0x09300000`, the last MiB of the window EDK2 reserves for OP-TEE, left
outside the firewall region on purpose. `tools/readcon` exposes it as
`/proc/readcon`. Boot messages before the MMU is on are not captured.

## Using the token

    pkcs11-tool --module /usr/lib/libckteec.so -L
    pkcs11-tool --module /usr/lib/libckteec.so --slot 0 --init-token --label t --so-pin ...
    pkcs11-tool --module /usr/lib/libckteec.so --slot 0 --init-pin --so-pin ... --pin ...
    pkcs11-tool --module /usr/lib/libckteec.so --slot 0 --login --pin ... \
        --write-object key.der --type privkey --id 01 --usage-sign
    pkcs11-tool --module /usr/lib/libckteec.so --slot 0 --login --pin ... \
        --sign --mechanism ECDSA --id 01 -i digest -o sig.raw

Storage lives in `/var/lib/tee`, encrypted under a key derived from the
hardware unique key in OTP; it is unreadable on any other board. No RPMB on
this board, so there is no rollback protection for it.
