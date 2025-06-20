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
    create_dra,
    create_fsx,
    delete_fsx,
    get_available_subnet,
    get_dra,
    get_efs,
    get_fsx,
    get_keypair_name,
    get_security_group,
    list_all_dras_for_fsx,
    list_all_fsx,
    list_existing_stacks,
    release_subnets,
    remove_key,
)
from hpc_provisioner.cluster import Cluster, ClusterJSONEncoder
from hpc_provisioner.constants import (
    BILLING_TAG_KEY,
    BILLING_TAG_VALUE,
    CONFIG_VALUES,
    DRAS,
    PCLUSTER_CONFIG_TPL,
    PCLUSTER_DEV_CONFIG_TPL,
    PROJECT_TAG_KEY,
    REGION,
    VLAB_TAG_KEY,
)
from hpc_provisioner.dynamodb_actions import claim_cluster, dynamodb_resource
from hpc_provisioner.logging_config import LOGGING_CONFIG
from hpc_provisioner.utils import (
    get_ami_id,
    get_containers_bucket,
    get_efa_security_group_id,
    get_fs_bucket,
    get_fsx_policy_arn,
    get_infra_bucket,
    get_sbonexusdata_bucket,
    get_scratch_bucket,
    get_suffix,
)
from hpc_provisioner.yaml_loader import load_yaml_extended

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


class PClusterError(Exception):
    """An error reported by PCluster"""


class InvalidRequest(Exception):
    """When the request is invalid, likely due to invalid or missing data"""


def populate_config(
    cluster: Cluster,
    create_users_args: Optional[List[str]] = None,
) -> None:
    """
    populate config values for loading cluster config yaml

    :param cluster_name: name of the cluster
    :param create_users_args: arguments to create_users.py
    """
    ec2_client = boto3.client("ec2")
    efs_client = boto3.client("efs")
    # base_security_group_id and efs_id should be fairly static and change only if
    # something changes about the deployment.
    # base_subnet_id is where the interesting stuff happens
    CONFIG_VALUES["base_subnet_id"] = get_available_subnet(ec2_client, cluster.name)
    CONFIG_VALUES["base_security_group_id"] = get_security_group(ec2_client)
    CONFIG_VALUES["efs_id"] = get_efs(efs_client)
    CONFIG_VALUES["ssh_key"] = cluster.admin_ssh_key_name
    CONFIG_VALUES["sbonexusdata_bucket"] = get_sbonexusdata_bucket()
    CONFIG_VALUES["containers_bucket"] = get_containers_bucket()
    CONFIG_VALUES["fsx_policy_arn"] = get_fsx_policy_arn()
    if cluster.benchmark:
        CONFIG_VALUES["scratch_bucket"] = get_scratch_bucket()
    else:
        CONFIG_VALUES["scratch_bucket"] = "/".join(
            [get_scratch_bucket(), cluster.vlab_id, cluster.project_id]
        )
    CONFIG_VALUES["efa_security_group_id"] = get_efa_security_group_id()
    if create_users_args:
        CONFIG_VALUES["create_users_args"] = create_users_args
    CONFIG_VALUES["environment_args"] = [cluster.name]
    CONFIG_VALUES["ami_id"] = get_ami_id()
    CONFIG_VALUES["infra_assets_bucket"] = get_infra_bucket().replace("s3://", "")
    CONFIG_VALUES["create_users_script"] = f"{get_infra_bucket()}/scripts/create_users.py"
    CONFIG_VALUES["environment_script"] = f"{get_infra_bucket()}/scripts/environment.sh"
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


def get_tier_config(pcluster_config: dict, chosen_tier: str) -> list:
    available_tiers = [q["Name"] for q in pcluster_config["Scheduling"]["SlurmQueues"]]
    if chosen_tier not in available_tiers:
        raise ValueError(
            f"Tier {chosen_tier} not available - choose from {', '.join(available_tiers)}"
        )
    else:
        queues = pcluster_config["Scheduling"]["SlurmQueues"]
        queues = [next(q for q in queues if q["Name"] == chosen_tier)]

    return queues


def write_config(cluster_name: str, pcluster_config: dict) -> str:
    output_file = f"deployment-{cluster_name}.yaml"
    output_file = tempfile.NamedTemporaryFile(delete=False)

    logger.debug(f"Writing pcluster config to {output_file.name}")
    with open(output_file.name, "w") as out:
        yaml.dump(pcluster_config, out, sort_keys=False)

    logger.debug(f"pcluster config is {pcluster_config}")

    return output_file.name


def fsx_precreate(cluster: Cluster, filesystems: list) -> bool:
    """
    Return True if creating a filesystem, False if nothing to do
    """
    fsx_client = boto3.client("fsx")
    logger.debug(f"Precreating filesystems for {cluster.name}")
    fs = get_fsx(fsx_client=fsx_client, fs_name=cluster.name)
    if not fs:
        logger.debug(f"Creating filesystem for {cluster.name}")
        fs = create_fsx(
            fsx_client=fsx_client,
            fs_name=cluster.name,
            cluster=cluster,
        )["FileSystem"]
        logger.debug("Creating DRA")
    for dra in filesystems:
        if get_dra(
            fsx_client=fsx_client, filesystem_id=fs["FileSystemId"], mountpoint=dra["mountpoint"]
        ):
            continue
        else:
            create_dra(
                fsx_client=fsx_client,
                filesystem_id=fs["FileSystemId"],
                mountpoint=dra["mountpoint"],
                bucket=get_fs_bucket(dra["name"], cluster),
                vlab_id=cluster.vlab_id,
                project_id=cluster.project_id,
                writable=dra["writable"],
            )
            return True

    return False


def pcluster_create(cluster: Cluster, filesystems: list):
    """Create a pcluster for a given vlab

    Args:
        vlab_id: The id of the vlab
        project_id: The id of the project within the vlab
        options: a dict of user provided options.
            All possible options can be seen in DEFAULTS.

    """
    logger.info(f"Creating pcluster: {cluster}")

    if cluster_already_exists(cluster.name):
        return

    cluster_users = json.dumps(
        [
            {
                "name": "sim",
                "public_key": cluster.sim_pubkey,
                "sudo": False,
                "folder_ownership": ["/sbo/data/scratch"],
            }
        ]
    )
    create_users_args = [
        f"--vlab-id={cluster.vlab_id}",
        f"--project-id={cluster.project_id}",
        f"--users={cluster_users}",
    ]

    populate_config(cluster=cluster, create_users_args=create_users_args)
    fsx_client = boto3.client("fsx")
    for filesystem in filesystems:
        if filesystem.get("expected", True):
            fs = get_fsx(
                fsx_client=fsx_client,
                fs_name=cluster.name,
            )
            if not fs:
                raise RuntimeError(f"Filesystem {filesystem} not created when it should have been")
            CONFIG_VALUES["fsx"] = {
                "Name": filesystem["name"],
                "StorageType": "FsxLustre",
                "MountDir": filesystem["mountpoint"],
                "FsxLustreSettings": {"FileSystemId": fs["FileSystemId"]},
            }
        else:
            CONFIG_VALUES["fsx"] = {}

    pcluster_config = load_pcluster_config(cluster.dev)
    if not cluster.include_lustre:
        pcluster_config["SharedStorage"] = pcluster_config["SharedStorage"][:1]  # keep only EFS
    pcluster_config["Tags"] = populate_tags(pcluster_config, cluster.vlab_id, cluster.project_id)
    pcluster_config["Scheduling"]["SlurmQueues"] = get_tier_config(pcluster_config, cluster.tier)
    if cluster.benchmark:
        pcluster_config["HeadNode"]["CustomActions"]["OnNodeConfigured"]["Sequence"].append(
            {
                "Script": f"{get_infra_bucket()}/scripts/80_cloudwatch_agent_config_prolog.sh",
                "Args": [cluster.name],
            }
        )

    output_file_name = write_config(cluster.name, pcluster_config)

    try:
        logger.debug("Actual create_cluster command")
        return pc.create_cluster(
            cluster_name=cluster.name,
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


def pcluster_describe(cluster: Cluster):
    """Describe a cluster, given the vlab_id and project_id"""
    logger.debug("About to describe")
    return pc.describe_cluster(cluster_name=cluster.name, region=REGION)


def pcluster_delete(cluster: Cluster):
    """Destroy a cluster, given the vlab_id and project_id"""
    release_subnets(cluster.name)
    fsx_client = boto3.client("fsx")
    fs = get_fsx(fsx_client=fsx_client, fs_name=cluster.name)
    if fs:
        delete_fsx(fsx_client, fs["FileSystemId"])
    remove_key(get_keypair_name(cluster))
    remove_key(get_keypair_name(cluster, "sim"))
    return pc.delete_cluster(cluster_name=cluster.name, region=REGION)


def all_dras_for_cluster_done(cluster: Cluster) -> bool:
    """
    Check whether all filesystems for the cluster are created and their DRAs all available
    """
    logger.debug(f"Checking all DRAs for cluster: {cluster}")
    if cluster.include_lustre:
        fsx_client = boto3.client("fsx")
        for dra_data in DRAS:
            logger.debug(f"Getting fs {dra_data['name']}")
            fsx = get_fsx(fsx_client, fs_name=cluster.name)
            if not fsx or fsx["Lifecycle"] != "AVAILABLE":
                logger.debug(f"Filesystem {dra_data['name']} not found or not ready yet")
                return False
            created_dra = get_dra(
                fsx_client=fsx_client,
                filesystem_id=fsx["FileSystemId"],
                mountpoint=dra_data["mountpoint"],
            )
            if not created_dra or created_dra["Lifecycle"] != "AVAILABLE":
                logger.debug(f"DRA for filesystem {dra_data['name']} not found or not ready yet")
                return False
    logger.debug(f"All filesystems for cluster{cluster.name} ready!")
    return True


def any_fs_creating() -> bool:
    fsx_client = boto3.client("fsx")
    for fsx in list_all_fsx(fsx_client=fsx_client):
        if fsx["Lifecycle"] not in ["AVAILABLE", "FAILED"]:
            return True
        for dra in list_all_dras_for_fsx(fsx_client=fsx_client, filesystem_id=fsx["FileSystemId"]):
            if dra["Lifecycle"] not in ["AVAILABLE", "FAILED"]:
                return True
    return False


def call_async_lambda(cluster: Cluster):
    cf_client = boto3.client("cloudformation")

    create_args = {
        "cluster": cluster,
    }

    if cluster.name in list_existing_stacks(cf_client):
        print(f"Stack {cluster.name} already exists - exiting")
        return pcluster_describe(cluster)

    logger.debug(f"calling create lambda async with arguments {create_args}")
    boto3.client("lambda").invoke_async(
        FunctionName=f"hpc-resource-provisioner-creator-{get_suffix()}",
        InvokeArgs=json.dumps(create_args, cls=ClusterJSONEncoder),
    )
    logger.debug("called create lambda async")
    return {
        "cluster": {
            "clusterName": cluster.name,
            "clusterStatus": "CREATE_REQUEST_RECEIVED",
        }
    }


def do_cluster_create(cluster):
    """Actually create the cluster - it assumes that all the necessary filesystems have been created"""
    # if cluster.include_lustre:
    #     logger.debug(f"precreate filesystems for cluster {cluster.name}")
    #     if fsx_precreate(cluster, DRAS):
    #         logger.debug("Created FSx - not proceeding to cluster creation yet")
    #         create_eventbridge_dra_checking_rule(eb_client=boto3.client("events"))
    #         return
    #     else:
    #         logger.debug("All FSx filesystems created - proceeding to cluster create")
    # else:
    #     # the filesystems don't really need to exist - later code will check for this
    #     for fs in DRAS:
    #         fs["expected"] = False

    logger.debug(f"create pcluster {cluster.name}")
    claim_cluster(dynamodb_resource(), cluster)
    return call_async_lambda(cluster)
    # pcluster_create(cluster, DRA)
    # logger.debug(f"created pcluster {cluster.name}")
