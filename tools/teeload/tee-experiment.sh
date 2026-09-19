#!/bin/sh
# tee-experiment.sh <tee-v2.bin>: hand an OP-TEE image to TF-A under watchdog cover.
# A hang anywhere leaves the watchdog unfed and the board resets itself (~44 s).
set -e
img=$1; [ -f "$img" ] || { echo "usage: $0 <tee-v2.bin>"; exit 1; }
sudo install -Dm644 "$img" /lib/firmware/optee/tee.bin
sudo rmmod optee 2>/dev/null || true
sudo python3 - <<'PY'
import subprocess, os, glob
wd = open("/dev/watchdog0", "wb", buffering=0)          # armed; driver-fixed 44 s
feed = lambda: wd.write(b"\0")
print("watchdog armed", flush=True)
rc = subprocess.run(["taskset", "-c", "0", "sh", "-c", "insmod /home/zxc/src/teeload/teeload-$(uname -r).ko"]).returncode
feed(); print("loader returned rc", rc, "(ENODEV is expected; see dmesg)", flush=True)
# TF-A initialised OP-TEE on cpu0 only; cycle the others so the CPU-on hook does theirs
for c in sorted(glob.glob("/sys/devices/system/cpu/cpu[1-9]*/online")):
    open(c, "w").write("0"); open(c, "w").write("1"); feed(); print("cycled", c.split("/")[-2], flush=True)
rc = subprocess.run(["modprobe", "optee"]).returncode; feed()
print("modprobe optee rc", rc, flush=True)
wd.write(b"V"); wd.close(); print("watchdog disarmed", flush=True)
PY
sleep 3
sudo dmesg | grep -i "teeload\|optee" | tail -8
ls -l /dev/tee0 /dev/teepriv0 2>&1; systemctl is-active tee-supplicant@teepriv0 || true
