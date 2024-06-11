import json
import logging
import logging.config

import boto3
from pcluster.api.errors import NotFoundException

from .logging_config import LOGGING_CONFIG
from .pcluster_manager import (
    InvalidRequest,
    pcluster_create,
    pcluster_delete,
    pcluster_describe,
)

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("hpc-resource-provisioner")


def pcluster_do_create_handler(event, _context=None):
    logger.debug(f"event: {event}, _context: {_context}")
    vlab_id, options = _get_vlab_query_params(event)
    logger.debug(f"create pcluster {vlab_id}")
    pcluster_create(vlab_id, options)
    logger.debug(f"created pcluster {vlab_id}")


def pcluster_handler(event, _context=None):
    """
    * Check whether we have a GET, a POST or a DELETE method
    * Pass on to pcluster_*_handler
    """
    if event.get("httpMethod"):
        if event["httpMethod"] == "GET":
            logger.debug("GET pcluster")
            return pcluster_describe_handler(event, _context)
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
    """Request the creation of an HPC cluster for a given vlab_id"""

    vlab_id, _ = _get_vlab_query_params(event)
    logger.debug("calling create lambda async")
    boto3.client("lambda").invoke_async(
        FunctionName="hpc-resource-provisioner-creator",
        InvokeArgs=json.dumps({"vlab_id": vlab_id}),
    )
    logger.debug("called create lambda async")

    return response_json(
        {
            "cluster": {
                "clusterName": f"hpc-pcluster-vlab-{vlab_id}",
                "clusterStatus": "CREATE_REQUEST_RECEIVED",
            }
        }
    )


def pcluster_describe_handler(event, _context=None):
    """Describe a cluster given the vlab_id"""
    vlab_id, _ = _get_vlab_query_params(event)

    logger.debug(f"describe pcluster {vlab_id}")
    try:
        pc_output = pcluster_describe(vlab_id)
        logger.debug(f"described pcluster {vlab_id}")
    except NotFoundException as e:
        return {"statusCode": 404, "body": e.content.message}
    except Exception as e:
        return {"statusCode": 500, "body": str(type(e))}

    return response_json(pc_output)


def pcluster_delete_handler(event, _context=None):
    vlab_id, _ = _get_vlab_query_params(event)

    logger.debug(f"delete pcluster {vlab_id}")
    try:
        pc_output = pcluster_delete(vlab_id)
        logger.debug(f"deleted pcluster {vlab_id}")
    except NotFoundException as e:
        return {"statusCode": 404, "body": e.content.message}
    except Exception as e:
        return {"statusCode": 500, "body": str(type(e))}

    return response_json(pc_output)


def _get_vlab_query_params(event):
    vlab_id = event.get("vlab_id")
    options = {}

    logger.debug(f"Event: {event}")
    if vlab_id is None and "queryStringParameters" in event:
        if options := event.get("queryStringParameters"):
            vlab_id = options.pop("vlab_id", None)

    if vlab_id is None:
        raise InvalidRequest("missing required 'vlab_id' query param")

    return vlab_id, options


def response_text(text: str, code: int = 200):
    return {"statusCode": code, "body": text}


def response_json(data: dict, code: int = 200):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data),
    }
