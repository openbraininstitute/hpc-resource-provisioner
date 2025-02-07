FROM public.ecr.aws/lambda/python:3.12
LABEL org.opencontainers.image.source="https://github.com/openbraininstitute/hpc-resource-provisioner"

ARG SETUPTOOLS_SCM_PRETEND_VERSION

RUN dnf -y install nodejs findutils && python3 -m pip install aws-parallelcluster==3.9.3 awslambdaric

ADD hpc_provisioner /opt/hpc_provisioner
RUN python3 -m pip install /opt/hpc_provisioner

COPY patches/model.py /var/lang/lib/python3.12/site-packages/pcluster/cli/model.py
COPY patches/middleware.py /var/lang/lib/python3.12/site-packages/pcluster/cli/middleware.py
COPY patches/entrypoint.py /var/lang/lib/python3.12/site-packages/pcluster/cli/entrypoint.py
COPY patches/common.py /var/lang/lib/python3.12/site-packages/pcluster/api/controllers/common.py

WORKDIR /opt/hpc_provisioner/src/hpc_provisioner

ENTRYPOINT ["/var/lang/bin/python3", "-m", "awslambdaric"]
CMD [ "hpc_provisioner.handlers.pcluster_handler" ]
