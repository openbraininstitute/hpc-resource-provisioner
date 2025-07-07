#!/bin/bash

## This script:
## 1. Calls HPC provisioner to create a cluster with the <PROJECT_ID> defined in the variable below
## 2. Calls 'aws secretsmanager' to get the SSH key file of the new cluster
##
## For simplicity, the SSH key filename is the name of the cluster (<PROJECT_ID>)
##
## Notes:
## - This script assumes the following:
##     - The sequence of cluster_up + cluster_status + cluster_down scripts are called in this order
## - This script does NOT check for every possible error
## - This script allows tuning the cluster through some variables


# AWS credentials and needed data
export AWS_ACCESS_KEY_ID=$(awk '/^aws_access_key_id/ {print $3}' ~/.aws/credentials)
export AWS_SECRET_ACCESS_KEY=$(awk '/^aws_secret/ {print $3}' ~/.aws/credentials)
export AWS_APIGW_DEPLOY_ID=""
export AWS_REGION="us-east-1"

# PROJECT_ID, with automatic creation date for easy identification and uniqueness (date format is YYYY-MM-DD-hh-mm)
export PROJECT_ID="$(date '+%Y-%m-%d-%Hh%M')"
export SSH_KEY_FILE=${PROJECT_ID}

#VLAB_ID set to the username
export VLAB_ID=${USER}

# Cluster custom parameters
## Mount FSx Lustre storage
export LUSTRE="true"
## Benchmark mounts the whole FSx scratch
export BENCHMARK="false"
## EC2 instance type
export TIER="mixed-prod-mpi" # c7a and c6a

# Cluster creation call
echo "Calling cluster creation of ${PROJECT_ID}"
export COMMAND="curl -X POST --user \""${AWS_ACCESS_KEY_ID}":"${AWS_SECRET_ACCESS_KEY}"\" --aws-sigv4 \"aws:amz:"${AWS_REGION}":execute-api\" https://"${AWS_APIGW_DEPLOY_ID}".execute-api."${AWS_REGION}".amazonaws.com/production/hpc-provisioner/pcluster\?"

# Parameters need to go alphabetically ordered
if [ "${BENCHMARK}" = "true" ]; then
    # False by default
    export COMMAND=${COMMAND}"benchmark\=true\&"
fi
if [ "${LUSTRE}" = "false" ]; then
    # True by default
    export COMMAND=${COMMAND}"include_lustre\=false\&"
fi

export COMMAND=${COMMAND}"project_id\="${PROJECT_ID}"\&tier\="${TIER}"\&vlab_id\="${VLAB_ID}" | jq"
echo "+ ${COMMAND}"
export CLUSTER=$(eval "${COMMAND}")

echo "Cluster creation requested with ID '${PROJECT_ID}'"
echo "Cluster info:"
echo "${CLUSTER}" | jq

# Create SSH key file
touch ${PROJECT_ID}
chmod 0600 ${PROJECT_ID}
export CLUSTER_SSH_KEY_ARN=$(echo ${CLUSTER} | jq -r '.cluster.private_ssh_key_arn')
if [ $CLUSTER_SSH_KEY_ARN = "null" ]
then
	echo "Error: could not get the cluster SSH key file"
else
	echo "Getting arn key for: ${CLUSTER_SSH_KEY_ARN}"
	aws secretsmanager get-secret-value --secret-id=${CLUSTER_SSH_KEY_ARN} | jq -r .SecretString >| ${SSH_KEY_FILE}
	echo "Secret key stored in ${SSH_KEY_FILE}"
fi

export ADMIN_KEY=${PROJECT_ID}_admin
touch $ADMIN_KEY
chmod 0600 ${ADMIN_KEY}
export CLUSTER_SSH_KEY_ARN_ADMIN=$(echo ${CLUSTER} | jq -r '.cluster.admin_user_private_ssh_key_arn')
if [ $CLUSTER_SSH_KEY_ARN_ADMIN = "null" ]
then
	echo "Error: could not get the cluster admin SSH key file"
else
	echo "Getting arn admin key for: ${CLUSTER_SSH_KEY_ARN_ADMIN}"
	aws secretsmanager get-secret-value --secret-id=${CLUSTER_SSH_KEY_ARN_ADMIN} | jq -r .SecretString >| ${ADMIN_KEY}
	echo "Secret key stored in ${ADMIN_KEY}"
fi

