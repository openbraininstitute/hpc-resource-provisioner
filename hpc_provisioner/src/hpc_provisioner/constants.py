from pathlib import Path

PCLUSTER_CONFIG_TPL = str(Path(__file__).parent / "config" / "compute_cluster.tpl.yaml")
VLAB_TAG_KEY = "obp:costcenter:vlabid"
PROJECT_TAG_KEY = "obp:costcenter:project"
BILLING_TAG_KEY = "SBO_Billing"
BILLING_TAG_VALUE = "hpc:parallelcluster"
AVAILABLE_IPS_IN_UNUSED_SUBNET = 251
REGION = "us-east-1"  # TODO: don't hardcode?

DEFAULTS = {
    "tier": "lite",
    "fs_type": "efs",
    "project_id": "-",
}

CONFIG_VALUES = {}
