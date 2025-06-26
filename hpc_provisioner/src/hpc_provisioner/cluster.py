import copy
from json import JSONEncoder
from typing import Optional

BOOL_VALUES = ["benchmark", "dev", "include_lustre", "provisioning_launched"]


class ClusterJSONEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__


class Cluster:
    benchmark: bool
    dev: bool
    include_lustre: bool
    project_id: str
    sim_pubkey: Optional[str]
    admin_ssh_key_name: Optional[str]
    tier: str
    vlab_id: str
    provisioning_launched: bool
    creation_time: int

    def __init__(
        self,
        project_id: str,
        vlab_id: str,
        creation_time: int,
        tier: str = "debug",
        benchmark: bool = False,
        dev: bool = False,
        include_lustre: bool = True,
        sim_pubkey: Optional[str] = None,
        admin_ssh_key_name: Optional[str] = None,
        provisioning_launched: bool = False,
    ):
        self.benchmark = benchmark
        self.dev = dev
        self.include_lustre = include_lustre
        self.project_id = project_id
        self.tier = tier
        self.vlab_id = vlab_id
        self.sim_pubkey = sim_pubkey
        if admin_ssh_key_name:
            self.admin_ssh_key_name = admin_ssh_key_name
        else:
            self.admin_ssh_key_name = self.name
        self.provisioning_launched = provisioning_launched
        self.creation_time = creation_time

    @property
    def name(self):
        return f"pcluster-{self.vlab_id}-{self.project_id}"

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return (
            f"Cluster {self.name}; "
            f"tier: {self.tier}, benchmark: {self.benchmark}, "
            f"dev: {self.dev}, include_lustre: {self.include_lustre}, "
            f"admin_ssh_key_name: {self.admin_ssh_key_name} "
            f"sim_pubkey: {self.sim_pubkey}"
        )

    @staticmethod
    def from_dict(cluster_data: dict):
        if "name" in cluster_data:
            cluster_data.pop("name")
        return Cluster(**cluster_data)

    def as_dict(self) -> dict:
        d = copy.deepcopy(self.__dict__)
        d["name"] = self.name
        return d

    @staticmethod
    def from_dynamo_dict(cluster_data: dict):
        """
        Create the Cluster based on a dict retrieved from dynamodb,
        which means converting the boolean values back from 1 and 0 to True and False
        """
        for bool_value in BOOL_VALUES:
            cluster_data[bool_value] = True if cluster_data[bool_value] == 1 else False

        return Cluster.from_dict(cluster_data)

    def as_dynamo_dict(self) -> dict:
        """
        Return a dict where all booleans have been replaced with 1 (True) or 0 (False)
        This way we can create GSIs for them in dynamo if necessary
        """
        d = self.as_dict()
        for bool_value in BOOL_VALUES:
            d[bool_value] = 1 if d[bool_value] else 0

        return d

    def __eq__(self, other) -> bool:
        compare_props = ["benchmark", "dev", "include_lustre", "project_id", "tier", "vlab_id"]
        for prop in compare_props:
            if getattr(self, prop) != getattr(other, prop):
                print(f"{prop}: {getattr(self, prop)} != {getattr(other, prop)}")
                return False
        return True
