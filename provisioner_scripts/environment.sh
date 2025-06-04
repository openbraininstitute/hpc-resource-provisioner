#!/usr/bin/env bash

export CLUSTER_NAME=$1

echo "CLUSTER_NAME=${CLUSTER_NAME}" >> /etc/environment

curl --create-dirs --output /opt/slurm/etc/scripts/prolog.d/80_cloudwatch_agent_config_prolog.sh --create-file-mode 0755 https://raw.githubusercontent.com/openbraininstitute/hpc-resource-provisioner/refs/heads/main/provisioner_scripts/headnode/80_cloudwatch_agent_config_prolog.sh
