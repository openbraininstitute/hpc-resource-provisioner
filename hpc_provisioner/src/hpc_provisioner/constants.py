from pathlib import Path

PCLUSTER_CONFIG_TPL = str(Path(__file__).parent / "config" / "compute_cluster.tpl.yaml")
PCLUSTER_DEV_CONFIG_TPL = str(Path(__file__).parent / "config-dev" / "compute_cluster.tpl.yaml")
VLAB_TAG_KEY = "obp:costcenter:vlabid"
PROJECT_TAG_KEY = "obp:costcenter:project"
BILLING_TAG_KEY = "SBO_Billing"
BILLING_TAG_VALUE = "hpc:parallelcluster"
AVAILABLE_IPS_IN_UNUSED_SUBNET = 251
REGION = "us-east-1"  # TODO: don't hardcode?

DEFAULTS = {
    "tier": "debug",
    "project_id": "-",
    "dev": "false",
    "benchmark": "false",
    "include_lustre": "true",
}

CONFIG_VALUES = {}

DRA_CHECKING_RULE_NAME = "resource_provisioner_check_for_dra"
DRAS = [
    {
        "name": "projects",
        "mountpoint": "/sbo/data/projects",
        "writable": False,
    },
    {
        "name": "scratch",
        "mountpoint": "/sbo/data/scratch",
        "writable": True,
    },
]
