#!/bin/bash
# env.sh <instance>: writes /work/<instance>.env (+ CA) in the loadgen pod from the <instance>-conn Secret.
# Every test script runs `. /work/<instance>.env` first; it sets H, PO, PW, CA, MYSQL and SSL.
n=$1; ns=${NS:-tidb}; D=$(mktemp -d); g() { kubectl -n $ns get secret $n-conn -o jsonpath="{.data.${1//./\\.}}" | base64 -d; }
g ca.crt > $D/$n-ca.crt 2>/dev/null; CA=""
if [ -s $D/$n-ca.crt ]; then kubectl -n $ns exec -i loadgen -- sh -c "cat > /work/$n-ca.crt" < $D/$n-ca.crt; CA=/work/$n-ca.crt; fi
printf "export H='%s' PO='%s' PW='%s' CA='%s'\nMYSQL=\"mysql -h \$H -P \$PO -uroot -p\$PW \${CA:+--ssl-ca=\$CA --ssl-verify-server-cert}\"\nSSL=\${CA:+--ssl-ca \$CA}\n" "$(g host)" "$(g port)" "$(g password)" "$CA" | kubectl -n $ns exec -i loadgen -- sh -c "cat > /work/$n.env"
rm -rf $D
