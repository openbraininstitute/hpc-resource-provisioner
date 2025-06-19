import logging
from unittest.mock import MagicMock, patch

import pytest

from hpc_provisioner.cluster import Cluster
from hpc_provisioner.dynamodb_actions import (
    SubnetAlreadyRegisteredException,
    free_subnet,
    get_subnet,
    get_unclaimed_clusters,
    register_subnet,
)

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


def test_get_subnet():
    subnet_id = "sub=1"
    cluster = "cluster-1"
    mock_dynamodb_client = MagicMock()
    mock_dynamodb_client.get_item.return_value = {
        "Item": {"subnet_id": {"S": subnet_id}, "cluster": {"S": cluster}}
    }
    result = get_subnet(mock_dynamodb_client, subnet_id=subnet_id)
    mock_dynamodb_client.get_item.assert_called_once_with(
        TableName="sbo-parallelcluster-subnets",
        Key={"subnet_id": {"S": subnet_id}},
        ConsistentRead=True,
    )

    assert result == {subnet_id: cluster}


def test_register_subnet_already_registered():
    subnet_id = "sub-1"
    cluster = "cluster-1"
    mock_dynamodb_client = MagicMock()
    with pytest.raises(SubnetAlreadyRegisteredException):
        with patch(
            "hpc_provisioner.dynamodb_actions.get_subnet", return_value={subnet_id: cluster}
        ) as mock_get_subnet:
            register_subnet(mock_dynamodb_client, subnet_id, cluster)
            mock_get_subnet.assert_called_once_with(mock_dynamodb_client, subnet_id)


@patch("hpc_provisioner.dynamodb_actions.get_subnet", return_value=None)
def test_register_subnet(mock_get_subnet):
    subnet_id = "sub-1"
    cluster = "cluster-1"
    mock_dynamodb_client = MagicMock()
    register_subnet(mock_dynamodb_client, subnet_id, cluster)
    mock_get_subnet.assert_called_once_with(mock_dynamodb_client, subnet_id)
    mock_dynamodb_client.update_item.assert_called_once_with(
        TableName="sbo-parallelcluster-subnets",
        Key={"subnet_id": {"S": subnet_id}},
        AttributeUpdates={"cluster": {"Value": {"S": cluster}}},
    )


def test_free_subnet():
    subnet_id = "sub-1"
    mock_dynamodb_client = MagicMock()
    free_subnet(mock_dynamodb_client, subnet_id)
    mock_dynamodb_client.delete_item.assert_called_once_with(
        TableName="sbo-parallelcluster-subnets", Key={"subnet_id": {"S": subnet_id}}
    )


def test_get_unclaimed_clusters():
    mock_dynamodb_resource = MagicMock()
    mock_table = MagicMock()
    mock_table.query.return_value = {
        "Items": [
            {
                "name": "pcluster-test-dynamo_actions",
                "benchmark": 1,
                "dev": 1,
                "include_lustre": 0,
                "project_id": "dynamo_actions",
                "sim_pubkey": None,
                "admin_ssh_key_name": None,
                "tier": "debug",
                "vlab_id": "test",
                "claimed": 0,
            }
        ]
    }
    mock_dynamodb_resource.Table.return_value = mock_table
    unclaimed_clusters = get_unclaimed_clusters(mock_dynamodb_resource)
    assert unclaimed_clusters[0] == Cluster(
        project_id="dynamo_actions",
        vlab_id="test",
        tier="debug",
        benchmark=True,
        dev=True,
        include_lustre=False,
        claimed=False,
    )
