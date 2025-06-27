"""This script creates/Update a Grafana dashboard JSON model for monitoring AWS ParallelCluster and FSx performance metrics.
Example usage:
python grafana_dashboard.py create --clustername pcluster-weji-2025-06-17-14h03 --fsid fs-049aa0c3151500962 --tstart 2025-06-17T14:03Z
python grafana_dashboard.py update --title pcluster-weji-2025-06-17-14h03 --tend 2025-06-17T16:03Z
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import argparse
import json
import requests
import os

from typing import Optional

CLW_UID = "fep83zm6l8074d"
GRAFANA_URL = os.getenv("GRAFANA_SERVER")
API_KEY = os.getenv("GRAFANA_API_KEY")
assert GRAFANA_URL is not None, "GRAFANA_SERVER environment variable is not set"
assert API_KEY is not None, "GRAFANA_API_KEY environment variable is not set"


@dataclass
class TimeRange:
    tstart: str
    tend: str

    def to_dict(self):
        return {"from": self.tstart, "to": self.tend}


@dataclass
class DataSource:
    type: str
    uid: str


@dataclass
class GridPosition:
    h: int
    w: int
    x: int
    y: int


@dataclass
class Target:
    namespace: str
    metricName: str
    dimensions: dict[str, str]
    statistic: str
    period: Optional[str] = "60"
    region: Optional[str] = "default"
    matchExact: Optional[bool] = False
    metricEditorMod: Optional[int] = 0  # Builder/Code
    metricQueryType: Optional[int] = 0  # Metrics/Logs/Traces
    queryMode: Optional[str] = "Metrics"


@dataclass
class Panel:
    datasource: DataSource
    gridPos: GridPosition
    id: int
    targets: list[Target]
    title: str
    unit: Optional[str] = ""
    type: Optional[int] = "timeseries"

    def to_dict(self):
        d = asdict(self)
        # replace unit key with fieldConfig if unit is present, otherwise remove it
        unit_value = d.pop("unit", "")
        if unit_value:
            d["fieldConfig"] = {"defaults": {"unit": unit_value}}
        return d


@dataclass
class GrafanaDashboard:
    tags: list[str]
    panels: list[Panel]
    time: TimeRange
    timezone: str
    title: str
    version: int
    editable: Optional[bool] = True
    refresh: Optional[str] = ""
    id: Optional[str] = None
    uid: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        d["time"] = self.time.to_dict()
        d["panels"] = [panel.to_dict() for panel in self.panels]
        return d


def create_dashboard(
    data_source, cluster_name: str, fsid: str, tstart: str, tend: str
) -> GrafanaDashboard:
    panel_cpu = Panel(
        title="cpu_usage_active",
        datasource=data_source,
        gridPos=GridPosition(h=8, w=12, x=0, y=0),
        id=1,
        targets=[
            Target(
                dimensions={"ClusterName": cluster_name, "cpu": "cpu-total"},
                metricName="cpu_usage_active",
                namespace="CustomMetrics_test",
                statistic="Average",
            )
        ],
        unit="percent",
    )
    panel_mem = Panel(
        title="mem_used_percent",
        datasource=data_source,
        gridPos=GridPosition(h=8, w=12, x=12, y=0),
        id=2,
        targets=[
            Target(
                dimensions={"ClusterName": cluster_name},
                metricName="mem_used_percent",
                namespace="CustomMetrics_test",
                statistic="Average",
            )
        ],
        unit="percent",
    )
    panel_fsx_io = Panel(
        title="FSx Data Read/Write",
        datasource=data_source,
        gridPos=GridPosition(h=8, w=12, x=0, y=8),
        id=3,
        targets=[
            Target(
                dimensions={"FileSystemId": fsid},
                metricName="DataWriteBytes",
                namespace="AWS/FSx",
                statistic="Sum",
            ),
            Target(
                dimensions={"FileSystemId": fsid},
                metricName="DataReadBytes",
                namespace="AWS/FSx",
                statistic="Sum",
            ),
        ],
        unit="bytes",
    )
    dashboard = GrafanaDashboard(
        tags=["benchmark"],
        panels=[panel_mem, panel_cpu, panel_fsx_io],
        time=TimeRange(tstart, tend),
        timezone="browser",
        title=cluster_name,
        version=1,
    )
    return dashboard


def get_uid(base_url, api_key, title):
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(f"{base_url}/api/search?query={title}", headers=headers)
    resp.raise_for_status()
    for dashboard in resp.json():
        if dashboard.get("title") == title and dashboard.get("type") == "dash-db":
            return dashboard["uid"]
    return None


def get_json_model(base_url, api_key, title):
    uid = get_uid(base_url, api_key, title)
    assert uid is not None, f"Dashboard with title {title} not found"
    # Fetch the dashboard JSON model using the UID
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(f"{base_url}/api/dashboards/uid/{uid}", headers=headers)
    resp.raise_for_status()
    return resp.json()["dashboard"]


def update_endtime(json_model, tend):
    json_model["time"]["to"] = tend


def push_to_grafana(content: dict, base_url, api_key):
    """
    Push a dashboard JSON model to Grafana, either create or update.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"dashboard": content, "folderId": 0, "overwrite": True}
    payload_str = json.dumps(payload)
    r = requests.post(
        f"{base_url}/api/dashboards/db", data=payload_str, headers=headers
    )
    r.raise_for_status()
    print(f"Dashboard pushed successfully: {r.json().get('slug', 'unknown')}")


def validate_iso8601(dt_str):
    """Validate ISO 8601 format like 2025-06-17T14:03Z."""
    try:
        datetime.strptime(dt_str, "%Y-%m-%dT%H:%MZ")
        return True
    except ValueError:
        return False


def current_datetime_utc_iso8601():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def main():
    parser = argparse.ArgumentParser(
        description="Manage a Grafana dashboard for monitoring AWS ParallelCluster and FSx performance metrics."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create subcommand
    create_parser = subparsers.add_parser(
        "create", help="Create a new Grafana dashboard"
    )
    create_parser.add_argument(
        "--clustername", required=True, help="Name of the parallel cluster"
    )
    create_parser.add_argument(
        "--fsid",
        required=True,
        help="FileSystemID of the FSx associated with the cluster",
    )
    create_parser.add_argument(
        "--tstart",
        default="",
        help="Start (UTC) time for the dashboard, in ISO format (e.g., 2025-06-17T14:03Z), default is the current timestamp",
    )

    # Update subcommand
    update_parser = subparsers.add_parser(
        "update", help="Update the end time of an existing Grafana dashboard"
    )
    update_parser.add_argument(
        "--title", required=True, help="Title of the dashboard to update"
    )
    update_parser.add_argument(
        "--tend",
        default="",
        help="New end (UTC) time for the dashboard, in ISO format (e.g., 2025-06-17T14:03Z), default is the current timestamp",
    )

    args = parser.parse_args()

    if args.command == "create":
        # Example values for testing
        # cluster_name = "pcluster-weji-2025-06-17-14h03"
        # fs_id = "fs-049aa0c3151500962"
        # tstart = "2025-06-17T14:03Z"
        tstart = args.tstart or current_datetime_utc_iso8601()
        if not validate_iso8601(tstart):
            raise ValueError(
                f"tstart {tstart} is not in ISO format (YYYY-MM-DDTHH:MMZ)"
            )
        cloudwatch_source = DataSource(type="cloudwatch", uid=CLW_UID)
        dashboard = create_dashboard(
            data_source=cloudwatch_source,
            cluster_name=args.clustername,
            fsid=args.fsid,
            tstart=tstart,
            tend="now",
        )
        push_to_grafana(
            content=dashboard.to_dict(), base_url=GRAFANA_URL, api_key=API_KEY
        )
        print(f"Create dashboard {dashboard.title} successfully from {tstart} to now")
    elif args.command == "update":
        # Example values for testing
        # title = "pcluster-weji-2025-06-17-14h03"
        # tend = "2025-06-17T16:03Z"
        tend = args.tend or current_datetime_utc_iso8601()
        if not validate_iso8601(tend):
            raise ValueError(f"tend {tend} is not in ISO format (YYYY-MM-DDTHH:MMZ)")
        json_model = get_json_model(GRAFANA_URL, API_KEY, args.title)
        update_endtime(json_model, tend)
        push_to_grafana(content=json_model, base_url=GRAFANA_URL, api_key=API_KEY)
        print(f"Update endtime of dashboard {args.title} successfully to {tend}")
    else:
        raise NotImplementedError(f"Command {args.command} not implemented")


if __name__ == "__main__":
    main()
