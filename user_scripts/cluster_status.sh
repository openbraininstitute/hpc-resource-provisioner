#!/bin/bash

## Given a cluster name (<VLAB_ID>_<PROJECT_ID>), it prints the status of the cluster.
## The raw output is parsed through 'jq' for nicer formatting
##
## In addition, it parses the output to check for:
## - The creation of the head node of the cluster. If it is created:
##     - It copies the SSH key file to the bastion host, so that SSH login works properly
##     - It outputs the SSH commands needed to login to the bastion host and to the head node
## - The cluster status (clusterStatus entry) and outputs its status
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

# Query for cluster status
echo "Checking the status of cluster '${VLAB_ID}_${PROJECT_ID}'"
export COMMAND="curl -X GET --user \""${AWS_ACCESS_KEY_ID}":"${AWS_SECRET_ACCESS_KEY}"\" --aws-sigv4 \"aws:amz:"${AWS_REGION}":execute-api\" https://"${AWS_APIGW_DEPLOY_ID}".execute-api."${AWS_REGION}".amazonaws.com/production/hpc-provisioner/pcluster\?project_id\="${PROJECT_ID}"\&vlab_id\="${VLAB_ID}
echo "+ ${COMMAND} | jq"
export CLUSTER_STATUS=$(eval "${COMMAND}")

# Check for errors: if 'message' field is present, there's an error
export ERROR=$(echo ${CLUSTER_STATUS} | jq -r '.message')
if [ $ERROR != "null" ]
then
    echo "Error querying for cluster status:"
    echo "${CLUSTER_STATUS}" | jq
    exit 1
fi

echo ${CLUSTER_STATUS} | jq

# Bastion host IP
export BASTION_IP="98.84.40.226"

# Check if head node has been created (IP address exists?)
export IP_ADDR=$(echo $CLUSTER_STATUS | jq -r '.headNode | .privateIpAddress')

if [[ -n "$IP_ADDR" && "$IP_ADDR" != 'null'  ]]
then
	# Check if secret key already copied
	if ssh ec2-user@${BASTION_IP} test -f "~/.ssh/${SSH_KEY_FILE}"
	then
		echo "Head node is ready and secret key is already copied"
	else
		echo "Head node is ready, copying secret key..."
		scp ${SSH_KEY_FILE} ec2-user@${BASTION_IP}:~/.ssh
		scp ${SSH_KEY_FILE}.admin ec2-user@${BASTION_IP}:~/.ssh
		echo "Saving head node IP in ${SSH_KEY_FILE}.ip"
		echo $IP_ADDR > ${SSH_KEY_FILE}.ip
	fi

	echo "You can now login to the head node:"
	echo "ssh ec2-user@${BASTION_IP}"
	echo "ssh -i ~/.ssh/${SSH_KEY_FILE}.admin ${IP_ADDR}"
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
	echo "Cluster deployment in progress"

elif [ $IS_READY = "DELETE_IN_PROGRESS" ]
then
	echo "Cluster is shutting down"

else
	export STATUS=$(echo $CLUSTER_STATUS | jq -r '.project_id')
	if [ $STATUS != "null" ]
	then
		echo "Data provisioning is in progress, cluster provisioning will come next"
	else
		echo "Something went wrong with the cluster"
	fi
fi

