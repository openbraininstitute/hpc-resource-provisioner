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
    print(f"Run: {cmd}")
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


# Helper method to create a user and configure sudo permissions
def create_user(name: str, public_ssh_key: str, sudo: bool = False) -> None:
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
            f"chmod 600 /home/{name}/ssh/authorized_keys",
            f"Set permissions on authorized_keys file for {name}",
        )
    run_cmd(
        f"chown -R {name}:{name} /home/{name}/.ssh",
        f"Set ownership for {name} .ssh dir",
    )


def main(argv):
    if len(argv) != 2:
        print("No users to create - exiting")
        exit(0)

    group = {"id": 2000, "name": "obi"}

    # First, configure the OBI group for the users
    run_cmd(
        f"groupadd -g {group['id']} {group['name']}",
        f"Group '{group['name']}' creation",
    )

    # Create users within the OBI group and configure Lustre FSx 'scratch' directory, if required
    print("Loading users")
    users = json.loads(argv[1])
    print(f"Users: {users}")
    for user in users:
        print(f"Creating user {user}")
        create_user(user["name"], user["public_key"], user.get("sudo", False))


if __name__ == "__main__":
    main(sys.argv)
