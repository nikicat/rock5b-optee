#!/usr/bin/env python3
"""Sign OP-TEE images for a BL31 built with OPTEE_SMC_LOAD_SIGNED (ed25519, via openssl).

  tee-sign.py keygen KEY.pem                    writes KEY.pem and KEY.pub (raw 32 bytes: OPTEE_SIG_PUBKEY)
  tee-sign.py sign KEY.pem VERSION IN OUT       IN is tee-v2.bin, OUT goes to /usr/lib/firmware/optee/tee.bin
  tee-sign.py verify KEY.pub IN                 prints the version, exits non-zero on a bad signature

Blob: "OPTEESIG" u32 hdr_version=1 u32 version (little-endian) | image | 64-byte
signature over everything before it. Matches services/spd/opteed/opteed_sig.h.
"""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

SPKI_ED25519 = bytes.fromhex("302a300506032b6570032100")  # DER prefix for a raw ed25519 public key
MAGIC = b"OPTEESIG"


def openssl(*args, data=None):
    return subprocess.run(["openssl", *args], input=data, check=True, capture_output=True).stdout


def keygen(pem):
    pem = Path(pem)
    pem.write_bytes(openssl("genpkey", "-algorithm", "ed25519"))
    pem.chmod(0o600)
    spki = openssl("pkey", "-in", pem, "-pubout", "-outform", "DER")
    assert spki.startswith(SPKI_ED25519) and len(spki) == 44
    pem.with_suffix(".pub").write_bytes(spki[-32:])


def sign(pem, version, src, dst):
    msg = MAGIC + struct.pack("<II", 1, int(version)) + Path(src).read_bytes()
    with tempfile.NamedTemporaryFile() as m:
        m.write(msg); m.flush()
        sig = openssl("pkeyutl", "-sign", "-rawin", "-inkey", pem, "-in", m.name)
    assert len(sig) == 64
    Path(dst).write_bytes(msg + sig)


def verify(pub, blob):
    raw = Path(pub).read_bytes()
    data = Path(blob).read_bytes()
    assert len(raw) == 32, "KEY.pub must be 32 raw bytes"
    assert data[:8] == MAGIC and struct.unpack_from("<I", data, 8)[0] == 1, "not a signed OP-TEE image"
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "pub.der").write_bytes(SPKI_ED25519 + raw)
        (d / "msg").write_bytes(data[:-64]); (d / "sig").write_bytes(data[-64:])
        openssl("pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", d / "pub.der", "-in", d / "msg", "-sigfile", d / "sig")
    print(struct.unpack_from("<I", data, 12)[0])


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    try:
        {"keygen": keygen, "sign": sign, "verify": verify}[cmd](*args)
    except (KeyError, TypeError):
        sys.exit(__doc__)
    except subprocess.CalledProcessError as e:
        sys.exit(e.stderr.decode().strip() or f"openssl failed: {e.returncode}")
