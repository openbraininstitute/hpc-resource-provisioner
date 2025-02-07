#!/usr/bin/env python
# This is the top-level script to create a Parallel Cluster
# It requires the `base_system` terraform to have been applied. If not it will error out.

import logging
import logging.config
import pathlib
import tempfile

import boto3
import yaml
from botocore.client import ClientError
from pcluster import lib as pc

from hpc_provisioner.aws_queries import (
    get_available_subnet,
    get_cluster_name,
    get_efs,
    get_security_group,
    release_subnets,
    remove_key,
)
from hpc_provisioner.constants import (
    BILLING_TAG_KEY,
    BILLING_TAG_VALUE,
    CONFIG_VALUES,
    DEFAULTS,
    PCLUSTER_CONFIG_TPL,
    PCLUSTER_DEV_CONFIG_TPL,
    PROJECT_TAG_KEY,
    REGION,
    VLAB_TAG_KEY,
)
from hpc_provisioner.logging_config import LOGGING_CONFIG
from hpc_provisioner.yaml_loader import load_yaml_extended

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


class PClusterError(Exception):
    """An error reported by PCluster"""


class InvalidRequest(Exception):
    """When the request is invalid, likely due to invalid or missing data"""


def pcluster_create(vlab_id: str, project_id: str, keyname: str, options: dict = None):
    """Create a pcluster for a given vlab

    Args:
        vlab_id: The id of the vlab
        project_id: The id of the project within the vlab
        options: a dict of user provided options.
            All possible options can be seen in DEFAULTS.

    """
    logger.info(f"Creating pcluster: {vlab_id}-{project_id} with options {options}")
    if not options:
        options = {}
    for k, default in DEFAULTS.items():
        options.setdefault(k, default)

    cluster_name = get_cluster_name(vlab_id, project_id)

    try:
        cloudformation_client = boto3.client("cloudformation")
        cloudformation_client.describe_stacks(StackName=cluster_name)
        logger.debug(f"Stack {cluster_name} already exists - nothing to do")
        return
    except ClientError:
        logger.debug(f"Stack {cluster_name} does not exist yet - creating")

    ec2_client = boto3.client("ec2")
    efs_client = boto3.client("efs")

    # base_security_group_id, efs_id and ssh_key should be fairly static and change only if
    # something changes about the deployment.
    # base_subnet_id is where the interesting stuff happens
    CONFIG_VALUES["base_subnet_id"] = get_available_subnet(ec2_client, cluster_name)
    CONFIG_VALUES["base_security_group_id"] = get_security_group(ec2_client)
    CONFIG_VALUES["efs_id"] = get_efs(efs_client)
    CONFIG_VALUES["ssh_key"] = keyname
    logger.debug(f"Config values: {CONFIG_VALUES}")
    if options["dev"].lower() == "true":
        pcluster_config_path = PCLUSTER_DEV_CONFIG_TPL
    else:
        pcluster_config_path = PCLUSTER_CONFIG_TPL
    with open(pcluster_config_path, "r") as f:
        pcluster_config = load_yaml_extended(f, CONFIG_VALUES)

    logger.debug("Adding tags")
    logger.debug(f"pcluster_config: {pcluster_config}")
    tags = pcluster_config.get("Tags", [])
    tags.append({"Key": VLAB_TAG_KEY, "Value": vlab_id})
    tags.append({"Key": PROJECT_TAG_KEY, "Value": project_id})
    tags.append({"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE})
    logger.debug(f"Tags: {tags}")

    if options["tier"] == "lite":
        queues = pcluster_config["Scheduling"]["SlurmQueues"]
        del queues[1:]

    output_file = f"deployment-{cluster_name}.yaml"
    output_file = tempfile.NamedTemporaryFile(delete=False)

    logger.debug(f"Writing pcluster config to {output_file.name}")
    with open(output_file.name, "w") as out:
        yaml.dump(pcluster_config, out, sort_keys=False)

    logger.debug(f"pcluster config is {pcluster_config}")

    try:
        logger.debug("Actual create_cluster command")
        return pc.create_cluster(cluster_name=cluster_name, cluster_configuration=output_file.name)
    finally:
        logger.debug("Cleaning up temporary config file")
        pathlib.Path(output_file.name).unlink()
        logger.debug("Cleaned up temporary config file")


def pcluster_list():
    """List the existing pclusters"""
    return pc.list_clusters(region=REGION)


def pcluster_describe(vlab_id: str, project_id: str):
    """Describe a cluster, given the vlab_id and project_id"""
    cluster_name = get_cluster_name(vlab_id, project_id)
    return pc.describe_cluster(cluster_name=cluster_name, region=REGION)


def pcluster_delete(vlab_id: str, project_id: str):
    """Destroy a cluster, given the vlab_id and project_id"""
    cluster_name = get_cluster_name(vlab_id, project_id)
    release_subnets(cluster_name)
    remove_key(cluster_name)
    return pc.delete_cluster(cluster_name=cluster_name, region=REGION)
