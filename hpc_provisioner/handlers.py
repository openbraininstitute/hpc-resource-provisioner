import json

from .pcluster_manager import pcluster_create, pcluster_delete, pcluster_describe
from .pcluster_manager import PClusterError, InvalidRequest


def pcluster_create_handler(event, _context=None):
    """Request the creation of an HPC cluster for a given vlab_id"""
    try:
        vlab_id, options = _get_vlab_query_params(event)
        pc_output = pcluster_create(vlab_id, options)
    except InvalidRequest as e:
        return reponse_text(str(e), code=400)
    except PClusterError as e:
        return {"statusCode": 403, "body": str(e)}
    except Exception as e:
        return {"statusCode": 500, "body": str(e)}

    return reponse_json(pc_output)


def pcluster_describe_handler(event, _context=None):
    """Describe a cluster given the vlab_id"""
    vlab_id, _options = _get_vlab_query_params(event)

    try:
        pc_output = pcluster_describe(vlab_id)
    except Exception as e:
        return {"statusCode": 500, "body": str(e)}

    return reponse_json(pc_output)


def pcluster_delete_handler(event, _context=None):
    vlab_id, _options = _get_vlab_query_params(event)

    try:
        pc_output = pcluster_delete(vlab_id)
    except Exception as e:
        return {"statusCode": 500, "body": str(e)}

    return reponse_json(pc_output)


def _get_vlab_query_params(event):
    vlab_id = event.get("vlab_id")
    options = {}

    if vlab_id is None and "queryStringParameters" in event:
        if options := event.get("queryStringParameters"):
            vlab_id = options.pop("vlab_id", None)

    if vlab_id is None:
        raise InvalidRequest("missing required 'vlab' query param")

    return vlab_id, options


def reponse_text(text: str, code: int = 200):
    return {"statusCode": code, "body": text}


def reponse_json(data: dict, code: int = 200):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data),
    }
