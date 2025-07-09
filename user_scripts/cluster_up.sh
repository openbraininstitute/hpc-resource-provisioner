#!/bin/bash

## This script:
## 1. Calls HPC provisioner to create a cluster with the 'cluster name' defined in the variables below
## 2. Calls 'aws secretsmanager' to get the SSH key file of the new cluster
##
## For simplicity, the SSH key filename is the name of the cluster (<VLAB_ID>_<PROJECT_ID>)
##
## Notes:
## - This script assumes the following:
##     - The sequence of cluster_up + cluster_status + cluster_down scripts are called in this order
## - This script does NOT check for every possible error
## - This script allows tuning the cluster through some variables
## - If a cluster name is passed as a parameter, this variable is used instead of creating a new name
##     - VLAB_ID and PROJECT_ID can't contain "_", so the underscore is a valid delimiter to later recover
##       them from the cluster name


# AWS credentials and needed data
export AWS_ACCESS_KEY_ID=$(awk '/^aws_access_key_id/ {print $3}' ~/.aws/credentials)
export AWS_SECRET_ACCESS_KEY=$(awk '/^aws_secret/ {print $3}' ~/.aws/credentials)
export AWS_APIGW_DEPLOY_ID=""
export AWS_REGION="us-east-1"

# Default cluster name (VLAB_ID and PROJECT_ID), with automatic creation date for easy identification and uniqueness
# Date format is YYYY-MM-DD-hh-mm
export VLAB_ID="$(date '+%Y-%m-%d-%Hh%M')"
export PROJECT_ID="my-project"

# Overwrite default values if an argument is passed to the script
if [ "$1" ]; then
	# Get the VLAB ID and the Project ID from the cluster name
	IFS='_' read -r -a ARG <<< "$1"
	export VLAB_ID="${ARG[0]}"
	export PROJECT_ID="${ARG[1]}"
fi

export SSH_KEY_FILE="${VLAB_ID}_${PROJECT_ID}"

# Cluster custom parameters
## Mount FSx Lustre storage
export LUSTRE="true"
## Benchmark mounts the whole FSx scratch
export BENCHMARK="false"
## EC2 instance type
export TIER="mixed-prod-mpi" # c7a and c6a

# Cluster creation call
echo "Calling the creation of cluster '${VLAB_ID}_${PROJECT_ID}'"
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

export COMMAND=${COMMAND}"project_id\="${PROJECT_ID}"\&tier\="${TIER}"\&vlab_id\="${VLAB_ID}
echo "+ ${COMMAND} | jq"
export CLUSTER=$(eval "${COMMAND}")

echo "Cluster creation requested with cluster name: '${VLAB_ID}_${PROJECT_ID}'"

# Check for creation errors: if 'message' field is present, there's an error
export ERROR=$(echo ${CLUSTER} | jq -r '.message')
if [ $ERROR != "null" ]
then
	echo "Error creating cluster:"
	echo "${CLUSTER}" | jq
	exit 1
fi

# Cluster creation request succeeded beyond this point
echo "Cluster info:"
echo "${CLUSTER}" | jq

# Create SSH key file
touch ${SSH_KEY_FILE}
chmod 0600 ${SSH_KEY_FILE}
export CLUSTER_SSH_KEY_ARN=$(echo ${CLUSTER} | jq -r '.cluster.private_ssh_key_arn')
if [ $CLUSTER_SSH_KEY_ARN = "null" ]
then
	echo "Error: could not get the cluster SSH key arn"
else
	echo "Getting arn key for: ${CLUSTER_SSH_KEY_ARN}"
	aws secretsmanager get-secret-value --secret-id=${CLUSTER_SSH_KEY_ARN} | jq -r .SecretString >| ${SSH_KEY_FILE}
	echo "Secret key stored in ${SSH_KEY_FILE}"
fi

export ADMIN_KEY_FILE="${SSH_KEY_FILE}.admin"
touch $ADMIN_KEY_FILE
chmod 0600 ${ADMIN_KEY_FILE}
export CLUSTER_SSH_KEY_ARN_ADMIN=$(echo ${CLUSTER} | jq -r '.cluster.admin_user_private_ssh_key_arn')
if [ $CLUSTER_SSH_KEY_ARN_ADMIN = "null" ]
then
	echo "Error: could not get the cluster admin SSH key arn"
else
	echo "Getting arn admin key for: ${CLUSTER_SSH_KEY_ARN_ADMIN}"
	aws secretsmanager get-secret-value --secret-id=${CLUSTER_SSH_KEY_ARN_ADMIN} | jq -r .SecretString >| ${ADMIN_KEY_FILE}
	echo "Secret key stored in ${ADMIN_KEY_FILE}"
fi

export CFG_FILE="${SSH_KEY_FILE}.config"
echo "{" > ${CFG_FILE}
echo "  \"config\": {" >> ${CFG_FILE}
echo "    \"vlab_id\": \"${VLAB_ID}\"," >> ${CFG_FILE}
echo "    \"project_id\": \"${PROJECT_ID}\"," >> ${CFG_FILE}
echo "    \"lustre\": ${LUSTRE}," >> ${CFG_FILE}
echo "    \"benchmark\": ${BENCHMARK}," >> ${CFG_FILE}
echo "    \"tier\": \"${TIER}\"" >> ${CFG_FILE}
echo "  }," >> ${CFG_FILE}
echo "  \"aws\": {" >> ${CFG_FILE}
echo "    \"aws_api_gw\": \"${AWS_APIGW_DEPLOY_ID}\"," >> ${CFG_FILE}
echo "    \"aws_region\": \"${AWS_REGION}\"," >> ${CFG_FILE}
echo "    \"ssh_key_file\": \"${SSH_KEY_FILE}\"," >> ${CFG_FILE}
echo "    \"ssh_admin_file\": \"${ADMIN_KEY_FILE}\"" >> ${CFG_FILE}
echo "  }" >> ${CFG_FILE}
echo "}" >> ${CFG_FILE}

