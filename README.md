# WeazlOps

![WeazlOps browser capture of a synthetic mixed handoff](https://github.com/bprendie/weazlops/releases/download/v0.5.0-dev19/mixed-team-handoff.png)

*WeazlOps browser capture of a synthetic mixed handoff.*

One USB cable. A whole team. WeazlOps loads the plan, checks each unit's
handoff, and puts your desk back in service when the crew returns.

The station stays on your machine. It runs a local web app plus a native
USB adapter for [WeazlGhost and XL](https://github.com/bprendie/weazlghost)
and [GhostDrop](https://github.com/bprendie/ghostdrop).

## Set up the station

Use Linux with Docker Compose, Python 3.12+, and serial access for your user.
Connect devices directly by USB. Open ordinary browser tabs against the local
station.

1. Clone this project and create the adapter environment.

   ```sh
   git clone https://github.com/bprendie/weazlops.git
   cd weazlops
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-adapter.txt
   ```

2. Make an owner-only bootstrap file and choose a unique password of at least
   12 characters. The password prompt keeps it out of your shell history.

   ```sh
   .venv/bin/python - <<'PY'
   import getpass, json, os
   from pathlib import Path
   os.umask(0o077)
   path = Path(".private/admin-bootstrap.json")
   path.parent.mkdir(exist_ok=True)
   password = getpass.getpass("Choose a WeazlOps admin password: ")
   if len(password) < 12:
       raise SystemExit("Choose at least 12 characters.")
   with path.open("x") as stream:
       json.dump({"username": "admin", "password": password}, stream)
   PY
   .venv/bin/python tools/bootstrap.py
   ```

3. Install the login service on a systemd workstation.

   ```sh
   .venv/bin/python tools/install-startup.py
   ```

   Open [WeazlOps on this computer](http://127.0.0.1:5005) and sign in.
   The web app listens on loopback 5005. The token-authenticated adapter uses
   loopback 5015. Back up `.runtime/data` together with `.runtime/private`.

## Put a team on the wire

Download the paired ZIP for each model from its hardware repo. In
**Devices → Firmware library**, choose **Add firmware**. The station validates
each chip's own manifest and images. Flashing requires a separate confirmation.
Use **Prepare a team** to make a plan and hand out devices over USB.

See the [operator guide](OPERATOR-GUIDE.txt) for the complete workflow.

## Test locally

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
bash tools/check.sh
```
