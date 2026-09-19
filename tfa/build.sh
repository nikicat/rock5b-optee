#!/bin/sh
# Build BL31 for the ROCK 5B from the fork branch: the TF-A commit edk2-rk3588
# master pins, edk2's own patch set, and our two rk3588 changes (BL32 entry
# fallback, firewall region for BL32). Splits bl31.elf into the per-segment
# files the FIT wants (three segments on this TF-A).
#   build.sh <out-dir> [smcload]
# "smcload" builds the variant where Linux hands OP-TEE over at runtime.
set -e
out=$(realpath -m "$1"); mode=${2:-boot}
src=$out/src
[ -d "$src" ] || git clone -q --branch rk3588-optee-upstream https://github.com/nikicat/arm-trusted-firmware "$src"
cd "$src" && git checkout -q rk3588-optee-upstream
extra=""; [ "$mode" = smcload ] && extra="OPTEE_ALLOW_SMC_LOAD=1 PLAT_XLAT_TABLES_DYNAMIC=1"
make -j"$(nproc)" PLAT=rk3588 DEBUG=0 SPD=opteed CROSS_COMPILE="${CROSS_COMPILE-}" BUILD_BASE="$out/build" $extra bl31
python3 - "$out" <<'PY'
import sys
from elftools.elf.elffile import ELFFile
out = sys.argv[1]
f = ELFFile(open(f"{out}/build/rk3588/release/bl31/bl31.elf", "rb"))
for seg in f.iter_segments():
    if seg.header.p_type != "PT_LOAD" or seg.header.p_filesz == 0: continue
    n = f"{out}/bl31_0x{seg.header.p_paddr:08x}.bin"; open(n, "wb").write(seg.data()); print(n, seg.header.p_filesz)
PY
