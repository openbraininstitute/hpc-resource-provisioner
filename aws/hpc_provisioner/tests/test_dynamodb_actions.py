import logging
from unittest.mock import MagicMock, patch

import pytest
from hpc_provisioner.dynamodb_actions import (
    SubnetAlreadyRegisteredException,
    free_subnet,
    get_subnet,
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
