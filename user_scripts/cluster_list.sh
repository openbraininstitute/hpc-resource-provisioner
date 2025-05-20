#!/bin/bash

## Print the list of all the existing clusters with a summary status. The raw output is passed through 'jq'
##
## Note: This script does NOT check for any possible error


# AWS credentials and needed data
export AWS_ACCESS_KEY_ID=$(awk '/^aws_access_key_id/ {print $3}' ~/.aws/credentials)
export AWS_SECRET_ACCESS_KEY=$(awk '/^aws_secret/ {print $3}' ~/.aws/credentials)
export AWS_APIGW_DEPLOY_ID=""
export AWS_REGION="us-east-1"

# Get the list of clusters
CL=$(curl -X GET --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" --aws-sigv4 "aws:amz:"${AWS_REGION}":execute-api" https://${AWS_APIGW_DEPLOY_ID}.execute-api."${AWS_REGION}".amazonaws.com/production/hpc-provisioner/pcluster | jq)

echo ${CL} | jq

