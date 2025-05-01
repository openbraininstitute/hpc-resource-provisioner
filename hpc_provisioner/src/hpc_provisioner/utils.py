import os

from cryptography.hazmat.primitives import serialization


def _get_bucket_from_env(var_name: str) -> str:
    if bucket := os.environ.get(var_name):
        return bucket
    else:
        raise ValueError(f"{var_name} not set")


def get_sbonexusdata_bucket() -> str:
    return _get_bucket_from_env("SBO_NEXUSDATA_BUCKET")


def get_containers_bucket() -> str:
    return _get_bucket_from_env("CONTAINERS_BUCKET")


def get_scratch_bucket() -> str:
    return _get_bucket_from_env("SCRATCH_BUCKET")


def get_efa_security_group_id() -> str:
    return _get_bucket_from_env("EFA_SG_ID")


def generate_public_key(key_material):
    private_key = serialization.load_pem_private_key(key_material.encode(), password=None)
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH, format=serialization.PublicFormat.OpenSSH
    )
    return public_bytes.decode("utf-8")
