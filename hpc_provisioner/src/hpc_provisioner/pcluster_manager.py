#!/usr/bin/env python

import logging
import logging.config
import pathlib
import tempfile

# This is the top-level script to create a Parallel Cluster
# It requires the `base_system` terraform to have been applied. If not it will error out.
from pathlib import Path

import yaml
from pcluster import lib as pc

from hpc_provisioner.logging_config import LOGGING_CONFIG
from hpc_provisioner.yaml_loader import load_yaml_extended

PCLUSTER_CONFIG_TPL = str(Path(__file__).parent / "config" / "compute_cluster.tpl.yaml")
VLAB_TAG_KEY = "obp:costcenter:vlabid"
PROJECT_TAG_KEY = "obp:costcenter:project"
REGION = "us-east-1"  # TODO: don't hardcode?

DEFAULTS = {
    "tier": "lite",
    "fs_type": "efs",
    "project_id": "-",
}

CONFIG_VALUES = {
    "base_subnet_id": "subnet-021910397b5213f7b",  # Compute-0 # TODO: Dynamic
    # "base_subnet_id": "subnet-061e82790d3f3fafc",  # Compute-0 # TODO: Dynamic
    "base_security_group_id": "sg-0a22b30ec4989f0ba",  # sbo-poc-compute-hpc-sg
    "efs_id": "fs-0e64b596272e62bb2",  # Home
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


class PClusterError(Exception):
    """An error reported by PCluster"""


class InvalidRequest(Exception):
    """When the request is invalid, likely due to invalid or missing data"""


def pcluster_create(vlab_id: str, options: dict):
    """Create a pcluster for a given vlab

    Args:
        vlab_id: The id of the vlab
        options: a dict of user provided options.
            All possible options can be seen in DEFAULTS.

    """
    logger.info(f"Creating pcluster: {vlab_id}")
    for k, default in DEFAULTS.items():
        options.setdefault(k, default)

    logger.debug("Loading default pcluster config")
    with open(PCLUSTER_CONFIG_TPL, "r") as f:
        pcluster_config = load_yaml_extended(f, CONFIG_VALUES)

    logger.debug("Adding tags")
    # Add tags
    tags = pcluster_config["Tags"]
    tags.append({"Key": VLAB_TAG_KEY, "Value": vlab_id})
    tags.append({"Key": PROJECT_TAG_KEY, "Value": options.get("project_id")})
    logger.debug(f"Tags: {tags}")

    if options["tier"] == "lite":
        queues = pcluster_config["Scheduling"]["SlurmQueues"]
        del queues[1:]

    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    output_file = f"deployment-{cluster_name}.yaml"
    output_file = tempfile.NamedTemporaryFile(delete=False)

    logger.debug(f"Writing pcluster config to {output_file.name}")
    with open(output_file.name, "w") as out:
        yaml.dump(pcluster_config, out, sort_keys=False)

    try:
        logger.debug("Actual create_cluster command")
        return pc.create_cluster(cluster_name=cluster_name, cluster_configuration=output_file.name)
    except Exception as e:
        raise PClusterError from e
    finally:
        logger.debug("Cleaning up temporary config file")
        pathlib.Path(output_file.name).unlink()
        logger.debug("Cleaned up temporary config file")


def pcluster_describe(vlab_id: str):
    """Describe a cluster, given the vlab_id"""
    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    return pc.describe_cluster(cluster_name=cluster_name, region=REGION)


def pcluster_delete(vlab_id: str):
    """Destroy a cluster, given the vlab_id"""
    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    return pc.delete_cluster(cluster_name=cluster_name, region=REGION)
