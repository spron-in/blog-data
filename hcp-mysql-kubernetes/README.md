# Dynamic User Creation with MySQL on Kubernetes and Hashicorp Cloud Platform Vault
Blog post about integrating Percona Distribution for MySQL and HashiCorp Cloud Platform Vault to provide dynamic user creation.

Full blog post: [here](https://www.percona.com/blog/dynamic-user-creation-with-mysql-on-kubernetes-and-hashicorp-cloud-platform-vault/)

# Commands

## MySQL

### deploy operator
```
kubectl apply -f bundle.yaml
kubectl apply -f cr.yaml
```

### get mysql root password from secret
```
kubectl get secrets my-cluster-secrets -o yaml | awk '$1~/root/ {print $2}' | base64 --decode && echo
```

### check if pxc is ready and get the ENDPOINT
```
kubectl get pxc
```
### connect to the database
```
kubectl exec -ti cluster1-pxc-0 bash -c pxc
mysql -u root -p -h 35.223.41.79
```

### create mysql user and db
```
create user hcp identified by 'superduper';
grant select, insert, update, delete, drop, create, alter, create user on *.* to hcp with grant option;
flush privileges;
create database myapp;
```

## Vault

### login
```
export VAULT_ADDR=https://vault-cluster.SOMEURL.hashicorp.cloud:8200
export VAULT_NAMESPACE="admin"

vault login
```

### enable database secrets engine
```
vault secrets enable database
```

### create database config
```
vault write database/config/myapp plugin_name=mysql-database-plugin \
connection_url="{{username}}:{{password}}@tcp(IP_ADDRESS)/" \
allowed_roles="mysqlrole" \
username="hcp" \
password="superduper"
```

### create the role
```
vault write database/roles/mysqlrole db_name=myapp \
creation_statements="CREATE USER '{{name}}'@'%' IDENTIFIED BY '{{password}}'; GRANT select, insert, update, delete, drop, create, alter ON myapp.* TO '{{name}}'@'%';" \
default_ttl="1h" \
max_ttl="24h"
```

### create dynamic user
```
vault read database/creds/mysqlrole
```
