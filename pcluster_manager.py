#!/usr/bin/env python

# This is the top-level script to create a Parallel Cluster
# It requires the `base_system` terraform to have been applied. If not it will error out.


import yaml
from pathlib import Path
# from pcluster import lib as pc

PCLUSTER_CONFIG_TPL = str(Path(__file__).parent / "config" / "compute-cluster.tpl.yaml")


DEFAULTS = {
    "tier": "lite",
    "fs_type": "efs",
    "project_id": "-",
}


def pcluster_create_handler(event, _context=None):
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
        full_yaml = yaml.load(f, Loader)

    # Add tags
    full_yaml["Tags"].extend([{
        "Key": "sbo:billing:vlabid",
        "Value": options["vlab_id"]
    }, {
        "Key": "sbo:billing:project",
        "Value": options["project_id"]
    }])



    # return {
    #     "statusCode": 200,
    #     "headers": {"Content-Type": "application/json"},
    #     "body": json.dumps(result)
    # }


# Yaml extension for including files

class Loader(yaml.SafeLoader):

    def __init__(self, stream):
        self._root = Path(stream.name).parent
        super(Loader, self).__init__(stream)

    def include(self, node):
        filename = self._root / str(self.construct_scalar(node))
        with open(filename, 'r') as f:
            return yaml.load(f, Loader)


Loader.add_constructor('!include', Loader.include)

# @click.command()
# @click.argument('cluster-name')
# @click.option('--base-subnet-id', type=str, required=True)
# @click.option('--base-security-group-id', type=str, required=True)
# @click.option('--slurm-db-uri', type=str, required=True)
# @click.option('--slurm-db-secret_arn', type=str, required=True)
# @click.option('--efs-id', type=str, required=True)
# @click.option('--apply', is_flag=True, default=False)
# def create_pcluster(apply, **args):
#     print(args)
#     pcluster_name = args['cluster_name']
#     out_config_file = f"pcluster_creation_{pcluster_name}.yaml"
#     with open(PCLUSTER_CONFIG_TPL) as f:
#         tpl_contents = f.read()

#     final_config = tpl_contents
#     for arg, value in args.items():
#         final_config = final_config.replace("${{" + arg + "}}", value)

#     with open(out_config_file, "w") as f:
#         f.write(final_config)

#     if apply:
#         pc.create_cluster(cluster_name=pcluster_name, cluster_configuration=out_config_file)


if __name__ == "__main__":
    pcluster_create_handler({"vlab_id": "test"})
