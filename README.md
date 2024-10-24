# HPC Resource Provisioner

The HPC Resource Provisioner is a small application that offers an API to manage the creation and deletion of parallel-clusters in AWS. When creating a parallel-cluster, consumers are expected to poll regularly to check the progress.

## Uploading the container image to the POC

By default, the `upload to ecr` job will upload the resource provisioner container images to the sandbox account. If you want to upload to the PoC account, you'll need to run the job manually and set the `ENVIRONMENT` variable to "production".

Before running the job, however, you'll need to modify the AWS_CREDENTIALS variable. The reason for this is that it unfortunately includes a session token that expires and we haven't invested time into investigating why yet.

To get the credentials, go to https://bbp-sbo-poc.awsapps.com/start/#/?tab=accounts and log in. On the access portal, click the `Access keys` link for the `FullECSContainersAccess` account and copy the contents of the AWS credentials file.
Next, go to https://bbpgitlab.epfl.ch/hpc/hpc-resource-provisioner/-/settings/ci_cd and expand the Variables section, then edit the `AWS_CREDENTIALS` variable. Replace the value with the value you just copied and save the variable.

## Manually uploading an image to the PoC ECR

To get the credentials, go to https://bbp-sbo-poc.awsapps.com/start/#/?tab=accounts and log in. On the access portal, click the `Access keys` link for the `FullECSContainersAccess` account and copy the contents of the AWS credentials file. Put these in `~/.aws/credentials` (this can be a symlink if you're juggling multiple credential sets).
Keep in mind that there's a session token included with these credentials, so they will become invalid after some time. At that point you'll have to perform this step again.

Now you can log in (if you use docker, replace `podman` with `docker` and everything should work the same):

```bash
aws ecr get-login-password --profile 671250183987_FullECSContainersAccess --region us-east-1 | podman login --username AWS --password-stdin 671250183987.dkr.ecr.us-east-1.amazonaws.com
```

With all of this done, you can finally push:

```bash
podman push prov:$PROV_VERSION 671250183987.dkr.ecr.us-east-1.amazonaws.com/hpc-resource-provisioner:latest
```

## Installing locally

Create a virtualenv and run `pip install .` in the repository root:

```bash
python3.12 -m venv venv
pip install hpc_provisioner
```

You now have the `hpc-provisioner` entrypoint available in your virtualenv.


## Manual Usage

Using the HPC provisioner is fairly straightforward:

```bash
hpc-provisioner create my-pcluster
hpc-provisioner describe my-pcluster
hpc-provisioner delete my-pcluster
hpc-provisioner list
```

Manually calling the deployed API gateway is also possible. Save your AWS keypair as environment variables:

```bash
export AWS_ACCESS_KEY_ID=$(awk '/^aws_access_key_id/ {print $3}' ~/.aws/credentials)
export AWS_SECRET_ACCESS_KEY=$(awk '/^aws_secret/ {print $3}' ~/.aws/credentials)
```

You can get the URL from your API Gateway's Deployment page: in the AWS console, go to API Gateway -> hpc_resource_provisioner -> Stages -> fold out the stage you want down to the method you want and copy the Invoke URL.

Now you can use curl - make sure to set the region in the `aws-sigv4` parameter to match the region in the URL:

```bash
curl -X POST --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" --aws-sigv4 "aws:amz:us-east-1:execute-api" https://l1k1iw8me4.execute-api.us-east-1.amazonaws.com/production/hpc-provisioner/pcluster\?vlab_id\=my-pcluster
curl -X GET --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" --aws-sigv4 "aws:amz:us-east-1:execute-api" https://l1k1iw8me4.execute-api.us-east-1.amazonaws.com/production/hpc-provisioner/pcluster\?vlab_id\=my-pcluster
curl -X DELETE --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" --aws-sigv4 "aws:amz:us-east-1:execute-api" https://l1k1iw8me4.execute-api.us-east-1.amazonaws.com/production/hpc-provisioner/pcluster\?vlab_id\=my-pcluster
```

Of course, you can also simply call the required method from the API definition n the AWS console: go to API Gateway -> hpc_resource_provisioner -> Resources -> fold out the resources down to the method you want and select the Test tab.

If you want to skip the API part and call the lambda directly, that's also possible: go to Lambda -> hpc-resource-provisioner -> Test tab and put this in the Event JSON field:

```json
{
    "httpMethod": "GET",
    "vlab_id": "my-pcluster"
}
```

You can replace the `httpMethod` with `POST` or `DELETE` as desired.

## Development

### Version

When building, don't forget to bump the version number in hpc_provisioner/pyproject.toml - this is used to determine the container version!

### Tags

The resource provisioner uses certain resources deployed in the AWS cloud and identifies the ones it can use through the presence of the `HPC_Goal:compute_cluster` tag. If there's a need for new terraform-deployed resources to be used, don't forget to apply this tag in the [terraform configuration](https://bbpgitlab.epfl.ch/hpc/hpc-resource-provisioner/).

### Using Ruff

`ruff check` will output a list of formatting issues with your code
`ruff check --fix` will actually fix the issues for you. Make sure to proofread!

### Testing

```bash
python3.12 -m venv venv
pip install -e 'hpc_provisioner[test]'
pytest hpc_provisioner
```
# Acknowledgment

The development of this software was supported by funding to the Blue Brain Project,
a research center of the École polytechnique fédérale de Lausanne (EPFL),
from the Swiss government's ETH Board of the Swiss Federal Institutes of Technology.

Copyright (c) 2024-2024 Blue Brain Project/EPFL

