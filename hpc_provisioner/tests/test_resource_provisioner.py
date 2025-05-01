import copy
import json
import logging
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.client import ClientError
from pcluster.api.errors import NotFoundException

from hpc_provisioner import handlers, pcluster_manager
from hpc_provisioner.pcluster_manager import InvalidRequest

logger = logging.getLogger("test_logger")
fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(msg)s")
fh = logging.FileHandler("./test.log")
fh.setFormatter(fmt)
fh.setLevel(logging.DEBUG)
sh = logging.StreamHandler()
sh.setFormatter(fmt)
sh.setLevel(logging.DEBUG)
logger.addHandler(fh)
logger.addHandler(sh)
logger.setLevel(logging.DEBUG)


def expected_response_template(status_code=200, text=""):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": text,
    }


@pytest.fixture
def data():
    with open("hpc_provisioner/tests/data.json", "r") as fp:
        return json.load(fp)


@pytest.fixture
def event():
    return {
        "vlab_id": "test_vlab",
        "project_id": "test_project",
        "path": "/hpc-provisioner/pcluster",
    }


@pytest.fixture
def get_event(event):
    retval = copy.deepcopy(event)
    retval["httpMethod"] = "GET"
    retval.pop("vlab_id")
    retval["queryStringParameters"] = {
        "vlab_id": "vlab_as_querystring_param",
        "project_id": "project_as_querystring_param",
    }
    return retval


@pytest.fixture
def post_event(event):
    retval = copy.deepcopy(event)
    retval["httpMethod"] = "POST"
    return retval


@pytest.fixture
def put_event(event):
    retval = copy.deepcopy(event)
    retval["httpMethod"] = "PUT"
    return retval


@pytest.fixture
def delete_event(event):
    retval = copy.deepcopy(event)
    retval["httpMethod"] = "DELETE"
    return retval


def cluster_name(vlab_id, project_id):
    return f"pcluster-{vlab_id}-{project_id}"


@patch("hpc_provisioner.handlers.pcluster_describe_handler")
@patch("hpc_provisioner.handlers.pcluster_create_request_handler")
@patch("hpc_provisioner.handlers.pcluster_delete_handler")
@pytest.mark.parametrize(
    "event_to_test",
    [
        "get_event",
        "post_event",
        "delete_event",
    ],
)
def test_pcluster_handler_routing(  # noqa PLR0913
    patched_delete_handler,
    patched_create_request_handler,
    patched_describe_handler,
    event_to_test,
    request,
):
    event_to_test = request.getfixturevalue(event_to_test)
    all_patched_handlers = [
        patched_describe_handler,
        patched_create_request_handler,
        patched_delete_handler,
    ]

    handlers.pcluster_handler(event_to_test)
    logger.debug(f"Checking {event_to_test}")

    for patched_handler in all_patched_handlers:
        if (
            (patched_handler == patched_describe_handler and event_to_test["httpMethod"] == "GET")
            or (
                patched_handler == patched_create_request_handler
                and event_to_test["httpMethod"] == "POST"
            )
            or (
                patched_handler == patched_delete_handler
                and event_to_test["httpMethod"] == "DELETE"
            )
        ):
            logger.debug(f"Making sure that handler {patched_handler} was called")
            patched_handler.assert_called_once()
        else:
            logger.debug(f"Making sure that handler {patched_handler} was not called")
            patched_handler.assert_not_called()


def test_get(data, get_event):
    with patch(
        "hpc_provisioner.pcluster_manager.pc.describe_cluster",
        return_value=data["existingCluster"],
    ) as describe_cluster:
        vlab_id = get_event["queryStringParameters"]["vlab_id"]
        project_id = get_event["project_id"]
        result = handlers.pcluster_describe_handler(get_event)
        describe_cluster.assert_called_once_with(
            cluster_name=cluster_name(vlab_id, project_id),
            region="us-east-1",
        )
    expected_response = expected_response_template(text=json.dumps(data["existingCluster"]))
    assert result == expected_response


def test_get_all_clusters(data):
    with patch(
        "hpc_provisioner.pcluster_manager.pc.list_clusters", return_value=data["clusterList"]
    ):
        result = handlers.pcluster_describe_handler({"httpMethod": "GET"})

    expected_response = expected_response_template(text=json.dumps(data["clusterList"]))
    assert result == expected_response


@patch("hpc_provisioner.handlers.boto3")
@pytest.mark.parametrize("key_exists", [True, False])
def test_post(patched_boto3, post_event, key_exists):
    test_cluster_name = cluster_name(post_event["vlab_id"], post_event["project_id"])
    mock_client = MagicMock()
    patched_boto3.client.return_value = mock_client
    with patch("hpc_provisioner.handlers.create_keypair") as patched_create_keypair:
        if key_exists:
            patched_create_keypair.side_effect = [
                {
                    "KeyName": test_cluster_name,
                },
                {"KeyName": f"{test_cluster_name}_sim"},
            ]
        else:
            patched_create_keypair.side_effect = [
                {"KeyMaterial": "secret-stuff", "KeyName": test_cluster_name},
                {
                    "KeyMaterial": """-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEAvfvswsbNBM05kutLby0DZEl+tWx62yqMU0IgKqEoPamtgS3s
V6S5xOLqYItd5UAMLf4pAGbvqXNy8BbVNmiKfPEXRfBq1hC4t/FmILIh5uyTRqEe
ocB9s/RIR/bkAdrhK60ZzwPD4RHqfShGE6FuB3VPHbxWVsfrYjjsC66n675qSdnk
/4N69aURUX3xB+Rco2i1RW3VUbylPXnbKlG1KtIYGp6ctv3vQf3zXR7snp4580mu
1T6DBSmdhNY7r/IUGcQTePNo+R89FaK0OEOVNuPJUsT8InEihmTxR8HTkS6x31kd
OW9uWyCjUhZ86JgYMIWInOuD6dVjiVfOS3lz4wIDAQABAoIBAA6TWWLIJcqMhDJF
YxAwf+YdzV7V58cQyJtKo3Uh0BiLAAi9ITjIJoh4cErf5mBEPar5qOOjAhgaB2Ns
HQeDlbxoMsTm4QtzVPinyJIRmJBC7jmo+tSmE/7Oaw06X9vUkxnqueQsAccuvLLF
eDrhU7O2yE8bt/QIeoKao2FyEOgBHf5REK97PpXiuKC1YrZ4xf1akQJeKXOuVGMc
J373BnbiM2vAuB9nZxIwMqpALEV5Rd5kI/pjZViAMqZiZb5zworncdL05mRn9M9S
nIV8/lN2wvtiyT8fyapcY9nqYxTOwR6PrjM9xPWX8eehnR+357IoPPsxCVpd3Npt
r2YbhyECgYEA5vOejzbmVQSYfc46g0WQgvfwMvfUPGtl1mvakgdiM4TlxzfrTUxO
3Tt0ClP5eO6szp26U/8RMlmwCGSZeR+hp5ATu/KpElWOJESAeuMRkPzsebGwpqHU
g8FYBhbCZlxBP1VBtu5HVMzPTlzs1nWLERuRoKSjzbvqQy8udowv5f0CgYEA0pbW
+1S8M+/CuTgCscnjnEKOyo3/o821GUjwacRPJ1Rs6VO5bSUOdfD87zl5Bw2MO+YO
UVbr9DazDshoIglqPPMVUedMGkoKaoVm3XovLLs8Bf+w6nvf/cTyIG7L2Zg4S8bx
4zEW+3JezIcB5exhKzpt8SnezJy/yV/wOZ28918CgYAyhf8c83SmCrBVbUUtrI01
qYnZjI/Ye+I2azfQlF7uSFeAIoKOUXA7Q6NaEw7TXttdA/JcJ8OaUTaKT3+nmLzj
jEhU6HwGL8M9ueKlf4E7R6lv4eh0O5jjDev0wQvcGriHY15R54ShT4DWcsu5CtPW
dUKBcyMGgeJ4uhyfAIIF/QKBgC61VimYucWrQD1ktvRIGzvlZ1Z1+GWUkr5w9yH+
cLAAgcee0lnrBjISqYdF8BooXxpKBJL1/I/GMiDtQmuKOw4ZvHjWHIMYOQc3X4Fw
QFZjkQSjmdHod94JeMrIyF4S7SmhjrUdhkNvMqeaqkkdDNBRvWDoMIqhmchIhzfA
TNFxAoGATB6ReLKjX8kudSzGKQEYiMN9afFCYt4UsoED/FPoOTu7K9kuZ7Sbh/Q3
WoeXwwyBA7QuulZo9ACvHw6PqHbqQqD8IqJVocYisq9EmGFSnAmUYIX7hBwWr7pP
e15Cgo+/r/nqbT21oTkp4rbw5nT9lVyuHyBralzJ7Q/BDXXY0v0=
-----END RSA PRIVATE KEY-----""",
                    "KeyName": f"{test_cluster_name}_sim",
                },
            ]

        with patch("hpc_provisioner.handlers.store_private_key") as patched_store_private_key:
            patched_store_private_key.side_effect = [
                {"ARN": "secret ARN"},
                {"ARN": "secret ARN sim"},
            ]
            actual_response = handlers.pcluster_create_request_handler(post_event)
    expected_args = {
        "vlab_id": post_event["vlab_id"],
        "project_id": post_event["project_id"],
        "keyname": f"pcluster-{post_event['vlab_id']}-{post_event['project_id']}",
        "options": {
            "benchmark": False,
            "dev": False,
            "include_lustre": True,
            "tier": None,
            "project_id": post_event["project_id"],
            "vlab_id": post_event["vlab_id"],
            "keyname": None,
            "sim_pubkey": None,
        },
    }
    if not key_exists:
        expected_args["sim_pubkey"] = (
            """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC9++zCxs0EzTmS60tvLQNkSX61bHrbKoxTQiAqoSg9qa2BLexXpLnE4upgi13lQAwt/ikAZu+pc3LwFtU2aIp88RdF8GrWELi38WYgsiHm7JNGoR6hwH2z9EhH9uQB2uErrRnPA8PhEep9KEYToW4HdU8dvFZWx+tiOOwLrqfrvmpJ2eT/g3r1pRFRffEH5FyjaLVFbdVRvKU9edsqUbUq0hganpy2/e9B/fNdHuyenjnzSa7VPoMFKZ2E1juv8hQZxBN482j5Hz0VorQ4Q5U248lSxPwicSKGZPFHwdORLrHfWR05b25bIKNSFnzomBgwhYic64Pp1WOJV85LeXPj"""
        )
    mock_client.invoke_async.assert_called_with(
        FunctionName="hpc-resource-provisioner-creator",
        InvokeArgs=json.dumps(expected_args),
    )
    expected_response = expected_response_template(
        text=json.dumps(
            {
                "cluster": {
                    "clusterName": test_cluster_name,
                    "clusterStatus": "CREATE_REQUEST_RECEIVED",
                    "private_ssh_key_arn": "secret ARN",
                    "ssh_user": "sim",
                },
                "admin_user_private_ssh_key_arn": "secret ARN",
                "private_ssh_key_arn": "secret ARN sim",
            }
        )
    )
    assert actual_response == expected_response


@patch(
    "hpc_provisioner.aws_queries.dynamodb_client",
)
@patch("hpc_provisioner.aws_queries.free_subnet")
@patch("hpc_provisioner.pcluster_manager.remove_key")
def test_delete(
    patched_remove_key, patched_free_subnet, patched_dynamodb_client, data, delete_event
):
    mock_client = MagicMock()
    patched_dynamodb_client.return_value = mock_client
    with patch(
        "hpc_provisioner.pcluster_manager.pc.delete_cluster", return_value=data["deletingCluster"]
    ) as patched_delete_cluster:
        with patch(
            "hpc_provisioner.aws_queries.get_registered_subnets",
            return_value={
                "subnet-123": cluster_name(delete_event["vlab_id"], delete_event["project_id"]),
                "subnet-234": cluster_name(delete_event["vlab_id"], delete_event["project_id"]),
            },
        ) as patched_get_registered_subnets:
            actual_response = handlers.pcluster_delete_handler(delete_event)
            patched_delete_cluster.assert_called_once_with(
                cluster_name=cluster_name(delete_event["vlab_id"], delete_event["project_id"]),
                region="us-east-1",
            )
    expected_response = expected_response_template(text=json.dumps(data["deletingCluster"]))
    assert actual_response == expected_response
    patched_get_registered_subnets.assert_called_once()
    assert patched_remove_key.call_count == 2
    call1 = call(mock_client, "subnet-123")
    call2 = call(mock_client, "subnet-234")
    patched_free_subnet.assert_has_calls([call1, call2], any_order=True)


def test_get_not_found(get_event):
    vlab_id = get_event["queryStringParameters"]["vlab_id"]
    project_id = get_event["queryStringParameters"]["project_id"]
    error_message = f"Cluster {vlab_id}-{project_id} does not exist"
    with patch(
        "hpc_provisioner.pcluster_manager.pc.describe_cluster",
        side_effect=NotFoundException(error_message),
    ) as describe_cluster:
        result = handlers.pcluster_describe_handler(get_event)
        describe_cluster.assert_called_once()
    assert result == {"statusCode": 404, "body": error_message}


def test_get_internal_server_error(get_event):
    with patch(
        "hpc_provisioner.pcluster_manager.pc.describe_cluster",
        side_effect=RuntimeError,
    ) as patched_describe_cluster:
        result = handlers.pcluster_describe_handler(get_event)
        patched_describe_cluster.assert_called_once()
    assert result == {"statusCode": 500, "body": "<class 'RuntimeError'>"}


@patch(
    "hpc_provisioner.aws_queries.dynamodb_client",
)
@patch("hpc_provisioner.pcluster_manager.remove_key")
def test_delete_not_found(patched_remove_key, patched_dynamodb_client, delete_event):
    error_message = f"Cluster {delete_event['vlab_id']}-{delete_event['project_id']} does not exist"
    with patch(
        "hpc_provisioner.pcluster_manager.pc.delete_cluster",
        side_effect=NotFoundException(error_message),
    ) as delete_cluster:
        result = handlers.pcluster_delete_handler(delete_event)
        delete_cluster.assert_called_once()
    assert result == {"statusCode": 404, "body": error_message}
    patched_dynamodb_client.assert_called_once()
    assert patched_remove_key.call_count == 2


@patch(
    "hpc_provisioner.aws_queries.dynamodb_client",
)
@patch("hpc_provisioner.pcluster_manager.remove_key")
def test_delete_internal_server_error(patched_remove_key, patched_dynamodb_client, delete_event):
    with patch(
        "hpc_provisioner.pcluster_manager.pc.delete_cluster",
        side_effect=RuntimeError,
    ) as patched_delete_cluster:
        result = handlers.pcluster_delete_handler(delete_event)
        patched_delete_cluster.assert_called_once()
    assert result == {"statusCode": 500, "body": "<class 'RuntimeError'>"}
    patched_dynamodb_client.assert_called_once()
    assert patched_remove_key.call_count == 2


@patch("hpc_provisioner.pcluster_manager.pc.create_cluster")
@patch("hpc_provisioner.pcluster_manager.boto3")
def test_do_create_already_exists(patched_boto3, patched_create_cluster, post_event):
    mock_cloudformation_client = MagicMock()
    patched_boto3.client.return_value = mock_cloudformation_client
    handlers.pcluster_do_create_handler(post_event)
    mock_cloudformation_client.describe_stacks.assert_called_once_with(
        StackName=cluster_name(post_event["vlab_id"], post_event["project_id"])
    )
    patched_create_cluster.assert_not_called()


@patch("hpc_provisioner.pcluster_manager.pc.create_cluster")
@patch("hpc_provisioner.pcluster_manager.boto3")
@patch("hpc_provisioner.pcluster_manager.get_available_subnet", return_value="subnet-123")
@patch("hpc_provisioner.pcluster_manager.get_security_group", return_value="sg-123")
@patch("hpc_provisioner.pcluster_manager.get_efs", return_value="efs-123")
def test_do_create(
    patched_get_efs,
    patched_get_security_group,
    patched_get_available_subnet,
    patched_boto3,
    patched_create_cluster,
    post_event,
):
    mock_cloudformation_client = MagicMock()
    mock_cloudformation_client.describe_stacks.side_effect = ClientError(
        operation_name="describe_stacks", error_response={404: "No stacks found"}
    )
    mock_ec2_client = MagicMock()
    mock_efs_client = MagicMock()
    patched_boto3.client.side_effect = lambda x: {
        "cloudformation": mock_cloudformation_client,
        "ec2": mock_ec2_client,
        "efs": mock_efs_client,
    }[x]
    post_event["keyname"] = cluster_name(post_event["vlab_id"], post_event["project_id"])
    handlers.pcluster_do_create_handler(post_event)
    patched_create_cluster.assert_called_once()
    assert patched_create_cluster.call_args.kwargs["cluster_name"] == cluster_name(
        post_event["vlab_id"], post_event["project_id"]
    )
    assert "tmp" in patched_create_cluster.call_args.kwargs["cluster_configuration"]
    patched_get_efs.assert_called_once()
    patched_get_security_group.assert_called_once()
    patched_get_available_subnet.assert_called_once()


def test_invalid_http_method(put_event):
    actual_response = handlers.pcluster_handler(put_event)
    assert actual_response == {
        "statusCode": 400,
        "body": f"{put_event['httpMethod']} not supported",
    }


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_vlab_id_not_specified(method):
    with pytest.raises(InvalidRequest):
        handlers.pcluster_handler({"httpMethod": method})


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_project_id_not_specified(method):
    with pytest.raises(InvalidRequest):
        handlers.pcluster_handler({"httpMethod": method, "vlab_id": "test_vlab"})


def test_http_method_not_specified():
    response = handlers.pcluster_handler({})
    assert response == {
        "statusCode": 400,
        "body": "Could not determine HTTP method - make sure to GET, POST or DELETE",
    }


@pytest.mark.parametrize("tier,is_valid", [("prod-mpi", True), ("extra-expensive", False)])
def test_load_tier(tier, is_valid):
    pcluster_config = {
        "Scheduling": {"SlurmQueues": [{"Name": "debug"}, {"Name": "prod-mpi"}, {"Name": "lite"}]}
    }
    options = {"tier": tier}
    if is_valid:
        queues = pcluster_manager.choose_tier(pcluster_config, options)
        logger.debug(pcluster_config)
        assert len(queues) == 1
        assert queues[0]["Name"] == tier
    else:
        with pytest.raises(ValueError):
            pcluster_manager.choose_tier(pcluster_config, options)
