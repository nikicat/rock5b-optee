# Kernel side

`PKGBUILD` is Arch Linux ARM's `linux-aarch64` with three changes: package name
`linux-aarch64-tee` so it installs next to the stock kernel, `CONFIG_TEE=m`
`CONFIG_OPTEE=m` `CONFIG_OPTEE_INSECURE_LOAD_IMAGE=y` `CONFIG_TRUSTED_KEYS_TEE=y`,
and a UKI preset (`linux.preset`) that boots as `arch-linux-tee.efi` with the
devicetree from `uki-tee.conf`.

The devicetree only needs one extra node so the `optee` driver probes:

    cp /boot/dtbs/rockchip/rk3588-rock-5b.dtb /etc/kernel/dtb/rk3588-rock-5b-optee.dtb
    fdtput -c  /etc/kernel/dtb/rk3588-rock-5b-optee.dtb /firmware/optee
    fdtput -ts /etc/kernel/dtb/rk3588-rock-5b-optee.dtb /firmware/optee compatible linaro,optee-tz
    fdtput -ts /etc/kernel/dtb/rk3588-rock-5b-optee.dtb /firmware/optee method smc

`90-clk-optee.conf` goes to `/etc/cmdline.d/`: Linux gates the OTP controller
clocks at the end of boot, and OP-TEE loaded afterwards then times out reading
the hardware unique key.  Only needed while OP-TEE is handed over at runtime.

EDK2's boot manager loads UKIs directly (no systemd-boot), so a one-shot boot of
the tee entry is `efibootmgr -n <id>`; the entry is created with
`efibootmgr -c -d /dev/nvme0n1 -p 1 -L "Arch Linux Mainline (tee)" -l '\EFI\Linux\arch-linux-tee.efi'`.
