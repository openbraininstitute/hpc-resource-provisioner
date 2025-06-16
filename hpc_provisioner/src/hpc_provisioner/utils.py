import json
import os
from typing import List

from cryptography.hazmat.primitives import serialization

from hpc_provisioner.cluster import Cluster


def _get_env_var(var_name: str) -> str:
    if value := os.environ.get(var_name):
        return value
    else:
        raise ValueError(f"{var_name} not set")


def get_sbonexusdata_bucket() -> str:
    return _get_env_var("SBO_NEXUSDATA_BUCKET")


def get_containers_bucket() -> str:
    return _get_env_var("CONTAINERS_BUCKET")


def get_scratch_bucket() -> str:
    return _get_env_var("SCRATCH_BUCKET")


def get_projects_bucket() -> str:
    return _get_env_var("PROJECTS_BUCKET")


def get_efa_security_group_id() -> str:
    return _get_env_var("EFA_SG_ID")


def get_fsx_policy_arn() -> str:
    return _get_env_var("FSX_POLICY_ARN")


def get_suffix() -> str:
    return _get_env_var("SUFFIX")


def get_fs_subnet_ids() -> List[str]:
    return json.loads(_get_env_var("FS_SUBNET_IDS"))


def get_fs_sg_id() -> str:
    return _get_env_var("FS_SG_ID")


def get_eventbridge_role_arn() -> str:
    return _get_env_var("EVENTBRIDGE_ROLE_ARN")


def get_api_gw_arn() -> str:
    return _get_env_var("API_GW_STAGE_ARN")


def get_fs_bucket(bucket_name: str, cluster: Cluster) -> str:
    if bucket_name == "projects":
        return get_sbonexusdata_bucket()
    elif bucket_name == "scratch":
        return f"{get_scratch_bucket()}/{cluster.vlab_id}/{cluster.project_id}"
    else:
        raise NotImplementedError(f"Can't get fs bucket for {bucket_name}")


def get_ami_id() -> str:
    return _get_env_var("PCLUSTER_AMI_ID")


def generate_public_key(key_material):
    private_key = serialization.load_pem_private_key(key_material.encode(), password=None)
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH, format=serialization.PublicFormat.OpenSSH
    )
    return public_bytes.decode("utf-8")
