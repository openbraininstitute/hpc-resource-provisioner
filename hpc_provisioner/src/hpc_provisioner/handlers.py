import json
import logging
import logging.config
from importlib.metadata import version

import boto3
from pcluster.api.errors import NotFoundException

from hpc_provisioner.aws_queries import create_keypair, list_existing_stacks, store_private_key
from hpc_provisioner.constants import (
    BILLING_TAG_KEY,
    BILLING_TAG_VALUE,
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
    options = _get_vlab_query_params(event)
    vlab_id = options["vlab_id"]
    project_id = options["project_id"]
    logger.debug(f"handler: create pcluster {vlab_id}-{project_id} with options: {options}")
    pcluster_create(vlab_id, project_id, options)
    logger.debug(f"created pcluster {vlab_id}-{project_id}")


def pcluster_handler(event, _context=None):
    """
    * Check whether we have a GET, a POST or a DELETE method
    * Pass on to pcluster_*_handler
    """
    if event.get("httpMethod"):
        if event["httpMethod"] == "GET":
            if event["path"] == "/hpc-provisioner/pcluster":
                logger.debug("GET pcluster")
                return pcluster_describe_handler(event, _context)
            elif event["path"] == "/hpc-provisioner/version":
                logger.debug("GET version")
                return response_text(text=version("hpc_provisioner"))
        elif event["httpMethod"] == "POST":
            logger.debug("POST pcluster")
            return pcluster_create_request_handler(event, _context)
        elif event["httpMethod"] == "DELETE":
            logger.debug("DELETE pcluster")
            return pcluster_delete_handler(event, _context)
        else:
            return response_text(f"{event['httpMethod']} not supported", code=400)

    return response_text(
        "Could not determine HTTP method - make sure to GET, POST or DELETE", code=400
    )


def pcluster_create_request_handler(event, _context=None):
    """Request the creation of an HPC cluster for a given vlab_id and project_id"""

    options = _get_vlab_query_params(event)
    vlab_id = options["vlab_id"]
    project_id = options["project_id"]
    ec2_client = boto3.client("ec2")
    sm_client = boto3.client("secretsmanager")
    cf_client = boto3.client("cloudformation")

    ssh_keypair = create_keypair(
        ec2_client,
        vlab_id=vlab_id,
        project_id=project_id,
        tags=[
            {"Key": VLAB_TAG_KEY, "Value": vlab_id},
            {"Key": PROJECT_TAG_KEY, "Value": project_id},
            {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
        ],
    )

    admin_user_secret = store_private_key(sm_client, vlab_id, project_id, ssh_keypair)

    response = {
        "cluster": {
            "clusterName": f"pcluster-{vlab_id}-{project_id}",
            "clusterStatus": "CREATE_REQUEST_RECEIVED",
            "private_ssh_key_arn": admin_user_secret["ARN"],
        }
    }

    create_args = {
        "vlab_id": vlab_id,
        "project_id": project_id,
        "keyname": ssh_keypair["KeyName"],
        "options": options,
    }

    sim_user_ssh_keypair = create_keypair(
        ec2_client,
        vlab_id=vlab_id,
        project_id=project_id,
        tags=[
            {"Key": VLAB_TAG_KEY, "Value": vlab_id},
            {"Key": PROJECT_TAG_KEY, "Value": project_id},
            {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
        ],
        keypair_user="sim",
    )

    sim_user_secret = store_private_key(sm_client, vlab_id, project_id, sim_user_ssh_keypair)
    response["cluster"]["ssh_user"] = "sim"
    response["admin_user_private_ssh_key_arn"] = admin_user_secret["ARN"]
    response["private_ssh_key_arn"] = sim_user_secret["ARN"]
    logger.debug(f"Created sim user keypair: {sim_user_ssh_keypair}")

    if key_material := sim_user_ssh_keypair.get("KeyMaterial"):
        create_args["sim_pubkey"] = generate_public_key(key_material)
    logger.debug(f"Create args: {create_args}")

    if f"pcluster-{vlab_id}-{project_id}" in list_existing_stacks(cf_client):
        print(f"Stack pcluster-{vlab_id}-{project_id} already exists - exiting")
        return response_json(response)

    logger.debug("calling create lambda async")
    boto3.client("lambda").invoke_async(
        FunctionName="hpc-resource-provisioner-creator",
        InvokeArgs=json.dumps(create_args),
    )
    logger.debug("called create lambda async")

    return response_json(response)


def pcluster_describe_handler(event, _context=None):
    """Describe a cluster given the vlab_id and project_id"""
    try:
        options = _get_vlab_query_params(event)
        vlab_id = options["vlab_id"]
        project_id = options["project_id"]
    except InvalidRequest:
        logger.debug("No vlab_id specified - listing pclusters")
        pc_output = pcluster_list()
    else:
        logger.debug(f"describe pcluster {vlab_id}-{project_id}")
        try:
            pc_output = pcluster_describe(vlab_id, project_id)
            logger.debug(f"described pcluster {vlab_id}-{project_id}")
        except NotFoundException as e:
            return {"statusCode": 404, "body": e.content.message}
        except Exception as e:
            return {"statusCode": 500, "body": str(type(e))}

    return response_json(pc_output)


def pcluster_delete_handler(event, _context=None):
    """Delete a cluster given the vlab_id and project_id"""
    options = _get_vlab_query_params(event)
    vlab_id = options["vlab_id"]
    project_id = options["project_id"]

    logger.debug(f"delete pcluster {vlab_id}-{project_id}")
    try:
        pc_output = pcluster_delete(vlab_id, project_id)
        logger.debug(f"deleted pcluster {vlab_id}-{project_id}")
    except NotFoundException as e:
        return {"statusCode": 404, "body": e.content.message}
    except Exception as e:
        return {"statusCode": 500, "body": str(type(e))}

    return response_json(pc_output)


def _get_vlab_query_params(event):
    logger.debug(f"Getting query params from event {event}")

    params = {
        "benchmark": event.get("benchmark"),
        "dev": event.get("dev"),
        "include_lustre": event.get("include_lustre"),
        "tier": event.get("tier"),
        "project_id": event.get("project_id"),
        "vlab_id": event.get("vlab_id"),
        "keyname": event.get("keyname"),
        "sim_pubkey": event.get("sim_pubkey"),
    }

    logger.debug(f"Params: {params}")

    if query_string_parameters := event.get("queryStringParameters", event.get("options", {})):
        logger.debug(
            "Trying to get unset values from query string parameters or options: "
            f"{query_string_parameters}"
        )
        for param, value in params.items():
            if value is None:
                logger.debug(
                    f"Parameter {param} not defined yet - "
                    "checking queryStringParameters {queryStringParameters}"
                )
                if param in ["benchmark", "dev"]:
                    params[param] = query_string_parameters.pop(param, False)
                else:
                    params[param] = query_string_parameters.pop(param, None)

    for bool_param in ["benchmark", "dev", "include_lustre"]:
        if isinstance(params[bool_param], str):
            params[bool_param] = params[bool_param].lower() == "true"
        elif not isinstance(params[bool_param], bool):
            params[bool_param] = False

    if params["vlab_id"] is None:
        raise InvalidRequest("missing required 'vlab_id' query param")
    if params["project_id"] is None:
        raise InvalidRequest("missing required 'project_id' query param")

    logger.debug(f"Parameters: {params}")
    return params


def response_text(text: str, code: int = 200):
    return {"statusCode": code, "body": text}


def response_json(data: dict, code: int = 200):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data),
    }
