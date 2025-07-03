#!/bin/bash

## Given a cluster name (<VLAB_ID>_<PROJECT_ID>), this script:
## 1. Calls HPC provisioner to delete the given cluster
## 2. Deletes the SSH key file from the bastion host (assuming this was copied by cluster_status script)
## 3. Deletes the local copy of the SSH key file
##
## Notes:
## - This script assumes the following:
##     - The cluster with <cluster_name> exists
##     - The sequence of cluster_up + cluster_status + cluster_down scripts are called in this order
## - This script does NOT check for every possible error


# Cluster name needs to be passed to the script
if [ -z "$1" ]; then
  echo "Usage: $0 <cluster_name>"
  exit 1
fi

# AWS credentials and needed data
export AWS_ACCESS_KEY_ID=$(awk '/^aws_access_key_id/ {print $3}' ~/.aws/credentials)
export AWS_SECRET_ACCESS_KEY=$(awk '/^aws_secret/ {print $3}' ~/.aws/credentials)
export AWS_APIGW_DEPLOY_ID=""
export AWS_REGION="us-east-1"

# Get the VLAB ID and the Project ID from the cluster name
IFS='_' read -r -a ARG <<< "$1"
export VLAB_ID="${ARG[0]}"
export PROJECT_ID="${ARG[1]}"

export SSH_KEY_FILE=$1

# Delete the given cluster
echo "Calling the deletion of cluster '${VLAB_ID}_${PROJECT_ID}'"
export COMMAND="curl -X DELETE --user \""${AWS_ACCESS_KEY_ID}":"${AWS_SECRET_ACCESS_KEY}"\" --aws-sigv4 \"aws:amz:"${AWS_REGION}":execute-api\" https://"${AWS_APIGW_DEPLOY_ID}".execute-api."${AWS_REGION}".amazonaws.com/production/hpc-provisioner/pcluster\?project_id\="${PROJECT_ID}"\&vlab_id\="${VLAB_ID}
echo "+ ${COMMAND} | jq"
export CLUSTER=$(eval "${COMMAND}")
echo "${CLUSTER}" | jq

# Check for errors: if 'message' field is present, there's an error
export ERROR=$(echo ${CLUSTER} | jq -r '.message')
if [ $ERROR != "null" ]
then
    echo "Error in cluster deletion:"
    echo "${CLUSTER}" | jq
    # Don't exit yet, as we will clean up potentially left ARN key files
fi

# Bastion host IP
export BASTION_IP="98.84.40.226"

# Delete the SSH key file from the bastion host
if ssh ec2-user@${BASTION_IP} test -f "~/.ssh/${SSH_KEY_FILE}"
then
	ssh ec2-user@${BASTION_IP} "rm ~/.ssh/${SSH_KEY_FILE}"
	ssh ec2-user@${BASTION_IP} "rm ~/.ssh/${SSH_KEY_FILE}.admin"
	echo "SSH keyfiles deleted from bastion host"
	export IP_ADDR=$(cat ${SSH_KEY_FILE}.ip)
	ssh ec2-user@${BASTION_IP} "ssh-keygen -R ${IP_ADDR}"
	echo "Head node keys deleted from bastion host's known_hosts"
fi

# Delete the local copy of the SSH key file
rm -f ${SSH_KEY_FILE}
rm -f ${SSH_KEY_FILE}.admin
rm -rf ${SSH_KEY_FILE}.ip
echo "SSH keyfiles deleted locally" 

# If an error was detected above, exit; otherwise, check that the cluster is being deleted
if [ $ERROR != "null" ]
then
	exit 1
else
	export IS_DELETED=$(echo $CLUSTER | jq -r '.cluster | .clusterStatus')

	if [ $IS_DELETED = "DELETE_IN_PROGRESS" ]
	then
		echo "Cluster '${VLAB_ID}_${PROJECT_ID}' is shutting down"
	else
		echo "Cluster '${VLAB_ID}_${PROJECT_ID}' has been deleted"
	fi
fi

