from hpc_provisioner import handlers


def lambda_handler(event, _context=None):
    return handlers.pcluster_handler(event, _context)
