import logging
from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError
from hpc_provisioner.aws_queries import (
    CouldNotDetermineEFSException,
    CouldNotDetermineSecurityGroupException,
    OutOfSubnetsException,
    claim_subnet,
    create_keypair,
    create_secret,
    get_available_subnet,
    get_efs,
    get_secret,
    get_security_group,
    store_private_key,
)
from hpc_provisioner.constants import (
    BILLING_TAG_KEY,
    BILLING_TAG_VALUE,
    PROJECT_TAG_KEY,
    VLAB_TAG_KEY,
)
from hpc_provisioner.dynamodb_actions import SubnetAlreadyRegisteredException

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


@pytest.mark.parametrize(
    "filesystems",
    [
        {
            "FileSystems": [
                {
                    "FileSystemId": "fs-123",
                    "Tags": [
                        {"Key": "HPC_Goal", "Value": "compute_cluster"},
                        {"Key": "SBO_Billing", "Value": "hpc"},
                    ],
                },
                {
                    "FileSystemId": "fs-234",
                    "Tags": [{}],
                },
            ]
        },
        {
            "FileSystems": [
                {
                    "FileSystemId": "fs-123",
                    "Tags": [
                        {"Key": "HPC_Goal", "Value": "compute_cluster"},
                        {"key": "SBO_Billing", "Value": "hpc"},
                    ],
                },
                {
                    "FileSystemId": "fs-234",
                    "Tags": [{}],
                },
            ]
        },
    ],
)
def test_get_efs(filesystems):
    mock_efs_client = MagicMock()
    mock_efs_client.describe_file_systems.return_value = filesystems
    efs = get_efs(mock_efs_client)
    assert efs == filesystems["FileSystems"][0]["FileSystemId"]


@pytest.mark.parametrize(
    "filesystems",
    [
        {"FileSystems": []},
        {
            "FileSystems": [
                {
                    "FileSystemId": "fs-123",
                    "Tags": [{"Key": "HPC_Goal", "Value": "compute_cluster"}],
                },
                {
                    "FileSystemId": "fs-234",
                    "Tags": [{"Key": "HPC_Goal", "Value": "compute_cluster"}],
                },
            ]
        },
    ],
)
def test_get_efs_fails(filesystems):
    mock_efs_client = MagicMock()
    mock_efs_client.describe_file_systems.return_value = filesystems
    with pytest.raises(
        CouldNotDetermineEFSException,
        match=str([fs["FileSystemId"] for fs in filesystems["FileSystems"]]).replace("[", "\\["),
    ):
        get_efs(mock_efs_client)


@pytest.mark.parametrize(
    "security_groups",
    [
        {
            "SecurityGroups": [
                {"GroupId": "sg-1", "Tags": [{"Key": "HPC_Goal", "Value": "compute_cluster"}]},
            ]
        },
    ],
)
def test_get_security_group(security_groups):
    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_security_groups.return_value = security_groups
    security_group = get_security_group(mock_ec2_client)
    assert security_group == security_groups["SecurityGroups"][0]["GroupId"]


@pytest.mark.parametrize(
    "security_groups",
    [
        {"SecurityGroups": []},
        {
            "SecurityGroups": [
                {"GroupId": "sg-1", "Tags": [{"Key": "HPC_Goal", "Value": "compute_cluster"}]},
                {"GroupId": "sg-2", "Tags": [{"Key": "HPC_Goal", "Value": "compute_cluster"}]},
            ]
        },
    ],
)
def test_get_security_group_fails(security_groups):
    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_security_groups.return_value = security_groups
    with pytest.raises(
        CouldNotDetermineSecurityGroupException,
        match=str([sg["GroupId"] for sg in security_groups["SecurityGroups"]]).replace("[", "\\["),
    ):
        get_security_group(mock_ec2_client)


@patch("hpc_provisioner.aws_queries.free_subnet")
@pytest.mark.parametrize(
    "ec2_subnets,claimed_subnets,cluster_name",
    [
        ([{"SubnetId": "sub-1"}, {"SubnetId": "sub-2"}], {"sub-1": "cluster1"}, "cluster1"),
        (
            [{"SubnetId": "sub-1"}, {"SubnetId": "sub-2"}, {"SubnetId": "sub-3"}],
            {"sub-1": "cluster1", "sub-2": "cluster1"},
            "cluster1",
        ),
    ],
)
def test_claim_subnet_existing_claims(
    patched_free_subnet, ec2_subnets, claimed_subnets, cluster_name
):
    """
    1. One subnet was already claimed: nothing gets released, one gets returned
    2. Two subnets were already claimed: one gets released, one gets returned
    """
    mock_dynamodb_client = MagicMock()
    with patch("hpc_provisioner.aws_queries.get_registered_subnets") as mock_get_registered_subnets:
        mock_get_registered_subnets.return_value = claimed_subnets
        subnet = claim_subnet(mock_dynamodb_client, ec2_subnets, cluster_name)
        if len(claimed_subnets.keys()) == 1:
            patched_free_subnet.assert_not_called()
        else:
            assert patched_free_subnet.call_count == 1
        assert subnet == [*claimed_subnets][-1]


@patch("hpc_provisioner.aws_queries.free_subnet")
def test_all_ec2_subnets_are_registered(patched_free_subnet):
    ec2_subnets = [{"SubnetId": "sub-1"}, {"SubnetId": "sub-2"}]
    mock_dynamodb_client = MagicMock()
    with patch("hpc_provisioner.aws_queries.get_registered_subnets") as mock_get_registered_subnets:
        mock_get_registered_subnets.return_value = {"sub-1": "cluster1", "sub-2": "cluster2"}
        with pytest.raises(OutOfSubnetsException, match="All subnets are in use"):
            claim_subnet(mock_dynamodb_client, ec2_subnets, "cluster3")
        patched_free_subnet.assert_not_called()


@patch("hpc_provisioner.aws_queries.get_subnet", return_value={"sub-2": "cluster1"})
@patch("hpc_provisioner.aws_queries.free_subnet")
@patch("hpc_provisioner.aws_queries.logger")
def test_claim_subnet_claimed_between_list_and_register(
    patched_logger,
    patched_free_subnet,
    patched_get_subnet,
):
    """
    The subnet was not part of get_registered_subnets,
    but was claimed while we were checking the result of that call
    for existing claims for our cluster.
    """
    mock_dynamodb_client = MagicMock()
    ec2_subnets = [{"SubnetId": "sub-1"}, {"SubnetId": "sub-2"}]
    cluster_name = "cluster1"
    with patch("hpc_provisioner.aws_queries.get_registered_subnets") as mock_get_registered_subnets:
        mock_get_registered_subnets.return_value = {}
        with patch("hpc_provisioner.aws_queries.register_subnet") as mock_register_subnet:
            mock_register_subnet.side_effect = [SubnetAlreadyRegisteredException(), None]
            subnet = claim_subnet(mock_dynamodb_client, ec2_subnets, cluster_name)
    patched_free_subnet.assert_not_called()
    patched_logger.debug.assert_any_call("Subnet was registered just before us - continuing")
    patched_get_subnet.assert_called_once_with(mock_dynamodb_client, "sub-2")
    assert subnet == "sub-2"


@patch(
    "hpc_provisioner.aws_queries.get_subnet",
    side_effect=[{"sub-1": "cluster1"}, {"sub-2": "cluster2"}],
)
@patch("hpc_provisioner.aws_queries.free_subnet")
@patch("hpc_provisioner.aws_queries.logger")
def test_claim_subnet_claimed_between_register_and_write(
    patched_logger,
    patched_free_subnet,
    patched_get_subnet,
):
    """
    The subnet was not part of get_registered_subnets,
    but was registered at the same time as someone else (simultaneous writes).
    The other write won.
    """
    mock_dynamodb_client = MagicMock()
    ec2_subnets = [{"SubnetId": "sub-1"}, {"SubnetId": "sub-2"}]
    cluster_name = "cluster2"

    with patch("hpc_provisioner.aws_queries.get_registered_subnets") as mock_get_registered_subnets:
        mock_get_registered_subnets.return_value = {}
        with patch("hpc_provisioner.aws_queries.register_subnet") as mock_register_subnet:
            mock_register_subnet.return_value = None
            subnet = claim_subnet(mock_dynamodb_client, ec2_subnets, cluster_name)
    patched_free_subnet.assert_not_called()
    patched_logger.info.assert_any_call("Subnet sub-1 already claimed for cluster cluster1")
    first_get_subnet = call(mock_dynamodb_client, "sub-1")
    second_get_subnet = call(mock_dynamodb_client, "sub-2")
    patched_get_subnet.assert_has_calls([first_get_subnet, second_get_subnet])
    assert subnet == "sub-2"


@patch(
    "hpc_provisioner.aws_queries.get_subnet",
    return_value={"sub-1": "cluster1"},
)
@patch("hpc_provisioner.aws_queries.free_subnet")
@patch("hpc_provisioner.aws_queries.logger")
def test_claim_subnet_happy_path(
    patched_logger,
    patched_free_subnet,
    patched_get_subnet,
):
    """
    No weird behaviour, just claiming a subnet that nobody else is trying to claim.
    """

    mock_dynamodb_client = MagicMock()
    ec2_subnets = [{"SubnetId": "sub-1"}, {"SubnetId": "sub-2"}]
    cluster_name = "cluster1"

    with patch("hpc_provisioner.aws_queries.get_registered_subnets") as mock_get_registered_subnets:
        mock_get_registered_subnets.return_value = {}
        with patch("hpc_provisioner.aws_queries.register_subnet") as mock_register_subnet:
            mock_register_subnet.return_value = None
            subnet = claim_subnet(mock_dynamodb_client, ec2_subnets, cluster_name)
    patched_free_subnet.assert_not_called()
    patched_get_subnet.assert_called_once_with(mock_dynamodb_client, "sub-1")
    assert subnet == "sub-1"


def test_no_available_subnets():
    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_subnets.return_value = {"Subnets": []}
    with pytest.raises(OutOfSubnetsException):
        get_available_subnet(mock_ec2_client, "cluster1")


@patch("hpc_provisioner.aws_queries.dynamodb_client")
@patch("hpc_provisioner.aws_queries.claim_subnet", side_effect=OutOfSubnetsException())
@patch("hpc_provisioner.aws_queries.logger")
@patch("hpc_provisioner.aws_queries.time")
def test_out_of_subnets(mock_time, mock_logger, mock_claim_subnet, mock_dynamodb_client):
    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_subnets.return_value = {
        "Subnets": [{"SubnetId": "sub-1"}, {"SubnetId": "sub-2"}]
    }
    with pytest.raises(OutOfSubnetsException):
        get_available_subnet(mock_ec2_client, "cluster1")
    mock_logger.critical.assert_any_call(
        "All subnets are in use - either deploy more or remove some pclusters"
    )
    mock_time.sleep.assert_called_once_with(10)


@patch("hpc_provisioner.aws_queries.claim_subnet", return_value="sub-1")
@patch("hpc_provisioner.aws_queries.dynamodb_client")
def test_get_available_subnet(mock_dynamodb_client, mock_claim_subnet):
    ec2_subnets = {"Subnets": [{"SubnetId": "sub-1"}, {"SubnetId": "sub-2"}]}
    cluster_name = "cluster1"
    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_subnets.return_value = ec2_subnets
    subnet = get_available_subnet(mock_ec2_client, cluster_name)
    mock_claim_subnet.assert_called_once_with(
        mock_dynamodb_client(), ec2_subnets["Subnets"], cluster_name
    )
    assert subnet == "sub-1"


def test_create_keypair():
    mock_ec2_client = MagicMock()
    mock_ec2_client.describe_key_pairs.side_effect = ClientError(
        error_response={"Error": {"Code": 1, "Message": "It failed"}},
        operation_name="describe_key_pairs",
    )
    mock_ec2_client.create_key_pair.return_value = "key created"
    vlab_id = "test_vlab"
    project_id = "test_project"
    tags = [{"Key": "tagkey", "Value": "tagvalue"}]
    create_keypair(mock_ec2_client, vlab_id, project_id, tags)
    mock_ec2_client.create_key_pair.assert_called_once_with(
        KeyName=f"pcluster-{vlab_id}-{project_id}",
        TagSpecifications=[{"ResourceType": "key-pair", "Tags": tags}],
    )


def test_get_secret():
    secret_value = "supersecret"
    mock_sm_client = MagicMock()
    mock_sm_client.list_secrets.return_value = {"SecretList": [secret_value]}
    retrieved_secret = get_secret(mock_sm_client, "mysecret")
    assert retrieved_secret == secret_value


def test_get_secret_not_found():
    mock_sm_client = MagicMock()
    mock_sm_client.list_secrets.return_value = {}
    with pytest.raises(RuntimeError):
        get_secret(mock_sm_client, "mysecret")


def test_create_secret():
    mock_sm_client = MagicMock()
    vlab_id = "test_vlab"
    project_id = "test_project"
    secret_name = "mysecret"
    secret_value = "supersecret"
    create_secret(mock_sm_client, vlab_id, project_id, secret_name, secret_value)
    mock_sm_client.create_secret.assert_called_once_with(
        Name=secret_name,
        Description=f"SSH Key for cluster for vlab {vlab_id}, project {project_id}",
        SecretString=secret_value,
        Tags=[
            {"Key": VLAB_TAG_KEY, "Value": vlab_id},
            {"Key": PROJECT_TAG_KEY, "Value": project_id},
            {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
        ],
    )


@pytest.mark.parametrize("keypair_exists", [True, False])
@pytest.mark.parametrize("secret_exists", [True, False])
def test_store_private_key(keypair_exists, secret_exists):
    if secret_exists and not keypair_exists:
        pytest.skip(
            "New keypair with existing secret: sm_client.create_secret will raise "
            "on trying to create a secret that already exists."
        )
    mock_sm_client = MagicMock()
    vlab_id = "testvlab"
    project_id = "testproject"
    secret_name = key_name = f"pcluster-{vlab_id}-{project_id}"
    if not keypair_exists:
        ssh_keypair = {"KeyMaterial": "supersecret", "KeyName": key_name}
    else:
        ssh_keypair = {"KeyName": key_name}

    if not keypair_exists:
        if not secret_exists:
            print("Keypair created, secret does not exist yet")
            store_private_key(mock_sm_client, vlab_id, project_id, ssh_keypair)
            mock_sm_client.create_secret.assert_called_once_with(
                Name=secret_name,
                Description=f"SSH Key for cluster for vlab {vlab_id}, project {project_id}",
                SecretString=ssh_keypair["KeyMaterial"],
                Tags=[
                    {"Key": VLAB_TAG_KEY, "Value": vlab_id},
                    {"Key": PROJECT_TAG_KEY, "Value": project_id},
                    {"Key": BILLING_TAG_KEY, "Value": BILLING_TAG_VALUE},
                ],
            )
    elif secret_exists:
        print("Both already exist")
        mock_sm_client.list_secrets.return_value = {"SecretList": ["somesecret"]}
        retrieved_secret = store_private_key(mock_sm_client, vlab_id, project_id, ssh_keypair)
        assert retrieved_secret == "somesecret"
    else:
        print("Keypair already existed but was not stored in secretsmanager yet")
        mock_sm_client.list_secrets.return_value = {"SecretList": []}
        with pytest.raises(RuntimeError):
            store_private_key(mock_sm_client, vlab_id, project_id, ssh_keypair)
