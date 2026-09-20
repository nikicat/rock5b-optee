#!/bin/sh
# Host check of BL31's image verifier: build opteed_sig.c + Monocypher natively
# and feed it blobs from tee-sign.py. Fails if any of the rejections stops working.
#   tee-sign-selftest.sh <arm-trusted-firmware src> <tee-v2.bin>
set -eu
tfa=$1; img=$2; here=$(dirname "$(realpath "$0")")
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
cat > "$t/main.c" <<'C'
#include <stdio.h>
#include <stdlib.h>
#include "opteed_sig.h"
static unsigned char *slurp(const char *p, size_t *n) {
	FILE *f = fopen(p, "rb"); if (!f) { perror(p); exit(2); }
	fseek(f, 0, SEEK_END); *n = ftell(f); rewind(f);
	unsigned char *b = malloc(*n); if (fread(b, 1, *n, f) != *n) exit(2); fclose(f); return b;
}
int main(int argc, char **argv) {	/* chk BLOB PUB MINVER [TRUNCATE] -> exit 0 iff accepted */
	size_t n, pn, off, len; unsigned ver;
	unsigned char *b = slurp(argv[1], &n), *pk = slurp(argv[2], &pn);
	if (argc > 4) n -= strtoul(argv[4], 0, 0);
	int rc = opteed_sig_verify(b, n, strtoul(argv[3], 0, 0), pk, &off, &len, &ver);
	printf("rc=%d off=%zu len=%zu version=%u\n", rc, off, len, ver);
	return rc != 0;
}
C
cc -O1 -I"$tfa/lib/monocypher" -I"$tfa/services/spd/opteed" -o "$t/chk" "$t/main.c" \
	"$tfa/services/spd/opteed/opteed_sig.c" "$tfa/lib/monocypher/monocypher.c" "$tfa/lib/monocypher/monocypher-ed25519.c"
sign="python3 $here/tee-sign.py"
$sign keygen "$t/k.pem"; $sign keygen "$t/other.pem"
$sign sign "$t/k.pem" 7 "$img" "$t/good.bin"
[ "$($sign verify "$t/k.pub" "$t/good.bin")" = 7 ]
flip() { python3 -c "import sys;p=sys.argv[1];o=int(sys.argv[2]);d=bytearray(open(p,'rb').read());d[o]^=1;open(sys.argv[3],'wb').write(d)" "$@"; }
flip "$t/good.bin" 12 "$t/ver.bin"; flip "$t/good.bin" 100 "$t/body.bin"
sz=$(stat -c %s "$t/good.bin"); flip "$t/good.bin" $((sz - 1)) "$t/sig.bin"
$sign sign "$t/other.pem" 7 "$img" "$t/otherkey.bin"
"$t/chk" "$t/good.bin" "$t/k.pub" 7 >/dev/null           || { echo "FAIL: good image rejected"; exit 1; }
"$t/chk" "$t/good.bin" "$t/k.pub" 0 >/dev/null           || { echo "FAIL: min version 0"; exit 1; }
! "$t/chk" "$t/good.bin" "$t/k.pub" 8 >/dev/null         || { echo "FAIL: old version accepted"; exit 1; }
! "$t/chk" "$t/ver.bin" "$t/k.pub" 0 >/dev/null          || { echo "FAIL: edited version accepted"; exit 1; }
! "$t/chk" "$t/body.bin" "$t/k.pub" 0 >/dev/null         || { echo "FAIL: edited image accepted"; exit 1; }
! "$t/chk" "$t/sig.bin" "$t/k.pub" 0 >/dev/null          || { echo "FAIL: edited signature accepted"; exit 1; }
! "$t/chk" "$t/otherkey.bin" "$t/k.pub" 0 >/dev/null     || { echo "FAIL: other key accepted"; exit 1; }
! "$t/chk" "$t/good.bin" "$t/k.pub" 0 1 >/dev/null       || { echo "FAIL: truncated accepted"; exit 1; }
! "$t/chk" "$t/good.bin" "$t/k.pub" 0 $((sz - 40)) >/dev/null || { echo "FAIL: header-only accepted"; exit 1; }

# the same through gpg-agent, with a throwaway keyring
export GNUPGHOME="$t/gnupg"; mkdir -m 700 "$GNUPGHOME"
gpg --batch --quiet --pinentry-mode loopback --passphrase '' --quick-gen-key "selftest" ed25519 sign never 2>/dev/null
gfpr=$(gpg --list-keys --with-colons | awk -F: '$1=="fpr"{print $10; exit}')
$sign pubkey "gpg:$gfpr" "$t/g.pub"; trap 'gpgconf --kill gpg-agent; rm -rf "$t"' EXIT
$sign sign "gpg:$gfpr" 9 "$img" "$t/g.bin"; [ "$($sign verify "$t/g.pub" "$t/g.bin")" = 9 ]
"$t/chk" "$t/g.bin" "$t/g.pub" 9 >/dev/null || { echo "FAIL: gpg-signed image rejected"; exit 1; }
! "$t/chk" "$t/g.bin" "$t/k.pub" 0 >/dev/null || { echo "FAIL: gpg-signed image accepted by the file key"; exit 1; }
"$t/chk" "$t/good.bin" "$t/k.pub" 7
echo "all ok (file key and gpg-agent key)"
