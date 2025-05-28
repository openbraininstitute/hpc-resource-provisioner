import os

from cryptography.hazmat.primitives import serialization


def _get_env_var(var_name: str) -> str:
    if value := os.environ.get(var_name):
        return value
    else:
        raise ValueError(f"{var_name} not set")


def get_sbonexusdata_bucket() -> str:
    return _get_env_var("SBO_NEXUSDATA_BUCKET")


def get_containers_bucket() -> str:
    return _get_env_var("CONTAINERS_BUCKET")


def get_scratch_bucket_arn() -> str:
    return _get_env_var("SCRATCH_BUCKET_ARN")


def get_scratch_bucket() -> str:
    return _get_env_var("SCRATCH_BUCKET")


def get_efa_security_group_id() -> str:
    return _get_env_var("EFA_SG_ID")


def get_fsx_policy_arn() -> str:
    return _get_env_var("FSX_POLICY_ARN")


def get_datasync_role_arn() -> str:
    return _get_env_var("DATASYNC_ROLE_ARN")


def get_datasync_log_group_arn() -> str:
    return _get_env_var("DATASYNC_LOG_GROUP_ARN")


def generate_public_key(key_material):
    private_key = serialization.load_pem_private_key(key_material.encode(), password=None)
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH, format=serialization.PublicFormat.OpenSSH
    )
    return public_bytes.decode("utf-8")
