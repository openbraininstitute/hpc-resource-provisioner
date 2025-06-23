"""This script creates/Update a Grafana dashboard JSON model for monitoring AWS ParallelCluster and FSx performance metrics.
Example usage:
python grafana_dashboard.py create --clustername pcluster-weji-2025-06-17-14h03 --fsid fs-049aa0c3151500962 --tstart 2025-06-17T14:03Z --output dashboard.json
python grafana_dashboard.py update --input dashboard.json --tend 2025-06-17T16:03Z
"""

from dataclasses import dataclass, asdict
import argparse
import json

from typing import Optional

CLW_UID = "fep83zm6l8074d"


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
    type: Optional[int] = "timeseries"


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
        return d


def create_dashboard(
    data_source, cluster_name: str, fsid: str, tstart: str, tend: str
) -> GrafanaDashboard:
    panel_mem = Panel(
        title="mem_used_percent",
        datasource=data_source,
        gridPos=GridPosition(h=8, w=12, x=0, y=0),
        id=1,
        targets=[
            Target(
                dimensions={"ClusterName": cluster_name},
                metricName="mem_used_percent",
                namespace="CustomMetrics_test",
                statistic="Average",
            )
        ],
    )
    panel_cpu = Panel(
        title="cpu_usage_active",
        datasource=data_source,
        gridPos=GridPosition(h=8, w=12, x=0, y=8),
        id=2,
        targets=[
            Target(
                dimensions={"ClusterName": cluster_name, "cpu": "cpu-total"},
                metricName="cpu_usage_active",
                namespace="CustomMetrics_test",
                statistic="Average",
            )
        ],
    )
    panel_fsx_write = Panel(
        title="FSX/DataWriteBytes",
        datasource=data_source,
        gridPos=GridPosition(h=8, w=12, x=0, y=16),
        id=3,
        targets=[
            Target(
                dimensions={"FileSystemId": fsid},
                metricName="DataWriteBytes",
                namespace="AWS/FSx",
                statistic="Sum",
            )
        ],
    )
    panel_fsx_read = Panel(
        title="FSX/DataWriteBytes",
        datasource=data_source,
        gridPos=GridPosition(h=8, w=12, x=0, y=24),
        id=4,
        targets=[
            Target(
                dimensions={"FileSystemId": fsid},
                metricName="DataWriteBytes",
                namespace="AWS/FSx",
                statistic="Sum",
            )
        ],
    )
    dashboard = GrafanaDashboard(
        tags=["benchmark"],
        panels=[panel_mem, panel_cpu, panel_fsx_write, panel_fsx_read],
        time=TimeRange(tstart, tend),
        timezone="browser",
        title=cluster_name,
        version=1,
    )
    return dashboard


def dump_json_model(dashboard: GrafanaDashboard, filename: str):
    with open(filename, "w") as f:
        json.dump(dashboard.to_dict(), f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Manage a Grafana dashboard JSON model for monitoring AWS ParallelCluster and FSx performance metrics."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create subcommand
    create_parser = subparsers.add_parser(
        "create", help="Create a new dashboard JSON model"
    )
    create_parser.add_argument(
        "--clustername", required=True, help="The name of the current parallel cluster"
    )
    create_parser.add_argument(
        "--fsid",
        required=True,
        help="The FileSystemID for the FSx associated with the cluster",
    )
    create_parser.add_argument(
        "--tstart", required=True, help="Start time for the dashboard (ISO format)"
    )
    create_parser.add_argument("--output", required=True, help="Output JSON model file")

    # Update subcommand
    update_parser = subparsers.add_parser(
        "update", help="Update an existing dashboard JSON model"
    )
    update_parser.add_argument(
        "--input", required=True, help="The input JSON model file to update"
    )
    update_parser.add_argument(
        "--tend",
        required=True,
        help="New end time for the dashboard, in ISO format (e.g., 2025-06-17T14:03Z)",
    )
    args = parser.parse_args()

    if args.command == "create":
        # Example values for testing
        # cluster_name = "pcluster-weji-2025-06-17-14h03"
        # fs_id = "fs-049aa0c3151500962"
        # tstart = "2025-06-17-14:03Z"
        cloudwatch_source = DataSource(type="cloudwatch", uid=CLW_UID)
        dashboard = create_dashboard(
            data_source=cloudwatch_source,
            cluster_name=args.clustername,
            fsid=args.fsid,
            tstart=args.tstart,
            tend="now",
        )
        dump_json_model(dashboard, args.output)
    elif args.command == "update":
        # Example values for testing
        # tend = "2025-06-17-16:03Z"
        with open(args.input, "r") as f:
            dashboard_data = json.load(f)
        dashboard_data["time"]["to"] = args.tend
        with open(args.input, "w") as f:
            json.dump(dashboard_data, f, indent=2)


if __name__ == "__main__":
    main()
