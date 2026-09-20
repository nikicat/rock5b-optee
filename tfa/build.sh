#!/bin/sh
# Build BL31 for the ROCK 5B from the fork branch: the TF-A commit edk2-rk3588
# master pins, edk2's own patch set, and our rk3588 changes (BL32 entry
# fallback, firewall region for BL32, SPI NOR write-protect at boot). Splits bl31.elf into the per-segment
# files the FIT wants (three segments on this TF-A).
#   build.sh <out-dir> [smcload | signed <key.pub> <min-version>]
# "smcload" builds the variant where Linux hands OP-TEE over at runtime;
# "signed" is that variant with the ed25519 check (tools/tee-sign.py).
set -e
out=$(realpath -m "$1"); mode=${2:-boot}
src=$out/src
[ -d "$src" ] || git clone -q --branch rk3588-optee-upstream https://github.com/nikicat/arm-trusted-firmware "$src"
cd "$src" && git checkout -q rk3588-optee-upstream
extra=""
case $mode in
smcload) extra="OPTEE_ALLOW_SMC_LOAD=1 PLAT_XLAT_TABLES_DYNAMIC=1" ;;
signed) extra="OPTEE_ALLOW_SMC_LOAD=1 PLAT_XLAT_TABLES_DYNAMIC=1 OPTEE_SMC_LOAD_SIGNED=1 OPTEE_SIG_PUBKEY=$(realpath "$3") OPTEE_SIG_MIN_VERSION=$4" ;;
esac
# FWUPD_DIR, FWUPD_PUBKEY, FWUPD_VERSION in the environment add the power-on self-updater (rk3588-fwupd)
[ -z "${FWUPD_DIR-}" ] || extra="$extra FWUPD_DIR=$(realpath "$FWUPD_DIR") FWUPD_PUBKEY=$(realpath "$FWUPD_PUBKEY") FWUPD_VERSION=$FWUPD_VERSION"
make -j"$(nproc)" PLAT=rk3588 DEBUG=0 SPD=opteed RK3588_SPINOR_LOCK=1 CROSS_COMPILE="${CROSS_COMPILE-}" BUILD_BASE="$out/build" $extra bl31
python3 - "$out" <<'PY'
import sys
from elftools.elf.elffile import ELFFile
out = sys.argv[1]
f = ELFFile(open(f"{out}/build/rk3588/release/bl31/bl31.elf", "rb"))
for seg in f.iter_segments():
    if seg.header.p_type != "PT_LOAD" or seg.header.p_filesz == 0: continue
    n = f"{out}/bl31_0x{seg.header.p_paddr:08x}.bin"; open(n, "wb").write(seg.data()); print(n, seg.header.p_filesz)
PY
