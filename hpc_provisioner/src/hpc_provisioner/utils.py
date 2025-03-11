import os

from cryptography.hazmat.primitives import serialization


def get_sbonexusdata_bucket():
    return os.environ.get("SBO_NEXUSDATA_BUCKET")


def get_containers_bucket():
    return os.environ.get("CONTAINERS_BUCKET")


def get_scratch_bucket():
    return os.environ.get("SCRATCH_BUCKET")


def generate_public_key(key_material):
    private_key = serialization.load_pem_private_key(key_material.encode(), password=None)
    public_key = private_key.public_key()
    public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH, format=serialization.PublicFormat.OpenSSH
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH, format=serialization.PublicFormat.OpenSSH
    )
    return public_bytes.decode("utf-8")
