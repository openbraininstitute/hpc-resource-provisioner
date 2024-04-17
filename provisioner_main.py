#!/usr/bin/env python
import pprint
import sys
from hpc_provisioner.pcluster_manager import pcluster_create, pcluste_describe

if len(sys.argv) == 3:
    if sys.argv[1] == "create":
        out = pcluster_create(sys.argv[2], {})
    elif sys.argv[1] == "describe":
        out = pcluste_describe(sys.argv[2])
    else:
        raise RuntimeError(f"Invalid command: {sys.argv[1]}")
    pprint.pprint(out, width=120, sort_dicts=False)
else:
    print(f"Syntax: {sys.argv[0]} [create, describe] <cluster_name>", file=sys.stderr)
