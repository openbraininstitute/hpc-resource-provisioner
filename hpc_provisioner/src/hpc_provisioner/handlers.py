import copy
import json
import logging
import logging.config
from importlib.metadata import version

import boto3
from pcluster.api.errors import NotFoundException

from hpc_provisioner.aws_queries import (
    create_keypair,
    store_private_key,
)
from hpc_provisioner.cluster import Cluster
from hpc_provisioner.constants import (
    BILLING_TAG_KEY,
    BILLING_TAG_VALUE,
    DEFAULTS,
    FILESYSTEMS,
    PROJECT_TAG_KEY,
    VLAB_TAG_KEY,
)
from hpc_provisioner.dynamodb_actions import (
    ClusterAlreadyRegistered,
    delete_cluster,
    dynamodb_resource,
    get_unclaimed_clusters,
    register_cluster,
)
from hpc_provisioner.utils import (
    generate_public_key,
)

from .logging_config import LOGGING_CONFIG
from .pcluster_manager import (
    InvalidRequest,
    all_dras_for_cluster_done,
    any_fs_creating,
    do_cluster_create,
    fsx_precreate,
    pcluster_create,
    pcluster_delete,
    pcluster_describe,
    pcluster_list,
)

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


def pcluster_handler(event, _context=None):
    """
    * Check whether we have a GET, a POST or a DELETE method
    * Pass on to pcluster_*_handler
    """
    logger.debug(f"pcluster handler: event: {event}")
    if event.get("httpMethod"):
        if event["httpMethod"] == "GET":
            if event["path"] == "/hpc-provisioner/pcluster":
                logger.debug("GET pcluster")
                response = pcluster_describe_handler(event, _context)
            elif event["path"] == "/hpc-provisioner/version":
                logger.debug("GET version")
                response = response_text(text=version("hpc_provisioner"))
            else:
                response = response_text(f"Unclear what to do with GET {event['path']}", code=400)
        elif event["httpMethod"] == "POST":
            logger.debug(
                f"POST with path {event['path']} startswith /hpc-provisioner/dra: {event['path'].startswith('/hpc-provisioner/dra')}"
            )
            if event["path"] == "/hpc-provisioner/pcluster":
                logger.debug("POST pcluster")
                response = pcluster_create_request_handler(event, _context)
            elif event["path"].startswith("/hpc-provisioner/dra"):
                logger.debug("POST DRA")
                response = dra_check_handler(event, _context)
            else:
                response = response_text(f"Unclear what to do with POST {event['path']}", code=400)
        elif event["httpMethod"] == "DELETE":
            logger.debug("DELETE pcluster")
            response = pcluster_delete_handler(event, _context)
        else:
            response = response_text(f"{event['httpMethod']} not supported", code=400)
    else:
        response = response_text(f"Unclear what to do with event {event}", code=400)
    logger.debug(f"Response: {response}")
    return response


def dra_check_handler(event, _context=None):
    """
    1. Check which clusters are pending (claimed=False) creation and have include_lustre=True
    2. For each of them:
        check whether any DRAs are still pending
        if not: call do_cluster_create
    """
    logger.debug(f"event: {event}, _context: {_context}")
    dynamo = dynamodb_resource()
    for cluster in get_unclaimed_clusters(dynamodb_resource=dynamo):
        logger.debug(f"Unclaimed cluster: {cluster}")
        if all_dras_for_cluster_done(cluster):
            logger.debug(f"All filesystems for {cluster.name} ready - creating cluster")
            return response_json(do_cluster_create(cluster))
        elif any_fs_creating():
            msg = f"A filesystem is being created - skipping cluster {cluster.name} for now"
            logger.debug(msg)
            return response_text(msg)
        else:
            logger.debug(f"No filesystems being created - precreating for {cluster.name}")
            creating_fsx = fsx_precreate(cluster=cluster, filesystems=FILESYSTEMS)
            if creating_fsx:
                msg = f"Precreating fsx for cluster {cluster.name}"
            else:
                msg = "No filesystems to create"
            return response_text(msg)


def pcluster_do_create_handler(event, _context=None):
    """
    The handler for the async lambda which will do the actual create
    """
    logger.debug(f"event: {event}, _context: {_context}")
    cluster = Cluster.from_dict(event["cluster"])
    if not cluster.include_lustre:
        for fs in FILESYSTEMS:
            fs["expected"] = False
    pcluster_create(cluster, FILESYSTEMS)


def pcluster_create_request_handler(event, _context=None):
    """
    Handles the initial cluster create request.
      * register the cluster in dynamo
      * precreate ssh keys
    """

    cluster = _get_vlab_query_params(event)
    dynamo = dynamodb_resource()
    try:
        register_cluster(dynamo, cluster)
    except ClusterAlreadyRegistered as e:
        return response_text(text=e.__str__(), code=500)
    else:
        logger.debug(f"Cluster {cluster.name} registered successfully; proceeding")

    ec2_client = boto3.client("ec2")
    sm_client = boto3.client("secretsmanager")

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
    response["cluster"]["private_ssh_key_arn"] = sim_user_secret["ARN"]
    response["cluster"]["admin_user_private_ssh_key_arn"] = admin_user_secret["ARN"]

    if key_material := sm_client.get_secret_value(SecretId=sim_user_secret["ARN"]):
        cluster.sim_pubkey = generate_public_key(key_material["SecretString"])
    else:
        raise RuntimeError(
            f"Something went wrong retrieving the sim user private key: {sim_user_secret['ARN']}"
        )
    logger.debug(f"Cluster: {cluster}")

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
        dynamo = dynamodb_resource()
        delete_cluster(dynamo, cluster)
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


def response_text(text: str, code: int = 200):
    return {"statusCode": code, "body": text}


def response_json(data: dict, code: int = 200):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data),
    }
