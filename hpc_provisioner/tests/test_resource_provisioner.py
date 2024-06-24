import copy
import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from hpc_provisioner import handlers
from hpc_provisioner.pcluster_manager import InvalidRequest
from pcluster.api.errors import NotFoundException

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
    return {"vlab_id": "test_vlab", "project_id": "test_project"}


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
def test_post(patched_boto3, post_event):
    mock_client = MagicMock()
    patched_boto3.client.return_value = mock_client
    actual_response = handlers.pcluster_create_request_handler(post_event)
    mock_client.invoke_async.assert_called_once_with(
        FunctionName="hpc-resource-provisioner-creator",
        InvokeArgs=json.dumps(
            {"vlab_id": post_event["vlab_id"], "project_id": post_event["project_id"]}
        ),
    )
    expected_response = expected_response_template(
        text=json.dumps(
            {
                "cluster": {
                    "clusterName": cluster_name(post_event["vlab_id"], post_event["project_id"]),
                    "clusterStatus": "CREATE_REQUEST_RECEIVED",
                }
            }
        )
    )
    assert actual_response == expected_response


def test_delete(data, delete_event):
    with patch(
        "hpc_provisioner.pcluster_manager.pc.delete_cluster", return_value=data["deletingCluster"]
    ) as patched_delete_cluster:
        actual_response = handlers.pcluster_delete_handler(delete_event)
        patched_delete_cluster.assert_called_once_with(
            cluster_name=cluster_name(delete_event["vlab_id"], delete_event["project_id"]),
            region="us-east-1",
        )
    expected_response = expected_response_template(text=json.dumps(data["deletingCluster"]))
    assert actual_response == expected_response


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


def test_delete_not_found(delete_event):
    error_message = f"Cluster {delete_event['vlab_id']}-{delete_event['project_id']} does not exist"
    with patch(
        "hpc_provisioner.pcluster_manager.pc.delete_cluster",
        side_effect=NotFoundException(error_message),
    ) as delete_cluster:
        result = handlers.pcluster_delete_handler(delete_event)
        delete_cluster.assert_called_once()
    assert result == {"statusCode": 404, "body": error_message}


def test_delete_internal_server_error(delete_event):
    with patch(
        "hpc_provisioner.pcluster_manager.pc.delete_cluster",
        side_effect=RuntimeError,
    ) as patched_delete_cluster:
        result = handlers.pcluster_delete_handler(delete_event)
        patched_delete_cluster.assert_called_once()
    assert result == {"statusCode": 500, "body": "<class 'RuntimeError'>"}


@patch("hpc_provisioner.pcluster_manager.pc.create_cluster")
def test_do_create(patched_create_cluster, post_event):
    handlers.pcluster_do_create_handler(post_event)
    patched_create_cluster.assert_called_once()
    assert patched_create_cluster.call_args.kwargs["cluster_name"] == cluster_name(
        post_event["vlab_id"], post_event["project_id"]
    )
    assert patched_create_cluster.call_args.kwargs["cluster_configuration"].startswith("/tmp/tmp")


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
