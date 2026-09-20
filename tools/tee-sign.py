#!/usr/bin/env python3
"""Sign OP-TEE images for a BL31 built with OPTEE_SMC_LOAD_SIGNED (ed25519).

  tee-sign.py sign KEY VERSION IN OUT          KEY is a PEM file or gpg:<fingerprint> of an Ed25519 signing subkey
                                               (signed through gpg-agent); IN is tee-v2.bin, OUT goes to
                                               /usr/lib/firmware/optee/tee.bin
  tee-sign.py pubkey KEY OUT.pub               raw 32-byte public key: OPTEE_SIG_PUBKEY for the BL31 build
  tee-sign.py verify KEY.pub IN                prints the version, exits non-zero on a bad signature
  tee-sign.py keygen KEY.pem                   a file key (tests); production keys are gpg subkeys

Blob: "OPTEESIG" u32 hdr_version=1 u32 version (little-endian) | image | 64-byte
ed25519 signature over the SHA-512 of everything before it. Matches
services/spd/opteed/opteed_sig.h.
"""
import hashlib
import re
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


def sign(key, version, src, dst):
    msg = MAGIC + struct.pack("<II", 1, int(version)) + Path(src).read_bytes()
    sig = sign_digest(key, hashlib.sha512(msg).digest(), f"OP-TEE image version {version}")
    Path(dst).write_bytes(msg + sig)


def verify(pub, blob):
    raw = Path(pub).read_bytes()
    data = Path(blob).read_bytes()
    assert len(raw) == 32, "KEY.pub must be 32 raw bytes"
    assert data[:8] == MAGIC and struct.unpack_from("<I", data, 8)[0] == 1, "not a signed OP-TEE image"
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "pub.der").write_bytes(SPKI_ED25519 + raw)
        (d / "msg").write_bytes(hashlib.sha512(data[:-64]).digest()); (d / "sig").write_bytes(data[-64:])
        openssl("pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", d / "pub.der", "-in", d / "msg", "-sigfile", d / "sig")
    print(struct.unpack_from("<I", data, 12)[0])



# --- keys: a KEY argument is either a PEM file or "gpg:<fingerprint>" of an Ed25519 signing (sub)key;
# gpg signing goes through gpg-agent's raw interface, so the key can live in the agent or on a card.
def gpg(*args, data=None):
    return subprocess.run(["gpg", *args], input=data, check=True, capture_output=True).stdout


def gpg_grip(fpr):
    prev = None
    for line in gpg("--list-keys", "--with-colons", "--with-keygrip", fpr).decode().splitlines():
        f = line.split(":")
        if f[0] == "grp" and prev == fpr.upper():
            return f[9]
        if f[0] == "fpr":
            prev = f[9]
    sys.exit(f"no keygrip for {fpr}")


def gpg_pub(fpr):
    """Raw 32-byte Ed25519 public key of the (sub)key with this fingerprint."""
    packets = gpg("--list-packets", "--verbose", data=gpg("--export", fpr)).decode()
    point = None	# pkey lines come before the keyid line of the same packet
    for line in packets.splitlines():
        line = line.strip()
        if line.startswith("pkey[1]:"):
            point = bytes.fromhex(line.split()[1])
        elif line.startswith("keyid:") and line.split()[1] == fpr.upper()[-16:]:
            assert point and point[0] == 0x40 and len(point) == 33, "not an Ed25519 key"
            return point[1:]
    sys.exit(f"no Ed25519 key {fpr} in the keyring")


def gpg_sign(fpr, digest, desc):
    esc = desc.replace("%", "%25").replace("+", "%2B").replace(" ", "+")
    raw = subprocess.run(["gpg-connect-agent", f"SIGKEY {gpg_grip(fpr)}", f"SETKEYDESC {esc}",
                          f"SETHASH --hash=sha512 {digest.hex()}", "PKSIGN", "/bye"], check=True, capture_output=True).stdout
    # one percent-escaped "D " line; --decode would split the binary at newline bytes
    data = [l[2:] for l in raw.split(b"\n") if l.startswith(b"D ")]
    if not data or b"ERR" in raw:
        sys.exit("gpg-agent refused to sign: " + raw.decode(errors="replace").strip())
    out = re.sub(rb"%([0-9A-Fa-f]{2})", lambda h: bytes([int(h.group(1), 16)]), b"".join(data))
    m = re.search(rb"\(1:r(\d+):", out)
    r_len = int(m.group(1)); r = out[m.end():m.end() + r_len]
    m2 = re.search(rb"\(1:s(\d+):", out[m.end() + r_len:])
    s = out[m.end() + r_len + m2.end():m.end() + r_len + m2.end() + int(m2.group(1))]
    return r.rjust(32, b"\0") + s.rjust(32, b"\0")


def sign_digest(key, digest, desc):
    if key.startswith("gpg:"):
        return gpg_sign(key[4:], digest, desc)
    with tempfile.NamedTemporaryFile() as m:
        m.write(digest); m.flush()
        sig = openssl("pkeyutl", "-sign", "-rawin", "-inkey", key, "-in", m.name)
    assert len(sig) == 64
    return sig


def pubkey(key, out):
    """Write the raw 32-byte public key of KEY (PEM file or gpg:<fpr>) to OUT: what the BL31 build takes."""
    if key.startswith("gpg:"):
        raw = gpg_pub(key[4:])
    else:
        spki = openssl("pkey", "-in", key, "-pubout", "-outform", "DER")
        assert spki.startswith(SPKI_ED25519) and len(spki) == 44
        raw = spki[-32:]
    Path(out).write_bytes(raw)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    try:
        {"keygen": keygen, "sign": sign, "pubkey": pubkey, "verify": verify}[cmd](*args)
    except (KeyError, TypeError):
        sys.exit(__doc__)
    except subprocess.CalledProcessError as e:
        sys.exit(e.stderr.decode().strip() or f"openssl failed: {e.returncode}")
