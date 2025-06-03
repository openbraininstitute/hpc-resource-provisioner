#!/usr/bin/env python
# This is the top-level script to create a Parallel Cluster
# It requires the `base_system` terraform to have been applied. If not it will error out.

import json
import logging
import logging.config
import pathlib
import tempfile
from typing import List, Optional

import boto3
import yaml
from botocore.client import ClientError
from pcluster import lib as pc
from pcluster.api.errors import CreateClusterBadRequestException, InternalServiceException

from hpc_provisioner.aws_queries import (
    create_fsx,
    get_available_subnet,
    get_cluster_name,
    get_efs,
    get_fsx,
    get_keypair_name,
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
from hpc_provisioner.utils import (
    get_containers_bucket,
    get_efa_security_group_id,
    get_fsx_policy_arn,
    get_sbonexusdata_bucket,
    get_scratch_bucket,
)
from hpc_provisioner.yaml_loader import load_yaml_extended

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


class PClusterError(Exception):
    """An error reported by PCluster"""


class InvalidRequest(Exception):
    """When the request is invalid, likely due to invalid or missing data"""


def populate_config(
    cluster_name: str,
    keyname: str,
    vlab_id: str,
    project_id: str,
    create_users_args: Optional[List[str]] = None,
    benchmark: Optional[bool] = False,
) -> None:
    """
    populate config values for loading cluster config yaml

    :param cluster_name: name of the cluster
    :param keyname: ssh key name
    :param create_users_args: arguments to create_users.py
    """
    ec2_client = boto3.client("ec2")
    efs_client = boto3.client("efs")
    # base_security_group_id and efs_id should be fairly static and change only if
    # something changes about the deployment.
    # base_subnet_id is where the interesting stuff happens
    CONFIG_VALUES["base_subnet_id"] = get_available_subnet(ec2_client, cluster_name)
    CONFIG_VALUES["base_security_group_id"] = get_security_group(ec2_client)
    CONFIG_VALUES["efs_id"] = get_efs(efs_client)
    CONFIG_VALUES["ssh_key"] = keyname
    CONFIG_VALUES["sbonexusdata_bucket"] = get_sbonexusdata_bucket()
    CONFIG_VALUES["containers_bucket"] = get_containers_bucket()
    CONFIG_VALUES["fsx_policy_arn"] = get_fsx_policy_arn()
    if benchmark:
        CONFIG_VALUES["scratch_bucket"] = get_scratch_bucket()
    else:
        CONFIG_VALUES["scratch_bucket"] = "/".join([get_scratch_bucket(), vlab_id, project_id])
    CONFIG_VALUES["efa_security_group_id"] = get_efa_security_group_id()
    if create_users_args:
        CONFIG_VALUES["create_users_args"] = create_users_args
    CONFIG_VALUES["environment_args"] = [get_cluster_name(vlab_id, project_id)]
    logger.debug(f"Config values: {CONFIG_VALUES}")


def populate_tags(pcluster_config: dict, vlab_id: str, project_id: str) -> list:
    tags = pcluster_config.get("Tags", [])
    logger.debug(f"Populating tags {tags}")
    tags.append({"Key": VLAB_TAG_KEY, "Value": vlab_id})
    tags.append({"Key": PROJECT_TAG_KEY, "Value": project_id})
    tags.append({"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE})
    logger.debug(f"Tags after populating: {tags}")
    return tags


def cluster_already_exists(cluster_name: str) -> bool:
    try:
        cloudformation_client = boto3.client("cloudformation")
        cloudformation_client.describe_stacks(StackName=cluster_name)
        logger.debug(f"Stack {cluster_name} already exists - nothing to do")
        return True
    except ClientError:
        logger.debug(f"Stack {cluster_name} does not exist yet - creating")
        return False


def load_pcluster_config(dev: bool) -> dict:
    if dev:
        pcluster_config_path = PCLUSTER_DEV_CONFIG_TPL
    else:
        pcluster_config_path = PCLUSTER_CONFIG_TPL
    with open(pcluster_config_path, "r") as f:
        logger.debug(f"Loading config {pcluster_config_path} with CONFIG_VALUES {CONFIG_VALUES}")
        pcluster_config = load_yaml_extended(f, CONFIG_VALUES)

    return pcluster_config


def choose_tier(pcluster_config: dict, options: dict) -> list:
    available_tiers = [q["Name"] for q in pcluster_config["Scheduling"]["SlurmQueues"]]
    if options["tier"] not in available_tiers:
        raise ValueError(
            f"Tier {options['tier']} not available - choose from {', '.join(available_tiers)}"
        )
    else:
        queues = pcluster_config["Scheduling"]["SlurmQueues"]
        queues = [next(q for q in queues if q["Name"] == options["tier"])]

    return queues


def write_config(cluster_name: str, pcluster_config: dict) -> str:
    output_file = f"deployment-{cluster_name}.yaml"
    output_file = tempfile.NamedTemporaryFile(delete=False)

    logger.debug(f"Writing pcluster config to {output_file.name}")
    with open(output_file.name, "w") as out:
        yaml.dump(pcluster_config, out, sort_keys=False)

    logger.debug(f"pcluster config is {pcluster_config}")

    return output_file.name


def pcluster_create(
    vlab_id: str,
    project_id: str,
    options: dict,
):
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
        if k in options and options[k] is None:
            options.pop(k)
        options.setdefault(k, default)

    logger.info(f"Creating pcluster: {vlab_id}-{project_id} with default-filled options {options}")
    cluster_name = get_cluster_name(vlab_id, project_id)

    if cluster_already_exists(cluster_name):
        return

    fsx_client = boto3.client("fsx")
    dev = options["dev"]
    benchmark = options["benchmark"]
    cluster_users = json.dumps(
        [
            {
                "name": "sim",
                "public_key": options["sim_pubkey"],
                "sudo": False,
                "folder_ownership": ["/sbo/data/scratch"],
            }
        ]
    )
    create_users_args = [
        f"--vlab-id={vlab_id}",
        f"--project-id={project_id}",
        f"--users={cluster_users}",
    ]

    populate_config(
        cluster_name, options["keyname"], vlab_id, project_id, create_users_args, benchmark
    )

    if dev:
        projects_fs = get_fsx(
            fsx_client=fsx_client,
            shared=True,
            fs_name="projects",
            vlab_id=vlab_id,
            project_id=project_id,
        )
        if not projects_fs:
            projects_fs = create_fsx(
                fsx_client=fsx_client,
                fs_name="projects",
                bucket=get_sbonexusdata_bucket(),
                shared=True,
                vlab_id=vlab_id,
                project_id=project_id,
            )
        CONFIG_VALUES["projects_fsx"] = {
            "Name": next(
                tag["Value"] for tag in projects_fs["FileSystem"]["Tags"] if tag["Key"] == "Name"
            ),
            "StorageType": "FsxLustre",
            "MountDir": "/sbo/data/scratch",
            "FsxLustreSettings": {"FileSystemId": projects_fs["FileSystem"]["FileSystemId"]},
        }

    pcluster_config = load_pcluster_config(dev)
    pcluster_config["Tags"] = populate_tags(pcluster_config, vlab_id, project_id)
    pcluster_config["Scheduling"]["SlurmQueues"] = choose_tier(pcluster_config, options)
    if not options["include_lustre"]:
        pcluster_config["SharedStorage"].pop(1)
    if benchmark:
        pcluster_config["HeadNode"]["CustomActions"]["OnNodeConfigured"]["Sequence"].append(
            {
                "Script": "s3://sboinfrastructureassets-sandbox/scripts/80_cloudwatch_agent_config_prolog.sh"
            }
        )

    output_file_name = write_config(cluster_name, pcluster_config)

    try:
        logger.debug("Actual create_cluster command")
        return pc.create_cluster(
            cluster_name=cluster_name,
            cluster_configuration=output_file_name,
            rollback_on_failure=False,
        )
    except CreateClusterBadRequestException as e:
        logger.critical(f"Exception: {e.content}")
        raise
    except InternalServiceException as e:
        logger.critical(f"Exception: {e.content}")
        raise
    finally:
        logger.debug("Cleaning up temporary config file")
        pathlib.Path(output_file_name).unlink()
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
    remove_key(get_keypair_name(vlab_id, project_id))
    remove_key(get_keypair_name(vlab_id, project_id, "sim"))
    return pc.delete_cluster(cluster_name=cluster_name, region=REGION)
