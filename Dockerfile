FROM python:3.9-alpine

# autoconf=2.71-r2 has to come from 3.19; after that they upgraded, which breaks the awslambdaric install
# see https://github.com/aws/aws-lambda-python-runtime-interface-client/issues/144
# libexecinfo-dev has to come from 3.16; after that it was removed :'(

RUN apk add --no-cache --update --repository=https://dl-cdn.alpinelinux.org/alpine/v3.19/main autoconf=2.71-r2 \
 && apk add automake bash binutils cmake g++ gcc libtool make nodejs \
 && apk add --no-cache --update --repository=https://dl-cdn.alpinelinux.org/alpine/v3.16/main/ libexecinfo-dev \
 && python3 -m pip install aws-parallelcluster awslambdaric

ADD hpc_provisioner /opt/hpc_provisioner
RUN python3 -m pip install /opt/hpc_provisioner

# You either do this, or you figure out a way to create the STS endpoint with the global URL
RUN sed -i '/^\s*[^\s]us-east-1.,/d' $(find /usr/local/lib -name args.py | grep botocore)

WORKDIR /opt/hpc_provisioner/src/hpc_provisioner

ENTRYPOINT ["/usr/local/bin/python3", "-m", "awslambdaric"]
CMD [ "hpc_provisioner.handlers.pcluster_handler" ]
