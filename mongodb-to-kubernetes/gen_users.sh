clusterAdminPass="clusterAdmin"
userAdminPass="userAdmin"
clusterMonitorPass="clusterMonitor"
backupPass="backup"

# mongo shell
cat <<EOF > user-mongo-shell.txt
use admin
db.createRole(
{
"roles": [],
role: "pbmAnyAction",
"privileges" : [
                {
                        "resource" : {
                                "anyResource" : true
                        },
                        "actions" : [
                                "anyAction"
                        ]
                }
        ],

})

db.createUser( { user: "clusterMonitor", pwd: "$clusterMonitorPass", roles: [ "clusterMonitor" ] } )
db.createUser( { user: "userAdmin", pwd: "$userAdminPass", roles: [ "userAdminAnyDatabase" ] } )
db.createUser( { user: "clusterAdmin", pwd: "$clusterAdminPass", roles: [ "clusterAdmin" ] } )
db.createUser( { user: "backup", pwd: "$backupPass", roles: [ "readWrite", "backup", "clusterMonitor", "restore", "pbmAnyAction" ] } )
EOF

# user-secret.yaml
cat <<EOF > user-secret.yaml
apiVersion: v1
stringData:
  MONGODB_BACKUP_PASSWORD: $backupPass
  MONGODB_BACKUP_USER: backup
  MONGODB_CLUSTER_ADMIN_PASSWORD: $clusterAdminPass
  MONGODB_CLUSTER_ADMIN_USER: clusterAdmin
  MONGODB_CLUSTER_MONITOR_PASSWORD: $clusterMonitorPass
  MONGODB_CLUSTER_MONITOR_USER: clusterMonitor
  MONGODB_USER_ADMIN_PASSWORD: $userAdminPass
  MONGODB_USER_ADMIN_USER: userAdmin
  PMM_SERVER_PASSWORD: pmmpassword
  PMM_SERVER_USER: admin
kind: Secret
metadata:
  name: my-new-cluster-secrets
  namespace: default
type: Opaque
EOF

