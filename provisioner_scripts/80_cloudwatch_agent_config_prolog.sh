#!/bin/bash

mkdir -p /opt/slurm/etc/scripts/prolog.d

cat << _EOF_ >> /opt/slurm/etc/scripts/prolog.d/80_cloudwatch_agent_config_prolog.sh
#!/bin/bash

CWAGENT_CONFIG=/sbo/data/scratch/CWAgent_config_\$SLURM_CLUSTER_NAME.json

if [ ! -f \$CWAGENT_CONFIG ]; then
	echo "Create CWAGENT_CONFIG " \$CWAGENT_CONFIG
	sed "s/\\$CLUSTER_NAME/\$SLURM_CLUSTER_NAME/g" /opt/slurm/CWAgent_config_tpl.json > \$CWAGENT_CONFIG
fi

sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/\$CWAGENT_CONFIG -s
_EOF_

chmod 755 /opt/slurm/etc/scripts/prolog.d/80_cloudwatch_agent_config_prolog.sh

cat << _EOF_ >> /opt/slurm/CWAgent_config_tpl.json

{
	"agent": {
                "metrics_collection_interval": 60,
                "run_as_user": "root"
        },
        "metrics": {
		"namespace": "CustomMetrics_test",
		"aggregation_dimensions": [
       			["ClusterName", "InstanceId"]
       		],
                "append_dimensions": {
                        "InstanceId": "\${aws:InstanceId}"
                },
	        "metrics_collected": {
                	"disk": {
       				"append_dimensions":{
					"ClusterName": "\$CLUSTER_NAME"
				},
                                 "measurement": [
                                        "used_percent"
                                ],
                                "resources": [
                                        "*"
                                ]
                        },
                        "mem": {
				"append_dimensions":{
					"ClusterName": "\$CLUSTER_NAME"
				},
                                "measurement": [
                                        "mem_used_percent"
                                ]
                        },
			"cpu": {
       				"append_dimensions":{
					"ClusterName": "\$CLUSTER_NAME"
				},
        			"measurement": [
            				"cpu_usage_active"
        			],
        			"totalcpu": true
    				}
                }
        }
}
_EOF_
