# generate CA key
openssl genrsa -out ca.key 2048

# generate CA cert
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.pem -config mongo-ca.conf

# generate client key
openssl genrsa -out client.key 2048

# generate client csr
openssl req -new -key client.key -out client.csr -config mongo.conf

# generate client cert
openssl x509 -req -in client.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out client.pem -days 3650 -sha256 -extfile mongo.conf -extensions v3_req

cat client.pem client.key > mongod.pem

cat <<EOF > ssl-secret.yaml
apiVersion: v1
data:
  ca.crt: $(cat ca.pem | base64 -w0)
  tls.crt: $(cat client.pem | base64 -w0)
  tls.key: $(cat client.key | base64 -w0)
kind: Secret
metadata:
  name: my-custom-ssl
  namespace: default
type: kubernetes.io/tls

---
apiVersion: v1
data:
  ca.crt: $(cat ca.pem | base64 -w0)
  tls.crt: $(cat client.pem | base64 -w0)
  tls.key: $(cat client.key | base64 -w0)
kind: Secret
metadata:
  name: my-custom-ssl-internal
  namespace: default
type: kubernetes.io/tls
EOF
