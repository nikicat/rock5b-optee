#!/bin/sh
# Build OP-TEE for the ROCK 5B from the fork's integration branch (firewall left
# to BL31 + RAM console + OTP clock ungate) with the PKCS#11 TA compiled in.
#   build.sh <out-dir> <ta-signing-key.pem>
# Memory layout matches edk2-rk3588: TZDRAM at 0x08400000, 15 MiB (the 16th MiB
# of the reserved window holds the RAM console); DRAM ranges are the ROCK 5B's
# non-secure RAM below and above 4 GiB (shared memory with Linux).
set -e
out=$(realpath -m "$1"); key=$(realpath "$2")
src=$out/src
[ -d "$src" ] || git clone -q --branch rock5b https://github.com/nikicat/optee_os "$src"
cd "$src" && git checkout -q rock5b
make -j"$(nproc)" O="$out/build" PLATFORM=rockchip-rk3588 COMPILER=gcc \
  CROSS_COMPILE="${CROSS_COMPILE-}" CROSS_COMPILE64="${CROSS_COMPILE-}" CROSS_COMPILE_core="${CROSS_COMPILE-}" CROSS_COMPILE_ta_arm64="${CROSS_COMPILE-}" \
  CFG_ARM64_core=y CFG_USER_TA_TARGETS=ta_arm64 \
  CFG_TZDRAM_START=0x08400000 CFG_TZDRAM_SIZE=0x00f00000 CFG_CORE_RESERVED_SHM=n \
  CFG_CORE_LARGE_PHYS_ADDR=y CFG_DRAM_BASE=0x09400000 CFG_DRAM_SIZE=0xd1e80000 CFG_NSEC_DDR_1_BASE=0x100000000 CFG_NSEC_DDR_1_SIZE=0x2fbc00000 \
  CFG_DT_ADDR=0 CFG_RK_SECURE_BOOT=n CFG_RK3588_FIREWALL_BY_BL31=y CFG_RAMCON=y CFG_RAMCON_BASE=0x09300000 \
  CFG_IN_TREE_EARLY_TAS=pkcs11/fd02c9da-306c-48c7-a49c-bbd827ae86ee TA_SIGN_KEY="$key" \
  CFG_TEE_CORE_LOG_LEVEL=2 CFG_TEE_TA_LOG_LEVEL=1
cat "$out/build/core/tee-header_v2.bin" "$out/build/core/tee-pager_v2.bin" "$out/build/core/tee-pageable_v2.bin" > "$out/tee-v2.bin"
cp "$out/build/core/tee-raw.bin" "$out/tee-raw.bin"
echo "boot-time image: $out/tee-raw.bin   runtime-load image: $out/tee-v2.bin"
