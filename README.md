# rock5b-optee

Upstream OP-TEE with a built-in PKCS#11 token on a Radxa ROCK 5B (RK3588) that
boots edk2-rk3588 UEFI. The goal: a key store whose private keys root cannot
read, with import, sign and no export. Physical attacks are out of scope. Two
root-level holes remain open in the current setup; see Hardening below.

Status: works (2026-09-20). Keys imported from outside sign inside the TEE,
OpenSSL verifies, keys are non-extractable, storage survives reboots.

## Layout

| dir      | what |
|----------|------|
| `tfa/`   | build script for BL31 from [nikicat/arm-trusted-firmware `rk3588-optee-upstream`](https://github.com/nikicat/arm-trusted-firmware/tree/rk3588-optee-upstream): the upstream commit edk2-rk3588 master pins + edk2's patch set + BL32 entry fallback + firewall region, `SPD=opteed` |
| `optee/` | build script for OP-TEE from [nikicat/optee_os `rock5b`](https://github.com/nikicat/optee_os/tree/rock5b) (= upstream master + `rk3588-firewall-by-bl31` + `ramcon` + `rk3588-otp-clocks`), PKCS#11 as an early TA |
| `fit/`   | `fitrepack.py`: take an edk2-rk3588 image apart and rebuild it with our BL31/OP-TEE |
| `linux/` | kernel package (`linux-aarch64-tee`), UKI config, devicetree node |
| `tools/` | runtime-load loader module, RAM-console reader, marker reader, SMC probe, watchdog-guarded experiment script |

The userspace side (`tee-supplicant`, `libteec`, `libckteec`) is the AUR
package `optee-client`. edk2-rk3588 gets a `--bl32` option on
[nikicat/edk2-rk3588 `optee`](https://github.com/nikicat/edk2-rk3588/tree/optee)
so its own build can produce the same image.

## What had to change, and why

1. **The SPL passes no BL32 entry point, and garbage arguments.** Rockchip's
   SPL (`rk3588_spl_v1.12`) loads the FIT's `optee` image but hands BL31 a
   zero entry and leaves the four BL32 argument words uninitialised (leftover
   code and addresses). Upstream TF-A then never starts OP-TEE, and with only
   the entry fixed it starts it in 32-bit mode, because the OP-TEE dispatcher
   reads the first argument as the AArch32/AArch64 selector. `tfa/` patch:
   fall back to the FIT's fixed load address `0x08400000` and clear the
   arguments when the SPL passes nothing.
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
5. **OTP clocks.** The secure OTP controller shares three clock gates
   (arbiter, auto-read, phy) with the non-secure one, and Linux switches them
   off as unused at the end of its boot. OP-TEE started afterwards timed out
   reading the hardware unique key and had no secure storage (the PKCS#11 TA
   then panics on its first object open). The OP-TEE driver now ungates them
   before every OTP access (fork branch `rk3588-otp-clocks`).

Two more that cost a day: edk2-rk3588 FITs align data to 512 bytes, stock
`dumpimage` extracts them shifted by 0x90 (`fit/fitrepack.py` exists because
of that), and secure-world writes after the MMU is on sit in secure cache
lines a non-secure reader cannot see until cleaned (`dc cvac`).

## Two ways to run it

**Boot-time (classic):** BL31 starts the FIT's `optee` image before UEFI.
Build with `tfa/build.sh tfa-out` and `optee/build.sh optee-out ta.pem`, then

    fit/fitrepack.py extract rock-5b_UEFI_Release_v1.1.img v11
    fit/fitrepack.py build --head rock-5b_UEFI_Release_v1.1.img --uefi v11/edk2.bin \
        --atf 0x40000:tfa-out/bl31_0x00040000.bin --atf 0x5f000:tfa-out/bl31_0x0005f000.bin \
        --atf 0xff100000:tfa-out/bl31_0xff100000.bin \
        --optee optee-out/tee-raw.bin --fdt v11/fdt.bin -o FINAL.img

**Runtime load:** BL31 built with `tfa/build.sh tfa-out smcload` waits
for Linux to hand it `tee-v2.bin` (`tools/teeload`; `tools/systemd/` has the
boot unit that does it automatically, and `tools/dkms.conf` keeps the modules
built across kernel upgrades). A hang resets the board
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

## Hardening

What holds today: the DDR firewall keeps secure memory unreadable, the storage
is encrypted under a key that never leaves the chip, and the PKCS#11 code is
compiled into OP-TEE, so root cannot add trusted applications without the
signing key. What does not hold: root can still replace the secure world
itself, and the replacement runs with the same hardware key.

1. **Root swaps the OP-TEE image.** In the runtime-load setup Linux hands
   `/usr/lib/firmware/optee/tee.bin` to BL31 at boot. Fix: the boot-time
   chain (OP-TEE in the FIT, TF-A built without `OPTEE_ALLOW_SMC_LOAD`).
   Done 2026-09-20 together with 3 below; the first attempt hung because of
   the uninitialised SPL arguments described above.
2. **Root rewrites the SPI flash.** `flashcp` works from Linux, which is how
   this project avoided opening the case, and it works for an attacker too.
   Fix: TF-A's `sgrf_init()` assigns peripherals to the secure world at every
   boot; marking the flash controller secure-only makes the firmware read-only
   for Linux. Reversible (flash a non-locking TF-A from maskrom), unlike
   Rockchip's fused secure boot, which burns a key hash into OTP with closed
   tools and bricks the board on a mistake. The lock only holds while the
   locking firmware is installed, so every later *firmware* update (OS updates
   never touch the flash) needs one of:
   - maskrom, always available;
   - a header pin TF-A reads at boot, leaving the flash writable for that boot
     (the maskrom button cannot serve: it grounds the flash clock);
   - a signed unlock: a TA verifies a signature made off-board over a fresh
     nonce, OP-TEE asks TF-A to open the flash until the next reboot, then
     `flashcp` over ssh. The register write belongs in TF-A; S-EL1 firewall
     writes hang on this chain.
3. **Build hardening** once 1 is in: `CFG_REE_FS_TA=n` (needs
   `CFG_SECSTOR_TA_MGMT_PTA=n` too), drop the loader and reader modules and
   the boot unit. Done; `CFG_RAMCON` stays on until the next firmware update,
   it is the only log there is.
4. **Operational**: one PIN per service, kept out of shell history; the TA
   signing key and the originals of imported keys stay off the board. Keys
   generated inside the token cannot be backed up.

Still open after all of that: a root process holding a service's PIN can use
that key (no audit log or rate limit in the token); root can delete or restore
old copies of `/var/lib/tee` (no RPMB, no rollback protection); bugs in TF-A
or OP-TEE; anything physical.
