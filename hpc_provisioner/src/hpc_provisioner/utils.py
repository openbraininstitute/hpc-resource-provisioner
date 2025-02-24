import os


def get_sbonexusdata_bucket():
    return os.environ.get("SBO_NEXUSDATA_BUCKET")


def get_containers_bucket():
    return os.environ.get("CONTAINERS_BUCKET")


def get_scratch_bucket():
    return os.environ.get("SCRATCH_BUCKET")
