#!/bin/bash
export CLUSTER_MAIN=${1:-"psmdb-cluster-mcs-setup-test-1"}
export CLUSTER_REPL=${2:-"psmdb-cluster-mcs-setup-test-2"}
export CLUSTER_MAIN_CIDR=10.10.0.0/16
export CLUSTER_REPL_CIDR=10.12.0.0/16

for binary in eksctl aws kubectl
do
  command -v $binary >/dev/null 2>&1 || { echo >&2 "The script requires $binary but it's not installed.  Aborting."; exit 1; }
done

echo "########################## Create cluster 1 ############################"
eksctl create cluster -f eks-cluster-mcs-1.yaml

eksctl utils associate-iam-oidc-provider --region=eu-central-1 --cluster=${CLUSTER_MAIN} --approve
eksctl create iamserviceaccount --region eu-central-1 --name cloud-map-mcs-controller-manager --namespace cloud-map-mcs-system --cluster ${CLUSTER_MAIN} --attach-policy-arn arn:aws:iam::aws:policy/AWSCloudMapFullAccess --approve --override-existing-serviceaccounts

kubectl create ns mcs && kubectl config set-context --current --namespace mcs
echo "configure coredns for each cluster:"
kubectl apply -f https://raw.githubusercontent.com/aws/aws-cloud-map-mcs-controller-for-k8s/main/samples/coredns-clusterrole.yaml
kubectl apply -f https://raw.githubusercontent.com/aws/aws-cloud-map-mcs-controller-for-k8s/main/samples/coredns-configmap.yaml
kubectl apply -f https://raw.githubusercontent.com/aws/aws-cloud-map-mcs-controller-for-k8s/main/samples/coredns-deployment.yaml
echo "install controller:"
kubectl apply -k "github.com/aws/aws-cloud-map-mcs-controller-for-k8s/config/controller_install_release"

echo "########################### Create cluster 2 #############################"
eksctl create cluster -f eks-cluster-mcs-2.yaml
eksctl utils associate-iam-oidc-provider --region=eu-central-1 --cluster=${CLUSTER_REPL} --approve
eksctl create iamserviceaccount --region eu-central-1 --name cloud-map-mcs-controller-manager --namespace cloud-map-mcs-system --cluster ${CLUSTER_REPL} --attach-policy-arn arn:aws:iam::aws:policy/AWSCloudMapFullAccess --approve --override-existing-serviceaccounts
kubectl create ns mcs && kubectl config set-context --current --namespace mcs
echo "configure coredns for each cluster:"
kubectl apply -f https://raw.githubusercontent.com/aws/aws-cloud-map-mcs-controller-for-k8s/main/samples/coredns-clusterrole.yaml
kubectl apply -f https://raw.githubusercontent.com/aws/aws-cloud-map-mcs-controller-for-k8s/main/samples/coredns-configmap.yaml
kubectl apply -f https://raw.githubusercontent.com/aws/aws-cloud-map-mcs-controller-for-k8s/main/samples/coredns-deployment.yaml
echo "install controller:"
kubectl apply -k "github.com/aws/aws-cloud-map-mcs-controller-for-k8s/config/controller_install_release"

echo "########################### Setup VPC peering between clusters vpc ###################################################"

echo "To let traffic cross between main and repl clusters we need to create a VPC peer between our main and replica clusters."

export EKS_VPC_MAIN=$(aws eks describe-cluster  --name ${CLUSTER_MAIN}  --query "cluster.resourcesVpcConfig.vpcId" --output text)
export EKS_VPC_REPL=$(aws eks describe-cluster  --name ${CLUSTER_REPL}  --query "cluster.resourcesVpcConfig.vpcId" --output text)

export PEERING_ID=$(aws ec2 create-vpc-peering-connection --vpc-id $EKS_VPC_MAIN --peer-vpc-id $EKS_VPC_REPL --query 'VpcPeeringConnection.VpcPeeringConnectionId' --output text)
aws ec2 accept-vpc-peering-connection --vpc-peering-connection-id $PEERING_ID
aws ec2 modify-vpc-peering-connection-options --vpc-peering-connection-id $PEERING_ID --requester-peering-connection-options '{"AllowDnsResolutionFromRemoteVpc":true}' --accepter-peering-connection-options '{"AllowDnsResolutionFromRemoteVpc":true}'

echo "Allow traffic from the EKS VPC and Security group of main cluster to replica one"

export EKS_SECURITY_GROUP_MAIN=$(aws cloudformation list-exports --query "Exports[*]|[?Name=='eksctl-$CLUSTER_MAIN-cluster::SharedNodeSecurityGroup'].Value" --output text)
export EKS_SECURITY_GROUP_REPL=$(aws cloudformation list-exports --query "Exports[*]|[?Name=='eksctl-$CLUSTER_REPL-cluster::SharedNodeSecurityGroup'].Value" --output text)

export EKS_CIDR_RANGES_MAIN=$(aws ec2 describe-subnets --filter "Name=vpc-id,Values=$EKS_VPC_MAIN" --query 'Subnets[*].CidrBlock' --output text)
export EKS_CIDR_RANGES_REPL=$(aws ec2 describe-subnets --filter "Name=vpc-id,Values=$EKS_VPC_REPL" --query 'Subnets[*].CidrBlock' --output text)

for CIDR in $(echo $EKS_CIDR_RANGES_MAIN); do aws ec2 authorize-security-group-ingress  --group-id $EKS_SECURITY_GROUP_REPL --ip-permissions IpProtocol=tcp,FromPort=1024,ToPort=65535,IpRanges="[{CidrIp=$CIDR}]"; done

for CIDR in $(echo $EKS_CIDR_RANGES_REPL); do aws ec2 authorize-security-group-ingress --group-id $EKS_SECURITY_GROUP_MAIN --ip-permissions IpProtocol=tcp,FromPort=1024,ToPort=65535,IpRanges="[{CidrIp=$CIDR}]"; done

echo "Create routes in both VPCs to route traffic"
export CIDR_BLOCK_MAIN=$(aws ec2 describe-vpc-peering-connections --query "VpcPeeringConnections[?VpcPeeringConnectionId=='$PEERING_ID'].RequesterVpcInfo.CidrBlock" --output text)
export CIDR_BLOCK_REPL=$(aws ec2 describe-vpc-peering-connections --query "VpcPeeringConnections[?VpcPeeringConnectionId=='$PEERING_ID'].AccepterVpcInfo.CidrBlock" --output text)

export EKS_RT_MAIN=$(aws cloudformation list-stack-resources --query "StackResourceSummaries[?LogicalResourceId=='PublicRouteTable'].PhysicalResourceId" --stack-name eksctl-${CLUSTER_MAIN}-cluster --output text)
export EKS_RT_REPL=$(aws cloudformation list-stack-resources --query "StackResourceSummaries[?LogicalResourceId=='PublicRouteTable'].PhysicalResourceId" --stack-name eksctl-${CLUSTER_REPL}-cluster --output text)

aws ec2 create-route --route-table-id $EKS_RT_MAIN --destination-cidr-block $CIDR_BLOCK_REPL --vpc-peering-connection-id $PEERING_ID
aws ec2 create-route --route-table-id $EKS_RT_REPL --destination-cidr-block $CIDR_BLOCK_MAIN --vpc-peering-connection-id $PEERING_ID

echo "Now that traffic will route between our clusters we can deploy our application to the EKS clusters."
