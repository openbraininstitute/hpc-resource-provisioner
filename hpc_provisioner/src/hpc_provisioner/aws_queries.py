import logging
import logging.config
import time
from typing import Dict, Optional

import boto3
from botocore.exceptions import ClientError

from hpc_provisioner.cluster import Cluster
from hpc_provisioner.constants import (
    BILLING_TAG_KEY,
    BILLING_TAG_VALUE,
    DRA_CHECKING_RULE_NAME,
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
from hpc_provisioner.utils import (
    get_api_gw_arn,
    get_eventbridge_role_arn,
    get_fs_sg_id,
    get_fs_subnet_ids,
)

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


def get_keypair_name(cluster, keypair_user=None) -> str:
    keypair_name = cluster.name
    if keypair_user:
        keypair_name = "_".join([keypair_name, keypair_user])

    return keypair_name


def create_keypair(ec2_client, cluster, tags, keypair_user=None) -> dict:
    keypair_name = get_keypair_name(cluster, keypair_user)
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


def store_private_key(sm_client, cluster, ssh_keypair):
    if "KeyMaterial" in ssh_keypair:
        secret = create_secret(
            sm_client,
            cluster.vlab_id,
            cluster.project_id,
            ssh_keypair["KeyName"],
            ssh_keypair["KeyMaterial"],
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
    logger.debug(f"Releasing subnets for {cluster_name}")
    client = dynamodb_client()
    registered_subnets = get_registered_subnets(client)
    logger.debug(f"Registered subnets: {registered_subnets}")
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


def list_existing_stacks(cf_client):
    statuses = [
        "CREATE_IN_PROGRESS",
        "CREATE_FAILED",
        "CREATE_COMPLETE",
        "ROLLBACK_IN_PROGRESS",
        "ROLLBACK_FAILED",
        "ROLLBACK_COMPLETE",
        "DELETE_IN_PROGRESS",
        "DELETE_FAILED",
        "UPDATE_IN_PROGRESS",
        "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
        "UPDATE_COMPLETE",
        "UPDATE_FAILED",
        "UPDATE_ROLLBACK_IN_PROGRESS",
        "UPDATE_ROLLBACK_FAILED",
        "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
        "UPDATE_ROLLBACK_COMPLETE",
        "REVIEW_IN_PROGRESS",
        "IMPORT_IN_PROGRESS",
        "IMPORT_COMPLETE",
        "IMPORT_ROLLBACK_IN_PROGRESS",
        "IMPORT_ROLLBACK_FAILED",
        "IMPORT_ROLLBACK_COMPLETE",
    ]
    stacks = cf_client.list_stacks(StackStatusFilter=statuses)
    existing_stack_names = [
        stack["StackName"] for stack in stacks["StackSummaries"] if "ParentId" not in stack
    ]

    return existing_stack_names


def get_fsx_name(shared: bool, fs_name: str, cluster: Optional[Cluster]) -> str:
    if shared:
        return fs_name
    else:
        return f"{fs_name}-{cluster.name}"


def create_fsx(
    fsx_client,
    fs_name: str,
    shared: bool = True,
    cluster: Optional[Cluster] = None,
) -> Dict:
    """
    Create an FSX filesystem if it doesn't exist yet

    :param fs_name: name to identify the filesystem (e.g. "scratch", "projects", ...)
    :param shared: whether the filesystem is shared among all pclusters or specific to one cluster
    :param vlab_id: vlab of the cluster to which the filesystem will be attached.
    :param project_id: project of the cluster to which the filesystem will be attached.
    """

    logger.debug(
        f"Creating fsx with name {fs_name}, shared {shared}, and cluster {cluster}",
    )
    tags = [
        {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
    ]
    token = get_fsx_name(shared, fs_name, cluster)
    logger.debug(f"Token: {token}")
    tags.append({"Key": "Name", "Value": token})

    if not shared:
        tags.append({"Key": VLAB_TAG_KEY, "Value": cluster.vlab_id})
        tags.append({"Key": PROJECT_TAG_KEY, "Value": cluster.project_id})

    logger.debug(f"Tags: {tags}")

    fs = fsx_client.create_file_system(
        ClientRequestToken=token,
        FileSystemType="LUSTRE",
        StorageCapacity=19200,
        StorageType="SSD",
        SubnetIds=get_fs_subnet_ids(),
        SecurityGroupIds=[get_fs_sg_id()],
        Tags=tags,
        LustreConfiguration={
            "WeeklyMaintenanceStartTime": "6:05:00",  # start at 5AM on Saturdays
            # "ExportPath": "string",
            "DeploymentType": "PERSISTENT_2",
            "PerUnitStorageThroughput": 250,
            "DataCompressionType": "LZ4",
            "EfaEnabled": True,
            # "LogConfiguration": {  # TODO do we want this?
            #     "Level": "DISABLED" | "WARN_ONLY" | "ERROR_ONLY" | "WARN_ERROR",
            #     "Destination": "string",
            # },
            "MetadataConfiguration": {"Mode": "AUTOMATIC"},
        },
    )

    logger.debug(f"Created fsx {fs}")
    return fs


def get_fsx_by_id(fsx_client, filesystem_id: str) -> Optional[dict]:
    go_on = True
    next_token = None
    while go_on:
        if next_token:
            file_systems = fsx_client.describe_file_systems(NextToken=next_token)
        else:
            file_systems = fsx_client.describe_file_systems()
        try:
            return next(
                fs for fs in file_systems["FileSystems"] if fs["FileSystemId"] == filesystem_id
            )
        except StopIteration:
            next_token = file_systems.get("NextToken")
            go_on = next_token is not None


def list_all_fsx(fsx_client) -> list:
    all_fsx = []
    go_on = True
    next_token = None
    while go_on:
        if next_token:
            file_systems = fsx_client.describe_file_systems(NextToken=next_token)
        else:
            file_systems = fsx_client.describe_file_systems()
        next_token = file_systems.get("NextToken")
        go_on = next_token is not None
        all_fsx.extend(file_systems["FileSystems"])
    return all_fsx


def list_all_dras_for_fsx(fsx_client, filesystem_id) -> list:
    return fsx_client.describe_data_repository_associations(
        Filters=[{"Name": "file-system-id", "Values": [filesystem_id]}]
    ).get("Associations", [])


def get_fsx(fsx_client, shared: bool, fs_name: str, cluster: Cluster) -> Optional[dict]:
    full_fs_name = get_fsx_name(shared, fs_name, cluster)
    for fsx in list_all_fsx(fsx_client):
        if any([t["Value"] == full_fs_name for t in fsx["Tags"] if t["Key"] == "Name"]):
            return fsx
    return None


def create_dra(
    fsx_client,
    filesystem_id: str,
    mountpoint: str,
    bucket: str,
    vlab_id: str,
    project_id: str,
    writable: bool = False,
) -> dict:
    logger.debug(
        f"Creating DRA for fs {filesystem_id}, mount {bucket} at {mountpoint}, for {vlab_id}-{project_id}, writable {writable}"
    )
    s3_config = {
        "AutoImportPolicy": {  # from S3 to FS
            "Events": [
                "NEW",
                "CHANGED",
                "DELETED",
            ]
        },
    }

    if writable:
        s3_config["AutoExportPolicy"] = {"Events": ["NEW", "CHANGED", "DELETED"]}

    logger.debug(f"s3 config: {s3_config}")

    dra = fsx_client.create_data_repository_association(
        FileSystemId=filesystem_id,
        FileSystemPath=mountpoint,
        DataRepositoryPath=bucket,
        BatchImportMetaDataOnCreate=True,
        ImportedFileChunkSize=1024,
        S3=s3_config,
        ClientRequestToken=f"{filesystem_id}-{vlab_id}-{project_id}",
        Tags=[
            {"Key": "Name", "Value": f"{filesystem_id}-{mountpoint}"},
            {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
            {"Key": VLAB_TAG_KEY, "Value": vlab_id},
            {"Key": PROJECT_TAG_KEY, "Value": project_id},
        ],
    )

    logger.debug(f"Created DRA {dra}")
    return dra


def get_dra_by_id(fsx_client, dra_id: str) -> Optional[dict]:
    dras = fsx_client.describe_data_repository_associations(AssociationIds=[dra_id])
    if len(dras.get("Associations", [])) == 0:
        return None
    return dras.get("Associations")[0]


def get_dra(fsx_client, filesystem_id: str, mountpoint: str) -> Optional[dict]:
    dras = list_all_dras_for_fsx(fsx_client=fsx_client, filesystem_id=filesystem_id)

    try:
        dra = next(dra for dra in dras if dra["FileSystemPath"] == mountpoint)
        return dra
    except StopIteration:
        return None


def eventbridge_dra_checking_rule_exists(eb_client):
    response = eb_client.list_rules(NamePrefix="resource_provisioner", Limit=100)
    return any(rule["Name"] == DRA_CHECKING_RULE_NAME for rule in response.get("Rules", []))


def create_eventbridge_dra_checking_rule(eb_client):
    if eventbridge_dra_checking_rule_exists(eb_client):
        return

    eb_client.put_rule(
        Name=DRA_CHECKING_RULE_NAME,
        ScheduleExpression="rate(5 minutes)",
        State="ENABLED",
        Description="Periodically check for DRAs and fire resource creator",
        RoleArn=get_eventbridge_role_arn(),
        Tags=[
            {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
        ],
    )

    create_eventbridge_target(eb_client)


def create_eventbridge_target(eb_client):
    eb_client.put_targets(
        Rule=DRA_CHECKING_RULE_NAME,
        Targets=[
            {
                "Id": "hpc-resource-provisioner",
                "Arn": f"{get_api_gw_arn()}production/POST/hpc-provisioner/dra",
                "RoleArn": get_eventbridge_role_arn(),
            },
        ],
    )
