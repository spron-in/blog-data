from pulumi import Config, export, get_project, get_stack, Output, ResourceOptions
from pulumi_gcp.config import project, zone
from pulumi_gcp.container import Cluster, ClusterNodeConfigArgs
from pulumi_random import RandomPassword

import pulumi_kubernetes as kubernetes

# Read in some configurable settings for our cluster:
config = Config(None)

# nodeCount is the number of cluster nodes to provision. Defaults to 3 if unspecified.
NODE_COUNT = config.get_int('node_count') or 3
# nodeMachineType is the machine type to use for cluster nodes. Defaults to n1-standard-1 if unspecified.
# See https://cloud.google.com/compute/docs/machine-types for more details on available machine types.
NODE_MACHINE_TYPE = config.get('node_machine_type') or 'n1-standard-4'
# username is the admin username for the cluster.
USERNAME = config.get('username') or 'admin'
# password is the password for the admin user in the cluster.
PASSWORD = config.get_secret('password') or RandomPassword("password", length=20, special=True).result
# master version of GKE engine
MASTER_VERSION = config.get('master_version')

# PostgreSQL config block #
# namespace for Percona Operator
NAMESPACE = config.get('namespace') or 'default'
# PostgreSQL pguser password
PGUSER_PASSWORD = config.get('pguser_password') or RandomPassword("pguser_password", length=20, special=True).result
# PostgreSQL cluster name
PG_CLUSTER_NAME = config.get('pg_cluster_name') or 'cluster1'
# Service type used for pgBouncer
PG_SERVICE_TYPE = config.get('service_type') or 'ClusterIP'

# Now, actually create the GKE cluster.
k8s_cluster = Cluster('gke-cluster',
    initial_node_count=NODE_COUNT,
    node_version=MASTER_VERSION,
    min_master_version=MASTER_VERSION,
    node_config=ClusterNodeConfigArgs(
        machine_type=NODE_MACHINE_TYPE,
        oauth_scopes=[
            'https://www.googleapis.com/auth/compute',
            'https://www.googleapis.com/auth/devstorage.read_only',
            'https://www.googleapis.com/auth/logging.write',
            'https://www.googleapis.com/auth/monitoring'
        ],
    ),
)

# Manufacture a GKE-style Kubeconfig. Note that this is slightly "different" because of the way GKE requires
# gcloud to be in the picture for cluster authentication (rather than using the client cert/key directly).
k8s_info = Output.all(k8s_cluster.name, k8s_cluster.endpoint, k8s_cluster.master_auth)
k8s_config = k8s_info.apply(
    lambda info: """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {0}
    server: https://{1}
  name: {2}
contexts:
- context:
    cluster: {2}
    user: {2}
  name: {2}
current-context: {2}
kind: Config
preferences: {{}}
users:
- name: {2}
  user:
    auth-provider:
      config:
        cmd-args: config config-helper --format=json
        cmd-path: gcloud
        expiry-key: '{{.credential.token_expiry}}'
        token-key: '{{.credential.access_token}}'
      name: gcp
""".format(info[2]['cluster_ca_certificate'], info[1], '{0}_{1}_{2}'.format(project, zone, info[0])))

# Make a Kubernetes provider instance that uses our cluster from above.
k8s_provider = kubernetes.Provider('gke_k8s', kubeconfig=k8s_config)

# Create a K8s namespace
if pg_namespace != 'default':
    pg_namespace = kubernetes.core.v1.Namespace(
        "pgNamespace",
        metadata={
            "name": NAMESPACE,
        },opts=ResourceOptions(provider=k8s_provider))


# Deploy Percona PG Operator

# Deploy Operator
pgo_pgo_deployer_sa_service_account = kubernetes.core.v1.ServiceAccount("pgoPgo_deployer_saServiceAccount",
    api_version="v1",
    kind="ServiceAccount",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="pgo-deployer-sa",
        namespace=NAMESPACE,
    ),opts=ResourceOptions(provider=k8s_provider))

pgo_deployer_cr_cluster_role = kubernetes.rbac.v1.ClusterRole("pgo_deployer_crClusterRole",
    kind="ClusterRole",
    api_version="rbac.authorization.k8s.io/v1",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="pgo-deployer-cr",
    ),
    rules=[
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=[""],
            resources=["namespaces"],
            verbs=[
                "get",
                "list",
                "create",
                "patch",
                "delete",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=[""],
            resources=["pods"],
            verbs=["list"],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=[""],
            resources=["secrets"],
            verbs=[
                "list",
                "get",
                "create",
                "delete",
                "patch",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=[""],
            resources=[
                "configmaps",
                "services",
                "persistentvolumeclaims",
            ],
            verbs=[
                "get",
                "create",
                "delete",
                "list",
                "patch",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=[""],
            resources=["serviceaccounts"],
            verbs=[
                "get",
                "create",
                "delete",
                "patch",
                "list",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=[
                "apps",
                "extensions",
            ],
            resources=[
                "deployments",
                "replicasets",
            ],
            verbs=[
                "get",
                "list",
                "watch",
                "create",
                "delete",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=["apiextensions.k8s.io"],
            resources=["customresourcedefinitions"],
            verbs=[
                "get",
                "create",
                "delete",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=["rbac.authorization.k8s.io"],
            resources=[
                "clusterroles",
                "clusterrolebindings",
                "roles",
                "rolebindings",
            ],
            verbs=[
                "get",
                "create",
                "delete",
                "bind",
                "escalate",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=["rbac.authorization.k8s.io"],
            resources=["roles"],
            verbs=[
                "create",
                "delete",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=["batch"],
            resources=["jobs"],
            verbs=[
                "delete",
                "list",
            ],
        ),
        kubernetes.rbac.v1.PolicyRuleArgs(
            api_groups=["pg.percona.com"],
            resources=[
                "perconapgclusters",
                "pgclusters",
                "pgreplicas",
                "pgpolicies",
                "pgtasks",
            ],
            verbs=[
                "delete",
                "list",
            ],
        ),
    ],opts=ResourceOptions(provider=k8s_provider))

pgo_pgo_deployer_cm_config_map = kubernetes.core.v1.ConfigMap("pgoPgo_deployer_cmConfigMap",
    api_version="v1",
    kind="ConfigMap",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="pgo-deployer-cm",
        namespace=NAMESPACE,
    ),
    data={ "values.yaml": """
# =====================
# Configuration Options
# More info for these options can be found in the docs
# https://access.crunchydata.com/documentation/postgres-operator/latest/installation/configuration/
# =====================
archive_mode: "true"
archive_timeout: "60"
backrest_aws_s3_bucket: ""
backrest_aws_s3_endpoint: ""
backrest_aws_s3_key: ""
backrest_aws_s3_region: ""
backrest_aws_s3_secret: ""
backrest_aws_s3_uri_style: ""
backrest_aws_s3_verify_tls: "true"
backrest_gcs_bucket: ""
backrest_gcs_endpoint: ""
backrest_gcs_key_type: ""
backrest_port: "2022"
badger: "false"
ccp_image_prefix: "percona/percona-postgresql-operator"
ccp_image_pull_secret: ""
ccp_image_pull_secret_manifest: ""
ccp_image_tag: "1.1.0-postgres-ha"
create_rbac: "true"
crunchy_debug: "false"
db_name: ""
db_password_age_days: "0"
db_password_length: "24"
db_port: "5432"
db_replicas: "0"
db_user: "testuser"
default_instance_memory: "128Mi"
default_pgbackrest_memory: "48Mi"
default_pgbouncer_memory: "24Mi"
default_exporter_memory: "24Mi"
delete_operator_namespace: "false"
delete_watched_namespaces: "false"
disable_auto_failover: "false"
disable_fsgroup: "false"
reconcile_rbac: "true"
exporterport: "9187"
metrics: "false"
namespace: "{main_namespace}"
namespace_mode: "dynamic"
pgbadgerport: "10000"
pgo_add_os_ca_store: "false"
pgo_admin_password: "examplepassword"
pgo_admin_perms: "*"
pgo_admin_role_name: "pgoadmin"
pgo_admin_username: "admin"
pgo_apiserver_port: "8443"
pgo_apiserver_url: "https://postgres-operator"
pgo_client_cert_secret: "pgo.tls"
pgo_client_container_install: "false"
pgo_client_install: "false"
pgo_client_version: "4.7.1"
pgo_cluster_admin: "false"
pgo_disable_eventing: "false"
pgo_disable_tls: "false"
pgo_image_prefix: "percona/percona-postgresql-operator"
pgo_image_pull_policy: "Always"
pgo_image_pull_secret: ""
pgo_image_pull_secret_manifest: ""
pgo_image_tag: "1.1.0"
pgo_installation_name: "devtest"
pgo_noauth_routes: ""
pgo_operator_namespace: "{cluster_namespace}"
pgo_tls_ca_store: ""
pgo_tls_no_verify: "false"
pod_anti_affinity: "preferred"
pod_anti_affinity_pgbackrest: ""
pod_anti_affinity_pgbouncer: ""
scheduler_timeout: "3600"
service_type: "ClusterIP"
sync_replication: "false"
backrest_storage: "default"
backup_storage: "default"
primary_storage: "default"
replica_storage: "default"
pgadmin_storage: "default"
wal_storage: ""
storage1_name: "default"
storage1_access_mode: "ReadWriteOnce"
storage1_size: "1G"
storage1_type: "dynamic"
storage2_name: "hostpathstorage"
storage2_access_mode: "ReadWriteMany"
storage2_size: "1G"
storage2_type: "create"
storage3_name: "nfsstorage"
storage3_access_mode: "ReadWriteMany"
storage3_size: "1G"
storage3_type: "create"
storage3_supplemental_groups: "65534"
storage4_name: "nfsstoragered"
storage4_access_mode: "ReadWriteMany"
storage4_size: "1G"
storage4_match_labels: "crunchyzone=red"
storage4_type: "create"
storage4_supplemental_groups: "65534"
storage5_name: "storageos"
storage5_access_mode: "ReadWriteOnce"
storage5_size: "5Gi"
storage5_type: "dynamic"
storage5_class: "fast"
storage6_name: "primarysite"
storage6_access_mode: "ReadWriteOnce"
storage6_size: "4G"
storage6_type: "dynamic"
storage6_class: "primarysite"
storage7_name: "alternatesite"
storage7_access_mode: "ReadWriteOnce"
storage7_size: "4G"
storage7_type: "dynamic"
storage7_class: "alternatesite"
storage8_name: "gce"
storage8_access_mode: "ReadWriteOnce"
storage8_size: "300M"
storage8_type: "dynamic"
storage8_class: "standard"
storage9_name: "rook"
storage9_access_mode: "ReadWriteOnce"
storage9_size: "1Gi"
storage9_type: "dynamic"
storage9_class: "rook-ceph-block"
""".format(cluster_namespace=NAMESPACE, main_namespace=NAMESPACE),
    },opts=ResourceOptions(provider=k8s_provider))

pgo_deployer_crb_cluster_role_binding = kubernetes.rbac.v1.ClusterRoleBinding("pgo_deployer_crbClusterRoleBinding",
    api_version="rbac.authorization.k8s.io/v1",
    kind="ClusterRoleBinding",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="pgo-deployer-crb",
    ),
    role_ref=kubernetes.rbac.v1.RoleRefArgs(
        api_group="rbac.authorization.k8s.io",
        kind="ClusterRole",
        name="pgo-deployer-cr",
    ),
    subjects=[kubernetes.rbac.v1.SubjectArgs(
        kind="ServiceAccount",
        name="pgo-deployer-sa",
        namespace=NAMESPACE,
    )],opts=ResourceOptions(provider=k8s_provider))

pgo_pgo_deploy_job = kubernetes.batch.v1.Job("pgoPgo_deployJob",
    api_version="batch/v1",
    kind="Job",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        name="pgo-deploy",
        namespace=NAMESPACE,
    ),
    spec=kubernetes.batch.v1.JobSpecArgs(
        backoff_limit=0,
        template=kubernetes.core.v1.PodTemplateSpecArgs(
            metadata=kubernetes.meta.v1.ObjectMetaArgs(
                name="pgo-deploy",
            ),
            spec=kubernetes.core.v1.PodSpecArgs(
                service_account_name="pgo-deployer-sa",
                restart_policy="Never",
                containers=[kubernetes.core.v1.ContainerArgs(
                    name="pgo-deploy",
                    image="percona/percona-postgresql-operator:1.1.0-pgo-deployer",
                    image_pull_policy="Always",
                    env=[kubernetes.core.v1.EnvVarArgs(
                        name="DEPLOY_ACTION",
                        value="install",
                    )],
                    volume_mounts=[{
                        "name": "deployer-conf",
                        "mount_path": "/conf",
                    }],
                )],
                volumes=[kubernetes.core.v1.VolumeArgs(
                    name="deployer-conf",
                    config_map={
                        "name": "pgo-deployer-cm",
                    },
                )],
            ),
        ),
    ),opts=ResourceOptions(provider=k8s_provider))


# deploy pguser secret
percona_pg_cluster1_pguser_secret_secret = kubernetes.core.v1.Secret("percona_pguser_secretSecret",
    api_version="v1",
    string_data={
        "password": PGUSER_PASSWORD,
        "username": "pguser",
    },
    kind="Secret",
    metadata=kubernetes.meta.v1.ObjectMetaArgs(
        labels={
            "pg-cluster": PG_CLUSTER_NAME,
        },
        name="%s-pguser-secret" % PG_CLUSTER_NAME,
        namespace=NAMESPACE,
    ),
    type="Opaque",opts=ResourceOptions(provider=k8s_provider))

# deploy pg cluster
perconapg = kubernetes.apiextensions.CustomResource(
    "my_cluster_name",
    api_version="pg.percona.com/v1",
    kind="PerconaPGCluster",
    metadata={
        "namespace": NAMESPACE,
        "labels": {
            "pgo-version": "1.1.0",
        },
        "name": PG_CLUSTER_NAME
    },
    spec= {
    "upgradeOptions": {
      "versionServiceEndpoint": "https://check.percona.com",
      "apply": "disabled",
      "schedule": "0 4 * * *"
    },
    "database": "pgdb",
    "port": "5432",
    "user": "pguser",
    "disableAutofail": False,
    "tlsOnly": False,
    "standby": False,
    "pause": False,
    "keepData": True,
    "keepBackups": True,
    "userLabels": {
      "pgo-version": "1.1.0"
    },
    "pgPrimary": {
      "image": "percona/percona-postgresql-operator:1.1.0-ppg14-postgres-ha",
      "resources": {
        "requests": {
          "memory": "128Mi"
        }
      },
      "tolerations": [],
      "volumeSpec": {
        "size": "1G",
        "accessmode": "ReadWriteOnce",
        "storagetype": "dynamic",
        "storageclass": ""
      },
      "expose": {
        "serviceType": "ClusterIP"
      }
    },
    "backup": {
      "image": "percona/percona-postgresql-operator:1.1.0-ppg14-pgbackrest",
      "backrestRepoImage": "percona/percona-postgresql-operator:1.1.0-ppg14-pgbackrest-repo",
      "resources": {
        "requests": {
          "memory": "48Mi"
        }
      },
      "volumeSpec": {
        "size": "1G",
        "accessmode": "ReadWriteOnce",
        "storagetype": "dynamic",
        "storageclass": ""
      },
      "schedule": [
        {
          "name": "sat-night-backup",
          "schedule": "0 0 * * 6",
          "keep": 3,
          "type": "full",
          "storage": "local"
        }
      ]
    },
    "pgBouncer": {
      "image": "percona/percona-postgresql-operator:1.1.0-ppg14-pgbouncer",
      "size": 3,
      "resources": {
        "requests": {
          "cpu": "1",
          "memory": "128Mi"
        },
        "limits": {
          "cpu": "2",
          "memory": "512Mi"
        }
      },
      "expose": {
        "serviceType": PG_SERVICE_TYPE
      }
    },
    "pgReplicas": {
      "hotStandby": {
        "size": 3,
        "resources": {
          "requests": {
            "cpu": "1",
            "memory": "128Mi"
          }
        },
        "volumeSpec": {
          "accessmode": "ReadWriteOnce",
          "size": "1G",
          "storagetype": "dynamic",
          "storageclass": ""
        },
        "enableSyncStandby": False,
        "expose": {
          "serviceType": "ClusterIP"
        }
      }
    }
    },opts=ResourceOptions(provider=k8s_provider,depends_on=[pgo_pgo_deploy_job,percona_pg_cluster1_pguser_secret_secret])
)

# show kubeconfig 
export('kubeconfig', k8s_config)
