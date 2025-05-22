from hpc_provisioner import handlers


def lambda_handler(event, _context=None):
    return handlers.main_handler(event, _context)
