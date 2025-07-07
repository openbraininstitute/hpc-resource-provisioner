import logging
import logging.config

import boto3

from hpc_provisioner.logging_config import LOGGING_CONFIG

TABLE_NAME = "sbo-parallelcluster-subnets"

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


class SubnetAlreadyRegisteredException(Exception):
    "Raised when trying to register a subnet that already has a DB entry"


def dynamodb_client():
    """
    Return the DynamoDB boto3 client
    """
    return boto3.client("dynamodb")


def get_registered_subnets(dynamodb_client) -> dict:
    """
    Get all registered subnets and the clusters they are registered to
    """

    result = dynamodb_client.scan(TableName=TABLE_NAME)
    logger.debug(f"Registered subnets: {result}")

    return {item["subnet_id"]["S"]: item["cluster"]["S"] for item in result["Items"]}


def get_subnet(dynamodb_client, subnet_id: str) -> dict:
    logger.debug(f"Getting subnet {subnet_id}")
    items = dynamodb_client.get_item(
        TableName=TABLE_NAME,
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
        TableName=TABLE_NAME,
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
