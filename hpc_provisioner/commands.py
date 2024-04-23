#!/usr/bin/env python

import pprint
import sys

from .pcluster_manager import pcluster_create, pcluster_delete, pcluster_describe

REQUIRED_ARG_COUNT = 3

def hpc_provisioner():
    if len(sys.argv) != REQUIRED_ARG_COUNT:
        print(f"Syntax: {sys.argv[0]} <create, describe, delete> <cluster_name>", file=sys.stderr)
        return 1

    cmd = sys.argv[1]
    if cmd == "create":
        out = pcluster_create(sys.argv[2], {})
    elif cmd == "describe":
        out = pcluster_describe(sys.argv[2])
    elif cmd == "delete":
        out = pcluster_delete(sys.argv[2])
    else:
        raise RuntimeError(f"Invalid command: {sys.argv[1]}")
    pprint.pprint(out, width=120, sort_dicts=False)
