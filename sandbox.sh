#!/usr/bin/env bash


export AWS_ACCESS_KEY_ID=$(awk '/^aws_access_key_id/ {print $3}' ~/.aws/credentials | head -n 1)
export AWS_SECRET_ACCESS_KEY=$(awk '/^aws_secret/ {print $3}' ~/.aws/credentials | head -n 1)
export AWS_APIGW_DEPLOY_ID="4gnhfu4jk8"
export AWS_REGION="us-east-1"
