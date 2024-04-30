#!/usr/bin/env python

# This is the top-level script to create a Parallel Cluster
# It requires the `base_system` terraform to have been applied. If not it will error out.

from pathlib import Path

import yaml
from pcluster import lib as pc

from .yaml_loader import load_yaml_extended

PCLUSTER_CONFIG_TPL = str(Path(__file__).parent / "config" / "compute_cluster.tpl.yaml")
VLAB_TAG_KEY = "obp:costcenter:vlabid"
PROJECT_TAG_KEY = "obp:costcenter:project"

DEFAULTS = {
    "tier": "lite",
    "fs_type": "efs",
    "project_id": "-",
}

CONFIG_VALUES = {
    "base_subnet_id": "subnet-02719babe5e178f9f",  # Compute-0 # TODO: Dynamic
    # "base_subnet_id": "subnet-061e82790d3f3fafc",  # Compute-0 # TODO: Dynamic
    "base_security_group_id": "sg-0a22b30ec4989f0ba",  # sbo-poc-compute-hpc-sg
    "efs_id": "fs-0e64b596272e62bb2",  # Home
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

    with open(PCLUSTER_CONFIG_TPL, "r") as f:
        pcluster_config = load_yaml_extended(f, CONFIG_VALUES)

    # Add tags
    pcluster_config["Tags"].extend(
        [
            {
                "Key": VLAB_TAG_KEY,
                "Value": vlab_id,
            },
            {
                "Key": PROJECT_TAG_KEY,
                "Value": options["project_id"],
            },
        ]
    )

    if options["tier"] == "lite":
        queues = pcluster_config["Scheduling"]["SlurmQueues"]
        del queues[1:]

    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    output_file = f"deployment-{cluster_name}.yaml"

    with open(output_file, "w") as out:
        yaml.dump(pcluster_config, out, sort_keys=False)

    # On success returns json. Otherwise throws
    return pc.create_cluster(cluster_name=cluster_name, cluster_configuration=output_file)


def pcluster_describe(vlab_id: str):
    """Describe a cluster, given the vlab_id"""
    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    return pc.describe_cluster(cluster_name=cluster_name)


def pcluster_delete(vlab_id: str):
    """Destroy a cluster, given the vlab_id"""
    cluster_name = f"hpc-pcluster-vlab-{vlab_id}"
    return pc.delete_cluster(cluster_name=cluster_name)
