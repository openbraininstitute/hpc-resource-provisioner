import copy
import json
import logging
import logging.config
from importlib.metadata import version

import boto3
from pcluster.api.errors import NotFoundException

from hpc_provisioner.aws_queries import (
    create_keypair,
    get_fsx,
    list_existing_stacks,
    store_private_key,
)
from hpc_provisioner.cluster import Cluster, ClusterJSONEncoder
from hpc_provisioner.constants import (
    BILLING_TAG_KEY,
    BILLING_TAG_VALUE,
    DEFAULTS,
    PROJECT_TAG_KEY,
    VLAB_TAG_KEY,
)
from hpc_provisioner.utils import generate_public_key

from .logging_config import LOGGING_CONFIG
from .pcluster_manager import (
    InvalidRequest,
    pcluster_create,
    pcluster_delete,
    pcluster_describe,
    pcluster_list,
)

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


def pcluster_do_create_handler(event, _context=None):
    logger.debug(f"event: {event}, _context: {_context}")
    cluster = Cluster.from_dict(event["cluster"])

    logger.debug(f"handler: create pcluster {cluster}")
    pcluster_create(cluster)
    logger.debug(f"created pcluster {cluster}")


def pcluster_handler(event, _context=None):
    """
    * Check whether we have a GET, a POST or a DELETE method
    * Pass on to pcluster_*_handler
    """
    if event.get("httpMethod"):
        if event["httpMethod"] == "GET":
            if event["path"] == "/hpc-provisioner/pcluster":
                logger.debug("GET pcluster")
                response = pcluster_describe_handler(event, _context)
            elif event["path"] == "/hpc-provisioner/version":
                logger.debug("GET version")
                response = response_json({"version": version("hpc_provisioner")})
            else:
                response = response_json(
                    {"message": f"Path {event['path']} not implemented"}, code=400
                )
        elif event["httpMethod"] == "POST":
            logger.debug("POST pcluster")
            response = pcluster_create_request_handler(event, _context)
        elif event["httpMethod"] == "DELETE":
            logger.debug("DELETE pcluster")
            response = pcluster_delete_handler(event, _context)
        else:
            response = response_json({"message": f"{event['httpMethod']} not supported"}, code=400)
    else:
        response = response_json(
            {"message": "Could not determine HTTP method - make sure to GET, POST or DELETE"},
            code=400,
        )

    return response


def pcluster_create_request_handler(event, _context=None):
    """Request the creation of an HPC cluster for a given vlab_id and project_id"""

    cluster = _get_vlab_query_params(event)

    ec2_client = boto3.client("ec2")
    sm_client = boto3.client("secretsmanager")
    cf_client = boto3.client("cloudformation")

    admin_ssh_keypair = create_keypair(
        ec2_client,
        cluster=cluster,
        tags=[
            {"Key": VLAB_TAG_KEY, "Value": cluster.vlab_id},
            {"Key": PROJECT_TAG_KEY, "Value": cluster.project_id},
            {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
        ],
    )

    admin_user_secret = store_private_key(sm_client, cluster, admin_ssh_keypair)

    response = {
        "cluster": {
            "clusterName": cluster.name,
            "clusterStatus": "CREATE_REQUEST_RECEIVED",
        }
    }

    create_args = {
        "cluster": cluster,
    }

    sim_user_ssh_keypair = create_keypair(
        ec2_client,
        cluster,
        tags=[
            {"Key": VLAB_TAG_KEY, "Value": cluster.vlab_id},
            {"Key": PROJECT_TAG_KEY, "Value": cluster.project_id},
            {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
        ],
        keypair_user="sim",
    )

    sim_user_secret = store_private_key(sm_client, cluster, sim_user_ssh_keypair)
    logger.debug(f"Created sim user keypair: {sim_user_ssh_keypair}")

    response["cluster"]["ssh_user"] = "sim"
    response["cluster"]["user_private_ssh_key_arn"] = sim_user_secret["ARN"]
    response["cluster"]["admin_private_ssh_key_arn"] = admin_user_secret["ARN"]

    if key_material := sm_client.get_secret_value(SecretId=sim_user_secret["ARN"]):
        cluster.sim_pubkey = generate_public_key(key_material["SecretString"])
    else:
        raise RuntimeError(
            f"Something went wrong retrieving the sim user private key: {sim_user_secret['ARN']}"
        )
    logger.debug(f"Cluster: {cluster}")

    if cluster.name in list_existing_stacks(cf_client):
        print(f"Stack {cluster.name} already exists - exiting")
        return response_json(response)

    logger.debug(f"calling create lambda async with arguments {create_args}")
    boto3.client("lambda").invoke_async(
        FunctionName="hpc-resource-provisioner-creator",
        InvokeArgs=json.dumps(create_args, cls=ClusterJSONEncoder),
    )
    logger.debug("called create lambda async")

    return response_json(response)


def pcluster_describe_handler(event, _context=None):
    """Describe a cluster given the vlab_id and project_id"""
    try:
        cluster = _get_vlab_query_params(event)
    except InvalidRequest:
        logger.debug("No vlab_id specified - listing pclusters")
        pc_output = pcluster_list()
    else:
        logger.debug(f"describe pcluster {cluster}")
        try:
            pc_output = pcluster_describe(cluster)
            pc_output["vlab_id"] = cluster.vlab_id
            pc_output["project_id"] = cluster.project_id
            fsx_client = boto3.client("fsx")
            if cluster_fsx := get_fsx(
                fsx_client=fsx_client,
                fs_name=cluster.name,
            ):
                pc_output["clusterFsxId"] = cluster_fsx["FileSystemId"]
            else:
                pc_output["clusterFsxId"] = None
            logger.debug(f"described pcluster {cluster}")
        except NotFoundException as e:
            return {"statusCode": 404, "body": e.content.message}
        except Exception as e:
            return {"statusCode": 500, "body": str(type(e))}

    return response_json(pc_output)


def pcluster_delete_handler(event, _context=None):
    """Delete a cluster given the vlab_id and project_id"""
    cluster = _get_vlab_query_params(event)

    logger.debug(f"delete pcluster {cluster}")
    try:
        pc_output = pcluster_delete(cluster)
        logger.debug(f"deleted pcluster {cluster.vlab_id}-{cluster.project_id}")
    except NotFoundException as e:
        return {"statusCode": 404, "body": e.content.message}
    except Exception as e:
        return {"statusCode": 500, "body": str(type(e))}

    return response_json(pc_output)


def _get_vlab_query_params(incoming_event) -> Cluster:
    logger.debug(f"Getting query params from event {incoming_event}")
    event = copy.deepcopy(incoming_event)

    params = {
        "benchmark": event.get("benchmark", DEFAULTS["benchmark"]),
        "dev": event.get("dev", DEFAULTS["dev"]),
        "include_lustre": event.get("include_lustre", DEFAULTS["include_lustre"]),
        "tier": event.get("tier", DEFAULTS["tier"]),
        "project_id": event.get("project_id"),
        "vlab_id": event.get("vlab_id"),
        "admin_ssh_key_name": event.get("admin_ssh_key_name"),
        "sim_pubkey": event.get("sim_pubkey"),
    }

    logger.debug(f"params: {params}")
    if event.get("queryStringParameters"):
        print("queryStringParameters specified - getting values from it")
        for param, value in params.items():
            if value == DEFAULTS.get(param) or value is None:
                logger.debug(
                    f"Param {param} is set to {value} (default or None)- making sure it's not in queryStringParameters"
                )
                if param in event.get("queryStringParameters", {}):
                    params[param] = event["queryStringParameters"][param]
    cluster = Cluster(
        project_id=params["project_id"],
        vlab_id=params["vlab_id"],
        tier=params["tier"],
        benchmark=params.get("benchmark", "").lower() == "true",
        dev=params.get("dev", "").lower() == "true",
        include_lustre=params.get("include_lustre", "").lower() == "true",
    )

    logger.debug(f"Params: {params}")
    logger.debug(f"Cluster: {cluster}")

    if params["vlab_id"] is None:
        raise InvalidRequest("missing required 'vlab_id' query param")
    if params["project_id"] is None:
        raise InvalidRequest("missing required 'project_id' query param")

    if params["admin_ssh_key_name"]:
        cluster.admin_ssh_key_name = params["admin_ssh_key_name"]
    if params["sim_pubkey"]:
        cluster.sim_pubkey = params["sim_pubkey"]

    logger.debug(f"Parameters: {params}")
    logger.debug(f"Cluster: {cluster}")
    return cluster


def response_json(data: dict, code: int = 200):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data),
    }
