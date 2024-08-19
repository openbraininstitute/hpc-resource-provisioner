#!/usr/bin/env python

import pprint
from argparse import ArgumentParser

from hpc_provisioner.pcluster_manager import (
    pcluster_create,
    pcluster_delete,
    pcluster_describe,
    pcluster_list,
)


def create_cluster(args):
    out = pcluster_create(args.vlab_id, {})
    pprint.pprint(out, width=120, sort_dicts=False)


def describe_cluster(args):
    out = pcluster_describe(args.vlab_id)
    pprint.pprint(out, width=120, sort_dicts=False)


def delete_cluster(args):
    out = pcluster_delete(args.vlab_id)
    pprint.pprint(out, width=120, sort_dicts=False)


def list_clusters(args):
    out = pcluster_list()
    pprint.pprint(out, width=120, sort_dicts=False)


def hpc_provisioner():
    parser = ArgumentParser("HPC Resource Provisioner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_create = subparsers.add_parser("create", help="Create a new pcluster")
    parser_create.set_defaults(func=pcluster_create)
    parser_create.add_argument("vlab_id", type=str, help="vlab ID")

    parser_describe = subparsers.add_parser("describe", help="describe a pcluster")
    parser_describe.set_defaults(func=pcluster_describe)
    parser_describe.add_argument("vlab_id", type=str, help="vlab ID")

    parser_delete = subparsers.add_parser("delete", help="delete a pcluster")
    parser_delete.set_defaults(func=pcluster_delete)
    parser_delete.add_argument("vlab_id", type=str, help="vlab ID")

    parser_list = subparsers.add_parser("list", help="list pclusters")
    parser_list.set_defaults(func=pcluster_list)

    args = parser.parse_args()
    kwargs = {}
    if vlab_id := getattr(args, "vlab_id", None):
        kwargs["vlab_id"] = vlab_id
    out = args.func(**kwargs)

    pprint.pprint(out, width=120, sort_dicts=False)


if __name__ == "__main__":
    hpc_provisioner()
