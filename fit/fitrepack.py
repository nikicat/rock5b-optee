#!/usr/bin/env python3
"""FIT surgery for edk2-rk3588 images (ROCK 5B).

Rockchip's mkimage places external FIT data at round_up(fdt totalsize, 512) and
aligns every image to 512 bytes; upstream dumpimage assumes 4, so it extracts
every blob shifted by 0x90.  This tool extracts with the right base, verifies
each blob against the FIT's own sha256, and rebuilds a FIT that both readers
agree on (mkimage -E -B 0x200, nvdata node spliced back, header padded to 512).

  fitrepack.py extract <image-or-fit> <outdir>
  fitrepack.py build --head <edk2 image> --uefi F --atf 0x40000:F [--atf ADDR:F ...]
                     [--optee F] --fdt F -o out.img
"""
import argparse, hashlib, os, struct, subprocess, sys

FIT_OFF = 0x100000            # FIT lives 1 MiB into the SPI image
NVDATA_POS, NVDATA_SIZE, NVDATA_LOAD = 0x6C0000, 0x30000, 0x7C0000

def fdtget(fit, *args):
    r = subprocess.run(["fdtget", *args[:1], fit, *args[1:]], capture_output=True, text=True)
    return r.stdout.split() if r.returncode == 0 else []

def total(b): return struct.unpack(">I", b[4:8])[0]

def images(fit):
    return fdtget(fit, "-l", "/images")

def blob(fit, b, name, align):
    base = (total(b) + align - 1) & ~(align - 1)
    off = int(fdtget(fit, "-tx", f"/images/{name}", "data-offset")[0], 16)
    size = int(fdtget(fit, "-tx", f"/images/{name}", "data-size")[0], 16)
    want = "".join("%02x" % int(x, 16) for x in fdtget(fit, "-tbx", f"/images/{name}/hash", "value"))
    d = b[base + off:base + off + size]
    return d, hashlib.sha256(d).hexdigest() == want

def extract(src, outdir):
    b = open(src, "rb").read()
    if b[:4] != b"\xd0\x0d\xfe\xed":
        b = b[FIT_OFF:]
    fit = os.path.join(outdir, "orig.itb"); os.makedirs(outdir, exist_ok=True); open(fit, "wb").write(b)
    for name in images(fit):
        if not fdtget(fit, "-tx", f"/images/{name}", "data-offset"): continue   # nvdata: a flash window, no data
        d, ok = blob(fit, b, name, 512)
        if not ok: sys.exit(f"{name}: hash mismatch at 512-byte base (not a Rockchip-style FIT?)")
        load = fdtget(fit, "-tx", f"/images/{name}", "load") or ["-"]
        open(os.path.join(outdir, f"{name}.bin"), "wb").write(d)
        print(f"{name:8} {len(d):9d} bytes  load={load[0]}  sha256 ok")

def node(name, file, typ, os_, load):
    l = f" load = <{load:#x}>;" if load is not None else ""; o = f' os = "{os_}";' if os_ else ""
    return (f'\t\t{name} {{ description = "{name}"; data = /incbin/("{file}"); type = "{typ}"; '
            f'arch = "arm64";{o} compression = "none";{l} hash {{ algo = "sha256"; }}; }};\n')

def build(a):
    ap = os.path.abspath
    a.uefi, a.fdt, a.head = ap(a.uefi), ap(a.fdt), ap(a.head)
    if a.optee: a.optee = ap(a.optee)
    atf = [(f"atf-{i+1}", ap(f), int(addr, 16)) for i, (addr, f) in enumerate(x.split(":", 1) for x in a.atf)]
    imgs = node("edk2", a.uefi, "standalone", "EDK2", 0x200000)
    for n, f, l in atf: imgs += node(n, f, "firmware", "arm-trusted-firmware", l)
    loadables = ["edk2"] + [n for n, _, _ in atf[1:]]
    if a.optee: imgs += node("optee", a.optee, "firmware", "op-tee", 0x8400000); loadables.append("optee")
    imgs += node("fdt", a.fdt, "flat_dt", None, None)
    ld = ", ".join(f'"{x}"' for x in loadables)
    its = ('/dts-v1/;\n/ {\n\tdescription = "FIT Image with ATF/OP-TEE/UEFI";\n\t#address-cells = <1>;\n'
           f'\timages {{\n{imgs}\t}};\n\tconfigurations {{\n\t\tdefault = "conf";\n'
           f'\t\tconf {{ description = "rock-5b"; rollback-index = <0x0>; firmware = "atf-1"; loadables = {ld}; fdt = "fdt"; }};\n\t}};\n}};\n')
    its_path = a.output + ".its"; open(its_path, "w").write(its)
    tmp = a.output + ".tmp.itb"
    r = subprocess.run(["mkimage", "-f", its_path, "-E", "-B", "0x200", tmp], capture_output=True, text=True)
    if r.returncode: sys.exit("mkimage failed:\n" + r.stderr)
    b = open(tmp, "rb").read(); t = total(b); assert t % 512 == 0
    s, data = b[:t], b[t:]; sdtb = a.output + ".hdr.dtb"; open(sdtb, "wb").write(s)
    for c in [["-c", "/images/nvdata"], ["-ts", "/images/nvdata", "description", "UEFI Non-Volatile Data"],
              ["-tx", "/images/nvdata", "data-position", f"{NVDATA_POS:#x}"], ["-tx", "/images/nvdata", "data-size", f"{NVDATA_SIZE:#x}"],
              ["-ts", "/images/nvdata", "type", "standalone"], ["-ts", "/images/nvdata", "arch", "arm64"],
              ["-ts", "/images/nvdata", "compression", "none"], ["-tx", "/images/nvdata", "load", f"{NVDATA_LOAD:#x}"],
              ["-ts", "/configurations/conf", "loadables", *loadables, "nvdata"]]:
        subprocess.run(["fdtput", c[0], sdtb, *c[1:]], check=True)
    s = open(sdtb, "rb").read(); t2 = total(s); s = s[:t2]; t3 = (t2 + 511) & ~511
    s = s + b"\0" * (t3 - t2); s = s[:4] + struct.pack(">I", t3) + s[8:]   # both 4- and 512-aligned readers agree
    out = s + data; fit = a.output + ".itb"; open(fit, "wb").write(out)
    for align in (4, 512):
        for n in ["edk2"] + [n for n, _, _ in atf] + (["optee"] if a.optee else []) + ["fdt"]:
            if not blob(fit, out, n, align)[1]: sys.exit(f"{n}: verification failed at align {align}")
    assert len(out) < NVDATA_POS, "FIT would overlap the UEFI variable store"
    head = open(a.head, "rb").read()[:FIT_OFF]
    open(a.output, "wb").write(head + out)
    for f in (tmp, sdtb): os.unlink(f)
    print(f"{a.output}: FIT {len(out)} bytes, loadables {loadables}, verified at 4 and 512")

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sp = p.add_subparsers(dest="cmd", required=True)
e = sp.add_parser("extract"); e.add_argument("src"); e.add_argument("outdir")
b = sp.add_parser("build"); b.add_argument("--head", required=True, help="edk2-rk3588 image whose first MiB (GPT + idblock) is reused")
b.add_argument("--uefi", required=True); b.add_argument("--atf", action="append", required=True, help="ADDR:FILE, first one is the BL31 entry segment")
b.add_argument("--optee"); b.add_argument("--fdt", required=True); b.add_argument("-o", "--output", required=True)
a = p.parse_args()
extract(a.src, a.outdir) if a.cmd == "extract" else build(a)
