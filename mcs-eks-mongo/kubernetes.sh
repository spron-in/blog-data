# kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-1.eu-central-1.eksctl.io
# kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-2.eu-central-1.eksctl.io

# install Operator
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-1.eu-central-1.eksctl.io apply -f bundle.yaml

# deploy cluster with MCS enabled
# mcs enabled, sharding disabled, replicaset exposed, cluster name changed
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-1.eu-central-1.eksctl.io apply -f cr1.yaml

# show service imports created

# get secrets from the cluster
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-1.eu-central-1.eksctl.io get secret cluster-main-ssl -o yaml > cluster-secrets.yaml
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-1.eu-central-1.eksctl.io get secret my-cluster-name-secrets -o yaml >> cluster-secrets.yaml
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-1.eu-central-1.eksctl.io get secret cluster-main-ssl-internal -o yaml >> cluster-secrets.yaml



# install operator in the 2nd cluster
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-2.eu-central-1.eksctl.io apply -f bundle.yaml

# apply stripped secrets
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-2.eu-central-1.eksctl.io apply -f cluster-secrets.yaml

# deploy the cluster on the 2nd cluster
# enable mcs, unmanaged true, updateStrategy OnDelete, backup disabled
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-2.eu-central-1.eksctl.io apply -f cr2.yaml

# deploy client container 
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-1.eu-central-1.eksctl.io run -i --rm --tty percona-client1 --image=percona/percona-server-mongodb:5.0 --restart=Never -- bash -il

# get root password
# connect to DB and show rs.status()

# apply cr1.yaml again with externalNodes
kubectl --context spronin-cli@psmdb-cluster-mcs-setup-test-1.eu-central-1.eksctl.io apply -f deploy/cr1.yaml
