#!/usr/bin/env python

# This is the top-level script to create a Parallel Cluster
# It requires the `base_system` terraform to have been applied. If not it will error out.

import json
import pprint
import sys
import yaml
from pathlib import Path
from pcluster import lib as pc

PCLUSTER_CONFIG_TPL = str(Path(__file__).parent / "config" / "compute_cluster.tpl.yaml")

DEFAULTS = {
    "tier": "lite",
    "fs_type": "efs",
    "project_id": "-",
}
CONFIG_VALUES = {
    "base_subnet_id": "subnet-0890aaffabda6d298",       # Compute-0 # TODO: Dynamic
    "base_security_group_id": "sg-0cf0c39efb8c1b033",   # VPC default
    "efs_id": "fs-06fba3379737f55c0",                   # Home
}


def pcluster_create_handler(event, _context=None):
    """Request the creation of an HPC cluster for a given vlab_id
    """
    vlab = event.get("vlab_id")
    if vlab is None and "queryStringParameters" in event:
        options = event.get("queryStringParameters")
    else:
        options = {"vlab_id": vlab}  # enable testing
    if not isinstance(options, dict) or not options.get("vlab_id"):
        return {"statusCode": 400, "body": "missing vlab query param"}

    for k, default in DEFAULTS.items():
        options.setdefault(k, default)

    with open(PCLUSTER_CONFIG_TPL, 'r') as f:
        pcluster_config = YamlLoader(f, CONFIG_VALUES).get_single_data()

    # Add tags
    pcluster_config["Tags"].extend([{
        "Key": "sbo:billing:vlabid",
        "Value": options["vlab_id"]
    }, {
        "Key": "sbo:billing:project",
        "Value": options["project_id"]
    }])

    cluster_name = f"hpc-pcluster-vlab-{vlab}"
    output_file = f"deployment-{cluster_name}.yaml"

    with open(output_file, "w") as out:
        yaml.dump(pcluster_config, out, sort_keys=False)

    try:
        pc_output = pc.create_cluster(cluster_name=cluster_name, cluster_configuration=output_file)
    except Exception as e:
        return {"statusCode": 400, "body": str(e)}

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(pc_output)
    }


def pcluster_describe_handler(event, _context=None):
    """Describe a cluster given the vlab_id
    """
    vlab = event.get("vlab_id")
    if vlab is None and "queryStringParameters" in event:
        if options := event.get("queryStringParameters"):
            vlab = options.get("vlab_id")

    cluster_name = f"hpc-pcluster-vlab-{vlab}"
    pc_output = pc.describe_cluster(cluster_name=cluster_name)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(pc_output)
    }


class YamlLoader(yaml.SafeLoader):
    """A custom Yaml Loader for handling of includes and config values
    """

    def __init__(self, stream, config_map):
        self._root = Path(stream.name).parent
        self._config_map = config_map
        super(YamlLoader, self).__init__(stream)

    def include(self, node):
        filename = self._root / str(self.construct_scalar(node))
        with open(filename, 'r') as f:
            return YamlLoader(f, self._config_map).get_single_data()

    def config(self, node):
        config_entry = str(self.construct_scalar(node))
        return self._config_map[config_entry]


YamlLoader.add_constructor('!include', YamlLoader.include)
YamlLoader.add_constructor('!config', YamlLoader.config)


if __name__ == "__main__":
    if len(sys.argv) == 3:
        if sys.argv[1] == "create":
            out = pcluster_create_handler({"vlab_id": sys.argv[2]})
        elif sys.argv[1] == "describe":
            out = pcluster_describe_handler({"vlab_id": sys.argv[2]})
        else:
            raise RuntimeError(f"Invalid command: {sys.argv[1]}")
        pprint.pprint(out, width=120, sort_dicts=False)
    else:
        print(f"Syntax: {sys.argv[0]} [create, describe] <cluster_name>", file=sys.stderr)
