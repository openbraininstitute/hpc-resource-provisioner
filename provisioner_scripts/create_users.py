#!/usr/bin/env python3

from io import TextIOWrapper
import json
import subprocess
import sys
from typing import Union


def run_cmd(
    cmd: str,
    msg_prefix: str,
    output_file: Union[int, TextIOWrapper] = subprocess.PIPE,
    exit_after_error: bool = True,
) -> None:
    """
    Run a command, exit after an error

    :param cmd: the command to run
    :param msg_prefix: log message prefix
    :param output_file: where to direct stdout. stderr always goes to subprocess.PIPE
    :param exit_after_error: whether to die on errors or not
    """
    try:
        subprocess.run(
            cmd.split(" "), stdout=output_file, stderr=subprocess.PIPE, check=True
        )
    except subprocess.CalledProcessError as ret:
        error_msg = ret.stderr.decode().replace("\n", "")
        print(f'{msg_prefix} failed:\n\t"{error_msg}"')
        if exit_after_error:
            exit(ret.returncode)
    print(f"{msg_prefix} succeeded.")


# Helper method to create a directory for a given user
def create_directory(prefix: str, user: str, group: str) -> None:
    """
    Create a directory for a given user (/{prefix}/scratch/{user})

    :param prefix: under which path the user directory should be created
    :param user: the username
    :param group: group to which the directory should belong
    """
    path = f"{prefix}/scratch/{user}"

    # Create folder with correct permissions and set ownership
    run_cmd(f"mkdir -m 755 -p {path}", f"Creation of Lustre path for '{user}'")
    run_cmd(
        f"chown {user}:{group} {path}",
        f"Setting Lustre path permissions for '{user}' at '{path}'",
    )


# Helper method to create a user and configure sudo permissions
def create_user(name: str, uid: int, group: str, shell: str, sudo: bool) -> None:
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
        f"useradd -d /sbo/home/{name} -M -s {shell} -u {uid} -U {name} -G {group}",
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


def main(argv):
    if len(argv) < 2 or len(argv) > 3:
        print(
            "Please, supply user database and/or Lustre FSx mount point, if required."
        )
        exit(1)

    user_filename = argv[1]
    fsx_path = argv[2] if len(argv) == 3 else None
    group = {"id": 2000, "name": "obi"}

    # First, configure the OBI group for the users
    run_cmd(
        f"groupadd -g {group['id']} {group['name']}",
        f"Group '{group['name']}' creation",
    )

    # Create users within the OBI group and configure Lustre FSx 'scratch' directory, if required
    with open(user_filename, "r") as f:
        users = json.load(f)
    for user in users:
        create_user(
            user["name"], user["uid"], group["name"], user["shell"], user["sudo"]
        )
        if fsx_path is not None:
            create_directory(fsx_path, user["name"], group["name"])

    # Configure the SLURM directory and set global permissions of Lustre FSx, if required
    if fsx_path is not None:
        create_directory(fsx_path, "slurm", "slurm")
        run_cmd(
            f"chmod 755 {fsx_path} {fsx_path}/scratch",
            f"Setting Lustre path permissions for '{fsx_path}'",
        )


if __name__ == "__main__":
    main(sys.argv)
