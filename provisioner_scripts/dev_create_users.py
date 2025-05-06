#!/usr/bin/env python3
import os
import time

from argparse import ArgumentParser
from io import TextIOWrapper
import json
import subprocess
import sys
from typing import List, Optional, Union


TIMEOUT = 900


def run_cmd(
    cmd: str,
    msg_prefix: str,
    output_file: Union[int, TextIOWrapper] = subprocess.PIPE,
    exit_after_error: bool = True,
) -> Optional[bytes]:
    """
    Run a command, exit after an error

    :param cmd: the command to run
    :param msg_prefix: log message prefix
    :param output_file: where to direct stdout. stderr always goes to subprocess.PIPE
    :param exit_after_error: whether to die on errors or not
    """
    print(f"Run: {cmd}")
    try:
        result = subprocess.run(
            cmd.split(" "), stdout=output_file, stderr=subprocess.PIPE, check=True
        )
        if output_file == subprocess.PIPE:
            return result.stdout
    except subprocess.CalledProcessError as ret:
        error_msg = ret.stderr.decode().replace("\n", "")
        print(f'{msg_prefix} failed:\n\t"{error_msg}"')
        if exit_after_error:
            exit(ret.returncode)
    print(f"{msg_prefix} succeeded.")


def wait_for_dra(vlab_id: str, project_id: str) -> None:
    timed_out = time.time() + 14400
    while time.time() < timed_out:
        output = run_cmd(
            "aws fsx describe-data-repository-associations", "Getting DRA status"
        )
        associations = json.loads(output)
        for association in associations["Associations"][::-1]:
            keep = False
            for tag in association["Tags"]:
                if (
                    tag["Key"] == "parallelcluster:cluster-name"
                    and tag["Value"] == f"pcluster-{vlab_id}-{project_id}"
                ):
                    keep = True

            if keep is False:
                associations["Associations"].remove(association)
        if len(associations["Associations"]) == 3:
            print("All DRAs found!")
            if any(
                association["Lifecycle"] == "FAILED"
                for association in associations["Associations"]
            ):
                raise RuntimeError(f"DRA failure: {associations}")
            elif all(
                association["Lifecycle"] == "AVAILABLE"
                for association in associations["Associations"]
            ):
                print("All DRA's available")
                return
            else:
                print(
                    f"All DRAs present, but not all in final state yet: {[association['Lifecycle'] for association in associations['Associations']]}"
                )
        else:
            print("Not all associations found yet - waiting")
        time.sleep(60)
    print("Timed out waiting for DRAs to become available")
    raise TimeoutError("Timed out waiting for DRAs to become available")


# Helper method to create a user and configure sudo permissions
def create_user(
    vlab_id: str,
    project_id: str,
    name: str,
    public_ssh_key: str,
    sudo: bool = False,
    folder_ownership: List[Optional[str]] = [],
) -> None:
    """
    Create a user and configure sudo permissions, if necessary

    :param name: username
    :param uid: uid to give the user
    :param group: main group for the user
    :param shell: which shell to give the user
    :param sudo: whether to give sudo permissions
    """
    # Create the user with the provided group and shell
    run_cmd(
        # TODO: homedir not created
        f"useradd -m -U {name} -G obi",
        f"User '{name}' creation",
    )

    # Configure sudo permissions accordingly
    sudoers_file = f"/etc/sudoers.d/{name}"
    if sudo:
        run_cmd(
            f"echo -n {name} ALL = NOPASSWD: ALL",
            f"Enabling sudo configuration for '{name}'",
            open(sudoers_file, "w"),
        )
    else:
        run_cmd(f"rm -f {sudoers_file}", f"Disabling sudo configuration for '{name}'")

    # Set the SSH key
    run_cmd(f"mkdir /home/{name}/.ssh", f"Make .ssh dir for {name}")
    run_cmd(f"chmod 700 /home/{name}/.ssh", f"Set permissions on .ssh dir for {name}")
    if public_ssh_key:
        with open(f"/home/{name}/.ssh/authorized_keys", "w") as fp:
            fp.write(public_ssh_key)
        run_cmd(
            f"chmod 600 /home/{name}/.ssh/authorized_keys",
            f"Set permissions on authorized_keys file for {name}",
        )
    run_cmd(
        f"chown -R {name}:{name} /home/{name}/.ssh",
        f"Set ownership for {name} .ssh dir",
    )
    timeout = time.time() + TIMEOUT

    wait_for_dra(vlab_id, project_id)

    for folder in folder_ownership:
        if not os.path.exists(folder):
            raise RuntimeError(f"Path {folder} does not exist")
        run_cmd(
            f"sudo setfacl -Rm d:u:{name}:rwX,u:{name}:rwX {folder}",
            f"setfacl on {folder} for {name}",
        )


def main(argv):
    parser = ArgumentParser()
    parser.add_argument("--users", help="Users to create")
    parser.add_argument("--vlab-id", required=True, help="Vlab ID")
    parser.add_argument("--project-id", required=True, help="Project ID")
    args = parser.parse_args()

    if not args.users:
        print("No users to create - exiting")
        exit(0)
    print("Loading users")
    users = json.loads(args.users)

    group = {"id": 2000, "name": "obi"}

    # First, configure the OBI group for the users
    run_cmd(
        f"groupadd -g {group['id']} {group['name']}",
        f"Group '{group['name']}' creation",
    )

    # Create users within the OBI group and configure Lustre FSx 'scratch' directory, if required
    print(f"Users: {users}")
    for user in users:
        print(f"Creating user {user}")
        create_user(
            args.vlab_id,
            args.project_id,
            user["name"],
            user["public_key"],
            user.get("sudo", False),
            user.get("folder_ownership", []),
        )


if __name__ == "__main__":
    main(sys.argv)
