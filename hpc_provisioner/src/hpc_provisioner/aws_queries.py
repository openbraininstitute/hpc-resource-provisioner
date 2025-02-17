import logging
import logging.config
import time
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from hpc_provisioner.constants import (
    BILLING_TAG_KEY,
    BILLING_TAG_VALUE,
    PROJECT_TAG_KEY,
    VLAB_TAG_KEY,
)
from hpc_provisioner.dynamodb_actions import (
    SubnetAlreadyRegisteredException,
    dynamodb_client,
    free_subnet,
    get_registered_subnets,
    get_subnet,
    register_subnet,
)
from hpc_provisioner.logging_config import LOGGING_CONFIG

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


class OutOfSubnetsException(Exception):
    """Indicates we're trying to deploy more clusters than we have subnets available."""


class CouldNotDetermineSecurityGroupException(Exception):
    """
    Indicates that we either found too many or no security groups with tags HPC_Goal:compute_cluster
    """


class CouldNotDetermineEFSException(Exception):
    """
    Indicates that we either found too many or no EFS filesystems with tags HPC_Goal:compute_cluster
    """


def get_cluster_name(vlab_id: str, project_id: str) -> str:
    return f"pcluster-{vlab_id}-{project_id}"


def create_keypair(ec2_client, vlab_id, project_id, tags) -> dict:
    keypair_name = get_cluster_name(vlab_id, project_id)
    try:
        existing_key = ec2_client.describe_key_pairs(KeyNames=[keypair_name])
        return existing_key["KeyPairs"][0]
    except ClientError:
        return ec2_client.create_key_pair(
            KeyName=keypair_name,
            TagSpecifications=[
                {
                    "ResourceType": "key-pair",
                    "Tags": tags,
                }
            ],
        )


def store_private_key(sm_client, vlab_id, project_id, ssh_keypair):
    if "KeyMaterial" in ssh_keypair:
        secret = create_secret(
            sm_client, vlab_id, project_id, ssh_keypair["KeyName"], ssh_keypair["KeyMaterial"]
        )
    else:
        secret = get_secret(sm_client, ssh_keypair["KeyName"])

    return secret


def create_secret(sm_client, vlab_id, project_id, secret_name, secret_value):
    secret = sm_client.create_secret(
        Name=secret_name,
        Description=f"SSH Key for cluster for vlab {vlab_id}, project {project_id}",
        SecretString=secret_value,
        Tags=[
            {"Key": VLAB_TAG_KEY, "Value": vlab_id},
            {"Key": PROJECT_TAG_KEY, "Value": project_id},
            {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
        ],
    )

    return secret


def get_secret(sm_client, secret_name):
    existing_secrets = sm_client.list_secrets(Filters=[{"Key": "name", "Values": [secret_name]}])
    if secret_list := existing_secrets.get("SecretList", []):
        secret = secret_list[0]
    else:
        raise RuntimeError(f"Secret {secret_name} does not exist in SecretsManager")

    return secret


def get_efs(efs_client) -> str:
    """
    Get the ID for the EFS for pclusters
    """
    file_systems = efs_client.describe_file_systems()["FileSystems"]
    logger.debug(f"file systems found: {file_systems}")
    candidates = [
        fs for fs in file_systems if {"Key": "HPC_Goal", "Value": "compute_cluster"} in fs["Tags"]
    ]
    if len(candidates) != 1:
        raise CouldNotDetermineEFSException(
            f"Could not choose EFS from {[efs.get('FileSystemId') for efs in candidates]}"
        )
    return candidates[0]["FileSystemId"]


def get_security_group(ec2_client) -> str:
    """
    Get the pcluster security group ID
    """

    security_groups = ec2_client.describe_security_groups(
        Filters=[{"Name": "tag:HPC_Goal", "Values": ["compute_cluster"]}]
    )
    if len(security_groups["SecurityGroups"]) != 1:
        raise CouldNotDetermineSecurityGroupException(
            f"Could not choose security group from {[sg.get('GroupId') for sg in security_groups['SecurityGroups']]}"
        )

    return security_groups["SecurityGroups"][0]["GroupId"]


def release_subnets(cluster_name: str) -> None:
    client = dynamodb_client()
    registered_subnets = get_registered_subnets(client)
    claimed_subnets = [
        subnet for subnet in registered_subnets if registered_subnets[subnet] == cluster_name
    ]
    logger.debug(f"Release subnets {claimed_subnets}")
    for subnet_id in claimed_subnets:
        logger.debug(f"Release subnet {subnet_id}")
        free_subnet(client, subnet_id)


def claim_subnet(dynamodb_client, ec2_subnets: list, cluster_name: str) -> Optional[str]:
    """
    Tries to claim a subnet for the given cluster_name
      * Check whether there are free subnets
      * Find an unclaimed subnet
      * Register it
      * Read the DynamoDB entry we just wrote to ensure nobody claimed it just before us
      * Continue with another subnet if needed
    """
    registered_subnets = get_registered_subnets(dynamodb_client)
    logger.debug(f"Registered subnets: {registered_subnets}")
    logger.debug(f"EC2 subnets: {ec2_subnets}")

    logger.info(f"Checking for existing claims for {cluster_name}")
    claimed_subnets = [
        subnet for subnet in registered_subnets if registered_subnets[subnet] == cluster_name
    ]
    if claimed_subnets:
        claim = claimed_subnets.pop()
        logger.debug(f"Already claimed subnet {claim}")
        for claimed_subnet in claimed_subnets:
            logger.debug(f"Releasing subnet {claimed_subnet}")
            free_subnet(dynamodb_client, claimed_subnet)

        return claim

    if len(registered_subnets) == len(ec2_subnets):
        raise OutOfSubnetsException(
            "All subnets are in use - either deploy more or remove some pclusters"
        )

    subnet_id = None
    for subnet in ec2_subnets:
        if subnet["SubnetId"] not in registered_subnets:
            logger.debug(f"Trying to register {subnet['SubnetId']}")

            try:
                register_subnet(dynamodb_client, subnet["SubnetId"], cluster_name)
            except SubnetAlreadyRegisteredException:
                logger.debug("Subnet was registered just before us - continuing")
                continue

            check_subnet = get_subnet(dynamodb_client, subnet["SubnetId"])

            claimed_cluster = check_subnet.get(subnet["SubnetId"])
            if check_subnet and claimed_cluster and claimed_cluster == cluster_name:
                logger.info(f"Subnet {subnet['SubnetId']} claimed for cluster {cluster_name}")
                subnet_id = subnet["SubnetId"]
                break
            else:
                logger.info(
                    f"Subnet {subnet['SubnetId']} already claimed for cluster {claimed_cluster}"
                )

    if not subnet_id:
        raise OutOfSubnetsException("Could not find a subnet")
    return subnet_id


def get_available_subnet(ec2_client, cluster_name: str) -> str:
    """
    Check all subnets marked for compute_cluster, and pick one which is available

    Return the subnet_id
    """

    ec2_subnets = ec2_client.describe_subnets(
        Filters=[
            {"Name": "tag:HPC_Goal", "Values": ["compute_cluster"]},
            {"Name": "available-ip-address-count", "Values": ["251"]},
        ]
    )["Subnets"]

    if not ec2_subnets:
        raise OutOfSubnetsException()

    client = dynamodb_client()
    subnet_id = None
    while not subnet_id:
        logger.debug("Trying to find a subnet until all subnets are claimed")
        try:
            subnet_id = claim_subnet(client, ec2_subnets, cluster_name)
        except OutOfSubnetsException:
            try:
                logger.info("Could not find a subnet - waiting a few seconds and trying again")
                time.sleep(10)
                subnet_id = claim_subnet(client, ec2_subnets, cluster_name)
            except OutOfSubnetsException:
                logger.critical(
                    "All subnets are in use - either deploy more or remove some pclusters"
                )
                raise

    return subnet_id


def remove_key(keypair_name: str) -> None:
    ec2_client = boto3.client("ec2")
    sm_client = boto3.client("secretsmanager")
    logger.debug(f"Deleting keypair {keypair_name} from EC2")
    client_delete = ec2_client.delete_key_pair(KeyName=keypair_name)
    logger.debug(f"Keypair deletion response: {client_delete}")

    logger.debug("Deleting secret from SecretsManager")
    secret_delete = sm_client.delete_secret(SecretId=keypair_name, ForceDeleteWithoutRecovery=True)
    logger.debug(f"Secret deletion response: {secret_delete}")
