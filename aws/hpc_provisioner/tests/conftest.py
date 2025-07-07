import copy
import json

import pytest

from hpc_provisioner.cluster import Cluster

PROJECT_ID = "testproject"
VLAB_ID = "testvlab"


@pytest.fixture
def test_cluster():
    return Cluster(
        project_id=PROJECT_ID,
        tier="debug",
        vlab_id=VLAB_ID,
        benchmark=False,
        dev=False,
        include_lustre=True,
    )


@pytest.fixture
def data():
    with open("hpc_provisioner/tests/data.json", "r") as fp:
        return json.load(fp)


@pytest.fixture
def create_event(test_cluster):
    return {"cluster": test_cluster.as_dict(), "path": "/hpc-provisioner/pcluster"}


@pytest.fixture
def event():
    return {
        "vlab_id": VLAB_ID,
        "project_id": PROJECT_ID,
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
def post_create_event(create_event):
    retval = copy.deepcopy(create_event)
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
