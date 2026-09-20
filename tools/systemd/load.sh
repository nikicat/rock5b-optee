#!/bin/sh
# Hand /usr/lib/firmware/optee/tee.bin to BL31 (built with OPTEE_ALLOW_SMC_LOAD).
# The hand-over blocks in an SMC until OP-TEE finished its init; if OP-TEE hangs
# the calling core is gone for good, so the watchdog is armed (never fed) until
# the hand-over returns: a hang resets the board in ~44 s instead of stranding it.
set -e
[ -e /dev/tee0 ] && exit 0                       # already loaded this boot
exec 3>/dev/watchdog0
taskset -c 0 modprobe teeload 2>/dev/null || true  # one-shot module: ENODEV is its normal exit
# BL31 initialised OP-TEE on cpu0 only; cycling the others runs its CPU-on hook
for c in /sys/devices/system/cpu/cpu[1-9]*/online; do echo 0 > "$c"; echo 1 > "$c"; done
# udev may have inserted the driver during the hand-over (probe failed: no OP-TEE
# yet) or not at all; either way a fresh insert now probes against a live OP-TEE
modprobe -r optee 2>/dev/null || true
modprobe optee
printf V >&3; exec 3>&-                          # magic close: disarm
