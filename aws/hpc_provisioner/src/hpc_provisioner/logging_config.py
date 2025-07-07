LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"fmt": {"format": "[%(asctime)s] [%(levelname)s] %(msg)s"}},
    "handlers": {
        "sh": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "fmt",
        },
    },
    "loggers": {"hpc-resource-provisioner": {"level": "DEBUG", "handlers": ["sh"]}},
}
