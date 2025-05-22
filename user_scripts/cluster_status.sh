#!/bin/bash

## Given a PROJECT_ID, it checks for the status of a cluster and prints the raw output through 'jq'
##
## In addition, it parses the output to check for:
## - The creation of the head node of the cluster. If it is created:
##     - It copies the SSH key file to the bastion host, so that SSH login works properly
##     - It outputs the SSH commands needed to login to the bastion host and to the head node
## - The cluster status (clusterStatus entry) and outputs its status
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
export SSH_KEY_FILE=${PROJECT_ID} # assumes SSH key filename is equal to the PROJECT_ID

# Query for cluster status
echo "Checking cluster status for ${PROJECT_ID}"
export COMMAND="curl -X GET --user \""${AWS_ACCESS_KEY_ID}":"${AWS_SECRET_ACCESS_KEY}"\" --aws-sigv4 \"aws:amz:"${AWS_REGION}":execute-api\" https://"${AWS_APIGW_DEPLOY_ID}".execute-api."${AWS_REGION}".amazonaws.com/production/hpc-provisioner/pcluster\?project_id\="${PROJECT_ID}"\&vlab_id\="${VLAB_ID}" | jq"
echo "+ ${COMMAND}"
export CLUSTER_STATUS=$(eval "${COMMAND}")
echo ${CLUSTER_STATUS} | jq

# Check if head node has been created (IP address exists?)
export IP_ADDR=$(echo $CLUSTER_STATUS | jq -r '.headNode | .privateIpAddress')

if [[ -n "$IP_ADDR" && "$IP_ADDR" != 'null'  ]]
then
	# Check if secret key already copied
	if ssh -i ~/.ssh/id_rsa_aws ec2-user@107.22.159.90 test -f "~/.ssh/${SSH_KEY_FILE}"
	then
		echo "Head node is ready and secret key is already copied"
	else
		echo "Head node is ready, copying secret key..."
		scp -i ~/.ssh/id_rsa_aws ${SSH_KEY_FILE} ec2-user@107.22.159.90:~/.ssh
		scp -i ~/.ssh/id_rsa_aws ${SSH_KEY_FILE}_admin ec2-user@107.22.159.90:~/.ssh
		echo "Saving head node IP in ${SSH_KEY_FILE}_ip"
		echo $IP_ADDR > ${SSH_KEY_FILE}_ip
	fi

	echo "You can now login to the head node:"
	echo "ssh ec2-user@107.22.159.90"
	echo "ssh -i ~/.ssh/${SSH_KEY_FILE} sim@${IP_ADDR}"
else
	echo "Head node not ready yet"
fi

# Check if the cluster is ready to use
export IS_READY=$(echo $CLUSTER_STATUS | jq -r '.clusterStatus')

if [ $IS_READY = "CREATE_COMPLETE" ]
then
	echo "Cluster is ready to use"

elif [ $IS_READY = "CREATE_IN_PROGRESS" ]
then
	echo "Cluster not ready yet"

elif [ $IS_READY = "DELETE_IN_PROGRESS" ]
then
	echo "Cluster is shutting down"

else
	echo "Something went wrong with the cluster"
fi

