FROM public.ecr.aws/lambda/python:3.12

RUN dnf -y install nodejs findutils && python3 -m pip install aws-parallelcluster==3.9.3 awslambdaric

ADD hpc_provisioner /opt/hpc_provisioner
RUN python3 -m pip install /opt/hpc_provisioner

WORKDIR /opt/hpc_provisioner/src/hpc_provisioner

ENTRYPOINT ["/var/lang/bin/python3", "-m", "awslambdaric"]
CMD [ "hpc_provisioner.handlers.pcluster_handler" ]
