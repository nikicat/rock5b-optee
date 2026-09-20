#!/bin/sh
# Prove the token does secp256k1: generate, sign a 32-byte digest, verify with
# OpenSSL; import an OpenSSL key and check the token reports the same point.
#   PIN=... tools/check-secp256k1.sh        (run on the board)
set -eu
M=/usr/lib/libckteec.so
: "${PIN:?set PIN}"
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
p11() { pkcs11-tool --module $M --slot 0 --login --pin "$PIN" "$@"; }

p11 --keypairgen --key-type EC:secp256k1 --id 4b --label k1test --usage-sign >/dev/null
p11 --read-object --type pubkey --id 4b -o "$t/pub.der" >/dev/null
head -c 32 /dev/urandom > "$t/digest"
p11 --sign --mechanism ECDSA --id 4b --signature-format openssl -i "$t/digest" -o "$t/sig" >/dev/null
openssl pkeyutl -verify -pubin -inkey "$t/pub.der" -in "$t/digest" -sigfile "$t/sig" | grep -q 'Verified OK'
openssl ec -pubin -inform DER -in "$t/pub.der" -text -noout 2>/dev/null | grep -q 'secp256k1'
echo "generate+sign: ok"

openssl ecparam -name secp256k1 -genkey -noout -outform DER -out "$t/imp.der" 2>/dev/null
openssl ec -inform DER -in "$t/imp.der" -pubout -outform DER -out "$t/imp.pub" 2>/dev/null
p11 --write-object "$t/imp.der" --type privkey --id 4c --label k1imp --usage-sign --sensitive >/dev/null
p11 --read-object --type pubkey --id 4c -o "$t/imp.pub.tok" >/dev/null
cmp "$t/imp.pub" "$t/imp.pub.tok"
echo "import: ok"

p11 --delete-object --type privkey --id 4b >/dev/null; p11 --delete-object --type pubkey --id 4b >/dev/null
p11 --delete-object --type privkey --id 4c >/dev/null; p11 --delete-object --type pubkey --id 4c >/dev/null
echo "all ok"
