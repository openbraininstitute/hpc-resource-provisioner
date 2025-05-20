#!/bin/bash

## This script:
## 1. Calls HPC provisioner to delete the given cluster
## 2. Deletes the SSH key file from the bastion host (assuming this was copied by cluster_status script)
## 3. Deletes the local copy of the SSH key file
##
## Notes:
## - This script assumes the following:
##     - The cluster with <PROJECT_ID> exists
##     - The sequence of cluster_up + cluster_status + cluster_down scripts are called in this order
## - This script does NOT check for every possible error


# PROJECT_ID needs to be passed to the script
if [ -z "$1" ]; then
  echo "Usage: $0 <PROJECT_ID>"
  exit 1
fi

# AWS credentials and needed data
export AWS_ACCESS_KEY_ID=$(awk '/^aws_access_key_id/ {print $3}' ~/.aws/credentials)
export AWS_SECRET_ACCESS_KEY=$(awk '/^aws_secret/ {print $3}' ~/.aws/credentials)
export AWS_APIGW_DEPLOY_ID=""
export AWS_REGION="us-east-1"
export PROJECT_ID="$1"
export VLAB_ID=$USER
export SSH_KEY_FILE=${PROJECT_ID}

# Delete the given cluster
echo "Calling cluster deletion of ${PROJECT_ID}"
export COMMAND="curl -X DELETE --user \""${AWS_ACCESS_KEY_ID}":"${AWS_SECRET_ACCESS_KEY}"\" --aws-sigv4 \"aws:amz:"${AWS_REGION}":execute-api\" https://"${AWS_APIGW_DEPLOY_ID}".execute-api."${AWS_REGION}".amazonaws.com/production/hpc-provisioner/pcluster\?project_id\="${PROJECT_ID}"\&vlab_id\="${VLAB_ID}" | jq"
echo "+ ${COMMAND}"
export CLUSTER=$(eval "${COMMAND}")
echo "${CLUSTER}" | jq

# Delete the SSH key file from the bastion host
if ssh -i ~/.ssh/id_rsa_aws ec2-user@107.22.159.90 test -f "~/.ssh/${SSH_KEY_FILE}"
then
	ssh -i ~/.ssh/id_rsa_aws ec2-user@107.22.159.90 "rm ~/.ssh/${SSH_KEY_FILE}"
	echo "SSH keyfile deleted from bastion host"
	export IP_ADDR=$(cat ${SSH_KEY_FILE}_ip)
	ssh -i ~/.ssh/id_rsa_aws ec2-user@107.22.159.90 "ssh-keygen -R ${IP_ADDR}"
	rm -rf ${SSH_KEY_FILE}_ip
	echo "Head node keys deleted from bastion host's known_hosts"
fi

# Delete the local copy of the SSH key file
rm -f ${PROJECT_ID}
rm -f ${PROJECT_ID}_admin
echo "SSH keyfile deleted locally" 

# Check that the cluster is being deleted
export IS_DELETED=$(echo $CLUSTER | jq -r '.cluster | .clusterStatus')

if [ $IS_DELETED = "DELETE_IN_PROGRESS" ]
then
	echo "Cluster ${PROJECT_ID} is shutting down"
else
	echo "Cluster ${PROJECT_ID} deleted"
fi

