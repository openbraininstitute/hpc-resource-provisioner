#!/usr/bin/env python

# This is the top-level script to create a Parallel Cluster
# It requires the `base_system` terraform to have been applied. If not it will error out.

import json
import yaml
from pathlib import Path
from pcluster import lib as pc
from .yaml_loader import load_yaml_extended

PCLUSTER_CONFIG_TPL = str(Path(__file__).parent.parent / "config" / "compute_cluster.tpl.yaml")

DEFAULTS = {
    "tier": "lite",
    "fs_type": "efs",
    "project_id": "-",
}

CONFIG_VALUES = {
    "base_subnet_id": "subnet-0533234eef89bbd93",       # Compute-0 # TODO: Dynamic
    "base_security_group_id": "sg-07bdce153f212accf",   # sbo-poc-compute-hpc-sg
    "efs_id": "fs-0740626872953c769",                   # Home
}


def pcluster_create(vlab_id: str, options: dict):
    """Create a pcluster for a given vlab

    Args:
        vlab_id: The id of the vlab
        options: a dict of user provided options.
            All possible options can be seen in DEFAULTS.

    """
    for k, default in DEFAULTS.items():
        options.setdefault(k, default)

    with open(PCLUSTER_CONFIG_TPL, 'r') as f:
        pcluster_config = load_yaml_extended(f, CONFIG_VALUES)

    # Add tags
    pcluster_config["Tags"].extend([{
        "Key": "sbo:billing:vlabid",
        "Value": vlab_id,
    }, {
        "Key": "sbo:billing:project",
        "Value": options["project_id"],
    }])

    if options["tier"] == "lite":
        queues = pcluster_config["Scheduling"]["SlurmQueues"]
        del queues[1:]

    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    output_file = f"deployment-{cluster_name}.yaml"

    with open(output_file, "w") as out:
        yaml.dump(pcluster_config, out, sort_keys=False)

    # On success returns json. Otherwise throws
    return pc.create_cluster(cluster_name=cluster_name, cluster_configuration=output_file)


def pcluster_create_handler(event, _context=None):
    """Request the creation of an HPC cluster for a given vlab_id
    """
    vlab_id, options = get_vlab_query_params(event)

    try:
        pc_output = pcluster_create(vlab_id, options)
    except Exception as e:
        return {"statusCode": 400, "body": str(e)}

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(pc_output)
    }


def pcluster_describe(vlab_id: str):
    """Describe a cluster, given the vlab_id
    """
    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    return pc.describe_cluster(cluster_name=cluster_name)


def pcluster_describe_handler(event, _context=None):
    """Describe a cluster given the vlab_id
    """
    vlab_id, _options = get_vlab_query_params(event)

    try:
        pc_output = pcluster_describe(vlab_id)
    except Exception as e:
        return {"statusCode": 400, "body": str(e)}

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(pc_output)
    }


def pcluster_delete(vlab_id: str):
    """Destroy a cluster, given the vlab_id
    """
    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    return pc.delete_cluster(cluster_name=cluster_name)


def get_vlab_query_params(event):
    vlab_id = event.get("vlab_id")
    options = {}

    if vlab_id is None and "queryStringParameters" in event:
        if options := event.get("queryStringParameters"):
            vlab_id = options.pop("vlab_id")

    if vlab_id is None:
        raise RuntimeError("missing required 'vlab' query param")

    return vlab_id, options
