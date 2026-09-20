# Boot unit for the runtime-load setup

`optee-load.service` runs `load.sh` early in boot: it hands
`/usr/lib/firmware/optee/tee.bin` to a BL31 built with
`OPTEE_ALLOW_SMC_LOAD=1`, under cover of the hardware watchdog, then cycles
the secondary CPUs so the dispatcher initialises them and re-probes the
`optee` driver. `modules-load.d` / `modprobe.d` snippets load the RAM
console reader as `/proc/readcon`.

Modules come from `../dkms.conf`: copy `tools/` to
`/usr/src/optee-tools-1.0` and `dkms install optee-tools/1.0`.

Install: `load.sh` to `/etc/optee/`, the unit to `/etc/systemd/system/`,
`systemctl enable optee-load`, the two `.conf` files to their directories.
