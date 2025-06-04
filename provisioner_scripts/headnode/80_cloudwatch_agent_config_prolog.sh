#!/bin/bash

CWAGENT_CONFIG=/sbo/data/scratch/CWAgent_config_$SLURM_CLUSTER_NAME.json

if [ ! -f $CWAGENT_CONFIG ]; then
	echo "Create CWAGENT_CONFIG " $CWAGENT_CONFIG
	sed "s/\$CLUSTER_NAME/$SLURM_CLUSTER_NAME/g" /sbo/data/scratch/CWAgent_config_tpl.json > $CWAGENT_CONFIG
fi

#sudo /opt/slurm/bin/srun --ntasks=$NODES --ntasks-per-node=1 /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a stop
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/$CWAGENT_CONFIG -s

