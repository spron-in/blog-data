namespace=prod-dbs
serviceaccount=database-manager

name=`kubectl -n $namespace get serviceAccounts $serviceaccount -o yaml | awk '$0~/^\-/ {print $3}'`
certificate=`kubectl -n $namespace get secret $name -o yaml | awk '$0~/ca\.crt:/ {print $2}'`
token=`kubectl -n $namespace get secret $name -o yaml | awk '$0~/token:/ {print $2}' | base64 --decode`
server=`kubectl cluster-info | grep 'Kubernetes control plane' | sed 's/.*\(https:\/\/.*\)/\1/'`

echo "apiVersion: v1
kind: Config
users:
- name: percona-pxc-manager
  user:
    token: $token
clusters:
- cluster:
    certificate-authority-data: $certificate
    server: $server
  name: self-hosted-cluster
contexts:
- context:
    cluster: self-hosted-cluster
    user: percona-pxc-manager
  name: svcs-acct-context
current-context: svcs-acct-context"
