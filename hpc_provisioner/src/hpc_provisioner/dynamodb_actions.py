import logging
import logging.config
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

from hpc_provisioner.cluster import Cluster
from hpc_provisioner.logging_config import LOGGING_CONFIG

SUBNET_TABLE_NAME = "sbo-parallelcluster-subnets"
CLUSTER_TABLE_NAME = "pclusters"

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


class SubnetAlreadyRegisteredException(Exception):
    "Raised when trying to register a subnet that already has a DB entry"


class ClusterNotRegistered(Exception):
    "Raised when trying to manipulate a cluster that's not registered"


class ClusterAlreadyRegistered(Exception):
    "Raised when trying register a cluster that's already registered"


class ClusterAlreadyInClaimState(Exception):
    "Raised when trying to claim / release a cluster that is already claimed / released"


def dynamodb_client():
    """
    Return the DynamoDB boto3 client
    """
    return boto3.client("dynamodb")


def dynamodb_resource():
    """
    Return the DynamoDB boto3 resource
    """
    return boto3.resource("dynamodb")


def get_registered_subnets(dynamodb_client) -> dict:
    """
    Get all registered subnets and the clusters they are registered to
    """

    result = dynamodb_client.scan(TableName=SUBNET_TABLE_NAME)
    logger.debug(f"Registered subnets: {result}")

    return {item["subnet_id"]["S"]: item["cluster"]["S"] for item in result["Items"]}


def get_subnet(dynamodb_client, subnet_id: str) -> dict:
    logger.debug(f"Getting subnet {subnet_id}")
    items = dynamodb_client.get_item(
        TableName=SUBNET_TABLE_NAME,
        Key={"subnet_id": {"S": subnet_id}},
        ConsistentRead=True,
    )

    logger.debug(f"Result: {items}")
    item = items.get("Item", {})

    return {item["subnet_id"]["S"]: item["cluster"]["S"]} if item else {}


def register_subnet(dynamodb_client, subnet_id: str, cluster: str) -> None:
    """
    Register a new subnet/parallel-cluster combination.
    Will raise SubnetAlreadyRegisteredException if there is already an entry for the subnet
    """

    logger.debug(f"Registering subnet {subnet_id} for cluster {cluster}")
    if get_subnet(dynamodb_client, subnet_id):
        logger.debug("Someone was faster")
        raise SubnetAlreadyRegisteredException()

    dynamodb_client.update_item(
        TableName=SUBNET_TABLE_NAME,
        Key={"subnet_id": {"S": subnet_id}},
        AttributeUpdates={"cluster": {"Value": {"S": cluster}}},
    )


def free_subnet(dynamodb_client, subnet_id: str) -> None:
    """
    Delete an entry, marking the subnet as available
    """
    dynamodb_client.delete_item(
        TableName="sbo-parallelcluster-subnets", Key={"subnet_id": {"S": subnet_id}}
    )


def get_unclaimed_clusters(dynamodb_resource) -> list:
    table = dynamodb_resource.Table(CLUSTER_TABLE_NAME)
    result = table.query(IndexName="ClaimIndex", KeyConditionExpression=Key("claimed").eq(0))
    logger.debug(f"Clusters in dynamo: {result}")
    retval = []
    for item in result.get("Items", []):
        retval.append(Cluster.from_dynamo_dict(item))
    return retval


def get_cluster_by_name(dynamodb_resource, cluster_name: str) -> Optional[dict]:
    table = dynamodb_resource.Table(CLUSTER_TABLE_NAME)
    result = table.get_item(Key={"name": cluster_name}, ConsistentRead=True)
    return result.get("Item")


def register_cluster(dynamodb_resource, cluster: Cluster) -> None:
    if registered_cluster := get_cluster_by_name(dynamodb_resource, cluster.name):
        if cluster != Cluster.from_dynamo_dict(registered_cluster):
            raise ClusterAlreadyRegistered(
                f"Cluster {cluster} already registered with different parameters"
            )
        else:
            return

    table = dynamodb_resource.Table(CLUSTER_TABLE_NAME)
    table.put_item(Item=cluster.as_dynamo_dict())


def delete_cluster(dynamodb_resource, cluster: Cluster) -> None:
    table = dynamodb_resource.Table(CLUSTER_TABLE_NAME)
    table.delete_item(Key={"name": cluster.name})


def _update_cluster_claim(dynamodb_resource, cluster: Cluster, new_value: int) -> None:
    stored_cluster = get_cluster_by_name(dynamodb_resource, cluster.name)
    if not stored_cluster:
        raise ClusterNotRegistered(f"Cluster {cluster} is not registered - cannot claim it")

    if stored_cluster.get("claimed") == new_value:
        raise ClusterAlreadyInClaimState(f"Cluster {cluster} already has claim state {new_value}")

    table = dynamodb_resource.Table(CLUSTER_TABLE_NAME)
    table.update_item(
        Key={"name": cluster.name},
        UpdateExpression="SET provisioning_launched = :claim",
        ExpressionAttributeValues={":claim": new_value},
    )


def claim_cluster(dynamodb_resource, cluster: Cluster) -> None:
    _update_cluster_claim(dynamodb_resource, cluster, 1)


def release_cluster(dynamodb_resource, cluster: Cluster) -> None:
    _update_cluster_claim(dynamodb_resource, cluster, 0)
