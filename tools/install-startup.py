"""Install the workstation-local systemd user unit after bootstrapping."""

import os
from pathlib import Path
import shutil
import subprocess

BASE = Path(__file__).resolve().parents[1]
PYTHON = BASE / ".venv/bin/python"
UNIT = "weazlops-startup.service"


def quote(value):
    value = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + value.replace("%", "%%").replace("$", "$$") + '"'


def main():
    docker = shutil.which("docker")
    if not docker or not PYTHON.is_file() or not (BASE / ".runtime/private/worker.token").is_file():
        raise SystemExit("Set up Docker, the adapter venv and private station files first. See README.md.")
    env = {**os.environ, "WZL_UID": str(os.getuid()), "WZL_GID": str(os.getgid())}
    subprocess.run([docker, "compose", "build"], cwd=BASE, env=env, check=True)
    systemd = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd/user"
    systemd.mkdir(parents=True, exist_ok=True)
    path = systemd / UNIT
    staged = path.with_suffix(".new")
    staged.write_text(
        "[Unit]\nDescription=Start WeazlOps and its local USB adapter\n\n"
        "[Service]\nType=oneshot\nRemainAfterExit=yes\nRestart=on-failure\nRestartSec=10\n"
        f"WorkingDirectory={quote(BASE)}\nEnvironment=WZL_UID={os.getuid()} WZL_GID={os.getgid()}\n"
        f"ExecStart={quote(docker)} compose up --detach --no-build --wait --wait-timeout 60\n"
        f"ExecStart={quote(PYTHON)} tools/start_adapter.py --ensure-running\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    staged.replace(path)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", UNIT], check=True)
    subprocess.run(["systemctl", "--user", "restart", UNIT], check=True)


if __name__ == "__main__":
    main()
