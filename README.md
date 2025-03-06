# HPC Resource Provisioner

The HPC Resource Provisioner is a small application that offers an API to manage the creation and deletion of parallel-clusters in AWS. When creating a parallel-cluster, consumers are expected to poll regularly to check the progress.

## Releasing and uploading the container image

There's a GitHub workflow called `Build and Release HPC Resource Provisioner` that allows for very easy releasing of new versions. Select the branch you want to create a release from, and an AWS environment to push the image to, and run the workflow.

## Manual Usage

If you have awscli configured to connect to the sandbox environment, it's fairly easy to get the necessary variables in your shell. Make sure the keypair for sandbox is the first entry in `~/.aws/credentials`

`source ./sandbox.sh`

Deploying a new cluster. You can run this command multiple times, as long as you specify the same `vlab_id` and `project_id` it will not deploy additional clusters.

Parameters (specify them in alphabetical order!):
* dev: optional: dev mode, when you need features that are currently still in development
* include_lustre: optional: defaults to true: set to false if you don't need lustre, it speeds up deployment and is a lot cheaper
* project_id: required: string to identify your project. Will be part of the cluster name.
* tier: optional: which pcluster configuration you want to deploy. Default: debug (really tiny nodes). See ./hpc_provisioner/src/hpc_provisioner/config/_slurm_queues.tpl.yaml for possible values
* vlab_id: required: string to identify your vlab. Will be part of the cluster name

```bash
curl -X POST --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" --aws-sigv4 "aws:amz:${AWS_REGION}:execute-api" https://${AWS_APIGW_DEPLOY_ID}.execute-api.${AWS_REGION}.amazonaws.com/production/hpc-provisioner/pcluster\?project_id\=test1\&vlab_id\=my-pcluster | jq
```

This will give you a reply that looks like this:
```json
{
  "cluster": {
    "clusterName": "pcluster-my-pcluster-test1",
    "clusterStatus": "CREATE_REQUEST_RECEIVED",
    "private_ssh_key_arn": "arn:aws:secretsmanager:us-east-1:130659266700:secret:pcluster-my-pcluster-test1-T2Aggx"
  }
}
```

You can retrieve the private SSH key for accessing your cluster with the following awscli command:

```bash
aws secretsmanager get-secret-value --secret-id="arn:aws:secretsmanager:us-east-1:130659266700:secret:pcluster-my-pcluster-test1-T2Aggx" | jq -r .SecretString >| secret_key
```

Getting the status of your cluster:

```bash
curl -X GET --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" --aws-sigv4 "aws:amz:${AWS_REGION}:execute-api" https://${AWS_APIGW_DEPLOY_ID}.execute-api.${AWS_REGION}.amazonaws.com/production/hpc-provisioner/pcluster\?project_id\=test1\&vlab_id\=my-pcluster
```

Tearing down your cluster:

```bash
curl -X DELETE --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" --aws-sigv4 "aws:amz:${AWS_REGION}:execute-api" https://${AWS_APIGW_DEPLOY_ID}.execute-api.${AWS_REGION}.amazonaws.com/production/hpc-provisioner/pcluster\?project_id\=test1\&vlab_id\=my-pcluster
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


## Installing locally

You should probably not be doing this unless you have a good reason.

Create a virtualenv and run `pip install .` in the repository root:

```bash
python3.12 -m venv venv
pip install hpc_provisioner
```

You now have the `hpc-provisioner` entrypoint available in your virtualenv.


## Development

### Version

Versions are determined automatically by setuptools-scm.

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

Copyright
=========

Copyright (c) 2024-2024 Blue Brain Project/EPFL

Copyright (c) 2025 Open Brain Institute

This work is licensed under `Apache 2.0 <https://www.apache.org/licenses/LICENSE-2.0.html>`_
