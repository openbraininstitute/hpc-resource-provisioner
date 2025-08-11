#!/bin/bash

## Print the list of all existing clusters with a summary status.
## The raw output is parsed through 'jq' for nicer formatting
##
## Note: This script does NOT check for every possible error


# AWS credentials and needed data
export AWS_ACCESS_KEY_ID=$(awk '/^aws_access_key_id/ {print $3}' ~/.aws/credentials)
export AWS_SECRET_ACCESS_KEY=$(awk '/^aws_secret/ {print $3}' ~/.aws/credentials)
export AWS_APIGW_DEPLOY_ID=""
export AWS_REGION="us-east-1"

# Get the list of clusters
export COMMAND="curl -X GET --user \""${AWS_ACCESS_KEY_ID}":"${AWS_SECRET_ACCESS_KEY}"\" --aws-sigv4 \"aws:amz:"${AWS_REGION}":execute-api\" https://"${AWS_APIGW_DEPLOY_ID}".execute-api."${AWS_REGION}".amazonaws.com/production/hpc-provisioner/pcluster"

echo "+ ${COMMAND} | jq"
export CLUSTER_LIST=$(eval "${COMMAND}")
echo ${CLUSTER_LIST}

# Check for errors: if 'message' field is present, there's an error
export ERROR=$(echo ${CLUSTER_LIST} | jq -r '.message')
if [ $ERROR != "null" ]
then
    echo "Error listing existing clusters:"
    echo "${CLUSTER_LIST}" | jq
    exit 1
fi

echo ${CLUSTER_LIST} | jq

