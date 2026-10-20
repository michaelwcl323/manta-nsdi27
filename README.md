# Manta

This branch contains the Manta implementation and its standalone benchmark
tools. The steps below use only the `manta` branch. All Fabric commands are run
from the repository's `benchmark/` directory.

## 1. Install the environment

Use Ubuntu with Bash, Python, Rust, and the native build tools below. The checked-in
`benchmark/requirements.txt` pins older packages, including Matplotlib 3.3.4;
Ubuntu 20.04 with Python 3.8 provides a compatible environment for these exact
requirements. The CloudLab installer also runs `pip3 install -r requirements.txt`
on each replica, so use the same Python environment on the replicas. Newer Python
versions require updating the legacy package pins before using that installer.

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential ca-certificates clang cmake curl git iproute2 \
  libclang-dev pkg-config python3 python3-pip python3-venv tmux

curl https://sh.rustup.rs -sSf | sh -s -- -y
source "$HOME/.cargo/env"
rustup default stable

git clone --branch manta --single-branch \
  https://github.com/michaelwcl323/manta-nsdi27.git
cd manta-nsdi27

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r benchmark/requirements.txt

cd benchmark
fab --list
```

For subsequent shells, activate `.venv` and enter `benchmark/` before running
Fabric commands. The first benchmark builds the Rust binaries in release mode
with the `benchmark` feature enabled.

## 2. Run locally

```bash
fab local
```

This starts a local committee, generates keys and configuration files, runs the
clients, and prints a performance summary containing `Consensus TPS`,
`Consensus latency`, `End-to-end TPS`, and `End-to-end latency`.

Edit `bench_params` and `node_params` inside `local()` in
[`benchmark/fabfile.py`](benchmark/fabfile.py) to change the experiment. Its
current benchmark defaults are:

```python
bench_params = {
    'faults': 0,
    'nodes': 10,
    'workers': 1,
    'rate_type': 'balanced',
    'rate': 80000,
    'tx_size': 512,
    'duration': 20,
}
```

`rate` is the total offered transaction rate, divided among clients. The
`sigma`, `kappa`, `reference`, and `coverage` fields are in `node_params`.
The local and CloudLab tasks have separate parameter dictionaries; update the
task you intend to run.

## 3. Run on CloudLab

### Allocate machines and configure SSH

Allocate the machines through the CloudLab web portal. By default,
`cloudlab_remote()` uses ten replica hosts. Run the Fabric commands from a
separate control machine that can reach every replica. The control machine can
be another CloudLab node; omit it from the replica list in the settings below.

The replica hosts must have passwordless `sudo`, Bash, internet access for
installation and Git, and network connectivity to one another. The control
machine needs the environment from Section 1 and an RSA private key accepted
by every replica. The current benchmark key loader expects an RSA key.

Check access to a replica, replacing the key, username, and address:

```bash
ssh -i /absolute/path/to/cloudlab_rsa YOUR_CLOUDLAB_USER@10.10.1.1
```

Use addresses reachable from both the control machine and the other replicas.
For an isolated CloudLab LAN, the example below uses private LAN addresses.

### Create `benchmark/cloudlab_settings.json`

While in `benchmark/`, create a file named `cloudlab_settings.json`:

```json
{
  "key": {
    "path": "/absolute/path/to/cloudlab_rsa"
  },
  "port": 5000,
  "repo": {
    "name": "manta-nsdi27",
    "url": "https://github.com/michaelwcl323/manta-nsdi27.git",
    "branch": "manta"
  },
  "hosts": [
    {"hostname": "10.10.1.1", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.2", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.3", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.4", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.5", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.6", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.7", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.8", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.9", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"},
    {"hostname": "10.10.1.10", "username": "YOUR_CLOUDLAB_USER", "port": 22, "region": "lan"}
  ]
}
```

Replace the private-key path, usernames, and addresses. `repo.name` is the
repository directory under each replica user's home directory. Keep
`repo.branch` set to `manta`. Top-level `port` is the benchmark's base port;
each host's `port` is its SSH port. Allow benchmark TCP traffic between replicas
on ports 5000–7000 for the default ten-node, one-worker configuration.

For an encrypted RSA key, set `SSH_KEY_PASSWORD` in the control shell. It can
be entered without displaying or placing the passphrase in shell history:

```bash
read -rsp 'SSH key passphrase: ' SSH_KEY_PASSWORD
export SSH_KEY_PASSWORD
echo
```

List the configured hosts and test their SSH connections:

```bash
fab cloudlab-info
fab cloudlab-test
```

### Initialize the `manta` checkout on every replica

The existing `cloudlab_install()` task clones the repository without a branch
argument. Initialize the replicas explicitly on `manta` first so installation
finds the correct `benchmark/requirements.txt`. Run this from `benchmark/` on
the control machine:

```bash
python - <<'PY'
import json
import os
import shlex

from fabric import Connection

with open("cloudlab_settings.json") as handle:
    settings = json.load(handle)

repo = settings["repo"]
name = shlex.quote(repo["name"])
url = shlex.quote(repo["url"])
branch = shlex.quote(repo["branch"])

for host in settings["hosts"]:
    kwargs = {"key_filename": settings["key"]["path"]}
    if os.environ.get("SSH_KEY_PASSWORD"):
        kwargs["passphrase"] = os.environ["SSH_KEY_PASSWORD"]
    with Connection(
        host["hostname"],
        user=host["username"],
        port=host.get("port", 22),
        connect_kwargs=kwargs,
    ) as connection:
        connection.run(
            'cd "$HOME" && '
            'sudo apt-get update && sudo apt-get install -y git curl && '
            f'if [ ! -d {name}/.git ]; then '
            f'git clone --branch {branch} --single-branch {url} {name}; '
            f'else cd {name} && git fetch origin {branch} && '
            f'git checkout {branch} && git pull --ff-only origin {branch}; fi'
        )
PY
```

### Install with `cloudlab_install`

```bash
fab cloudlab-install
```

This invokes `cloudlab_install()` in `benchmark/fabfile.py`. Fabric exposes
underscores in Python task names as hyphens on the command line. The task
installs Rust and build dependencies, updates the replica checkouts, and
installs their Python dependencies. Check that every configured host is reached;
the installer can skip hosts whose SSH connection fails.

### Configure and run the benchmark

Edit `bench_params` inside `cloudlab_remote()` in `benchmark/fabfile.py` on the
control machine. For a short first run, use:

```python
bench_params = {
    'faults': 0,
    'nodes': [10],
    'workers': 1,
    'collocate': True,
    'rate_type': 'balanced',
    'rate': [80000],
    'tx_size': 512,
    'duration': 20,
    'runs': 1,
}
```

The checked-in task instead sweeps seven rates from 40,000 to 140,000 tx/s,
with two 120-second runs at each rate. Provide at least as many replica hosts
as the largest `nodes` value.

For a LAN run, clear any previously configured emulated WAN delay, then start:

```bash
fab cloudlab-wan --action=clear
fab cloudlab-remote \
  --sigma=2 --kappa=2 --reference=4 --coverage=7 \
  --design-tag=manta --network-tag=lan --load-tag=balanced
```

`cloudlab-remote` checks out `repo.branch`, builds the benchmark binaries on the
replicas, uploads the committee configuration, runs the workload, and downloads
the results. `network-tag` labels the result directory; network emulation is
controlled separately by `cloudlab-wan`. Change `node_params` or the available
command-line flags to configure the protocol:

```bash
fab --help cloudlab-remote
```

Inspect or stop a remote run:

```bash
fab cloudlab-status
fab cloudlab-debug
fab cloudlab-kill
```

## 4. Read the results

Run outputs are saved under `benchmark/manta_result/` on the control machine.
CloudLab runs use the `design-tag`, `network-tag`, and `load-tag` hierarchy.
The file `benchmark/manta_result/.latest_run` records the latest run directory.
From `benchmark/`:

```bash
cat manta_result/.latest_run
cat "$(cat manta_result/.latest_run)/summary.txt"
```

Each run includes `summary.txt`, `latency.csv`, `run_metadata.json`, and `logs/`.
The summary reports consensus and end-to-end throughput and latency. Remote
performance measurements require the requested number of replicas to be
running successfully and a workload appropriate for the allocated machines.
