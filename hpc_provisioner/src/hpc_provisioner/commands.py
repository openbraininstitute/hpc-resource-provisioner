#!/usr/bin/env python

import pprint
import sys
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
    subparsers = parser.add_subparsers(dest="command")

    parser_create = subparsers.add_parser("create", help="Create a new pcluster")
    parser_create.add_argument("vlab_id", type=str, help="vlab ID")

    parser_describe = subparsers.add_parser("describe", help="describe a pcluster")
    parser_describe.add_argument("vlab_id", type=str, help="vlab ID")

    parser_delete = subparsers.add_parser("delete", help="delete a pcluster")
    parser_delete.add_argument("vlab_id", type=str, help="vlab ID")

    parser_list = subparsers.add_parser("list", help="list pclusters")

    args = parser.parse_args()

    if args.command == "create":
        out = pcluster_create(sys.argv[2], {})
    elif args.command == "describe":
        out = pcluster_describe(sys.argv[2])
    elif args.command == "delete":
        out = pcluster_delete(sys.argv[2])
    elif args.command == "list":
        out = pcluster_list()
    else:
        raise RuntimeError(f"Invalid command: {sys.argv[1]}")
    pprint.pprint(out, width=120, sort_dicts=False)


if __name__ == "__main__":
    hpc_provisioner()
