#!/usr/bin/env python3
"""Drive Figure 10c on the CloudLab controller via ``fab cloudlab-remote``.

This mirrors the manual one-cell-at-a-time workflow (no orchestrator matrix merge,
no CloudLabBench wrapper from experiment_reproduced). The laptop only SSHs to the
controller; each cell is a plain Fabric task with the same knobs as fabfile.py.

After all cells finish, by default this script extracts ``send_samples.csv``, syncs
``Figure10c/{k2-ref4,…}/``, and draws the AE send-time cumulative-mean overlay under
``results/regenerate_graphs/``. Pass ``--skip-plot`` to disable.

Usage (repo root):

  # clear netem once, then run the four 10c cells (+ auto plot)
  python experiment_reproduced/experiment2/run_figure10c_fab.py

  # skip WAN clear (assume already nodelay)
  python experiment_reproduced/experiment2/run_figure10c_fab.py --skip-wan-clear

  # only one cell
  python experiment_reproduced/experiment2/run_figure10c_fab.py --only k2c7
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS = REPO_ROOT / "cloudlab_settings.json"
DEFAULT_BUILD = REPO_ROOT / "build"
DEFAULT_PLOT_DIR = REPO_ROOT / "results" / "regenerate_graphs"
PLOT_SCRIPT = (
    REPO_ROOT / "paper_data" / "graph_generated_code" / "experiment2" / "plot_attack_latency_timeseries.py"
)
LOCAL_FIG10C = REPO_ROOT / "experiment_reproduced" / "experiment2" / "results" / "Figure10c"
FIGURE10C_ORDER = ["k2-c4", "k2-c7", "k3-c7", "k3-c10"]
CELL_TO_LABEL = {
    "k2c4": "k2-ref4",
    "k2c7": "k2-ref7",
    "k3c7": "k3-ref7",
    "k3c10": "k3-ref10",
}

# Default order matches the usual 10c sweep (weakest coverage first).
DEFAULT_CELLS = (
    {"name": "k2c4", "kappa": 2, "reference": 4, "coverage": 4},
    {"name": "k2c7", "kappa": 2, "reference": 7, "coverage": 7},
    {"name": "k3c7", "kappa": 3, "reference": 7, "coverage": 7},
    {"name": "k3c10", "kappa": 3, "reference": 10, "coverage": 10},
)


def nested(settings: dict, *keys, default=None):
    value = settings
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def load_settings(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("cloudlab", data)


def default_key(settings: dict) -> Path:
    explicit = nested(settings, "key", "private") or nested(settings, "key", "path")
    if explicit:
        return Path(str(explicit)).expanduser()
    pubkey = nested(settings, "key", "pubkey")
    if pubkey and str(pubkey).endswith(".pub"):
        return Path(str(pubkey)[:-4]).expanduser()
    return Path("~/.ssh/id_rsa").expanduser()


def default_username(settings: dict) -> str:
    hosts = settings.get("hosts") or []
    if hosts and isinstance(hosts[0], dict) and hosts[0].get("username"):
        return str(hosts[0]["username"])
    return "ubuntu"


def read_controller(build_dir: Path) -> str:
    path = build_dir / "controller"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    nodes = build_dir / "nodes"
    if not nodes.exists():
        raise SystemExit("missing build/controller (and build/nodes)")
    lines = [ln.strip() for ln in nodes.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise SystemExit("build/nodes is empty")
    return lines[-1]


def ssh_base(username: str, controller: str, key: Path, connect_timeout: int) -> list[str]:
    return [
        "ssh",
        "-A",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={connect_timeout}",
        "-o",
        "IdentitiesOnly=yes",
        "-i",
        str(key),
        f"{username}@{controller}",
    ]


def remote_bash(ssh: list[str], script: str) -> int:
    """Run ``script`` on the controller inside one remote shell command.

    SSH joins argv with spaces, so ``ssh host bash -lc cd /path && fab`` only
    makes ``bash -c`` see ``cd`` (then fab runs from ``$HOME`` and cannot find
    fabfile). Pass a single remote string instead.
    """
    print(f"[fab10c] remote:\n{script}", flush=True)
    remote = f"bash -lc {shlex.quote(script)}"
    return subprocess.run([*ssh, remote], check=False).returncode


def fab_args(cell: dict, *, design_tag: str, network_tag: str) -> str:
    """Build a Fabric 2 CLI invocation (flags, not legacy key=value)."""
    parts = [
        "fab",
        "cloudlab-remote",
        "--debug",
        f"--sigma={cell.get('sigma', 1)}",
        f"--kappa={cell['kappa']}",
        f"--reference={cell['reference']}",
        f"--coverage={cell['coverage']}",
        # Booleans that default False in fabfile: omit (=False).
        # Booleans with --[no-]* that we want True:
        "--attack-enabled",
        "--attack-limit-certificates",
        f"--attack-start-secs=60",
        f"--attack-duration-secs=1000",
        f"--attack-group-size=5",
        # --attack-limit-headers omitted => False
        # --enable-* / --allow-* / --solid-* omitted => False
        f"--fast-coin-candidate-threshold=0",
        f"--solid-candidate-threshold=0",
        f"--adaptive-intermediate-spill-trigger-digests=2",
        f"--adaptive-intermediate-spill-cap-digests=1",
        f"--load-tag={cell['name']}",
        f"--design-tag={design_tag}",
        f"--network-tag={network_tag}",
    ]
    return " ".join(shlex.quote(p) if " " in p else p for p in parts)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Figure 10c via remote fab cloudlab-remote")
    p.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    p.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    p.add_argument("--connect-timeout", type=int, default=20)
    p.add_argument(
        "--repo-dir",
        default="/users/michael9/manta-nsdi27",
        help="Absolute protocol repo path on the controller",
    )
    p.add_argument(
        "--design-tag",
        default="fig10c_fab",
        help="Passed through to fab; only affects result directory naming",
    )
    p.add_argument(
        "--network-tag",
        default="nodelay",
        help="Label for result dirs (does not change tc). Default nodelay after clear.",
    )
    p.add_argument(
        "--skip-wan-clear",
        action="store_true",
        help="Do not run fab cloudlab-wan action=clear before cells",
    )
    p.add_argument(
        "--kill-between",
        action="store_true",
        help="Run fab cloudlab-kill between cells",
    )
    p.add_argument(
        "--only",
        action="append",
        default=None,
        help="Run only these cells (k2c4/k2c7/k3c7/k3c10); repeatable",
    )
    p.add_argument(
        "--order",
        default="k2c4,k2c7,k3c7,k3c10",
        help="Comma-separated cell order (default: k2c4,k2c7,k3c7,k3c10)",
    )
    p.add_argument(
        "--skip-plot",
        action="store_true",
        help="Do not sync send_samples / plot the AE Figure 10c overlay after cells finish",
    )
    p.add_argument(
        "--plot-output-dir",
        type=Path,
        default=DEFAULT_PLOT_DIR,
        help=f"Where to write the overlay PDF/PNG (default: {DEFAULT_PLOT_DIR})",
    )
    return p.parse_args()


def sync_and_plot_figure10c(
    *,
    ssh: list[str],
    username: str,
    controller: str,
    key: Path,
    repo: str,
    design_tag: str,
    network_tag: str,
    cells: list[str],
    plot_output_dir: Path,
) -> int:
    """Extract send_samples on the controller, sync locally, draw send-time overlay."""
    result_root = f"{repo}/benchmark/manta_result/{design_tag}/{network_tag}"
    remote_export = "/tmp/fig10c_fab_ae_export"
    mapping = {name: CELL_TO_LABEL[name] for name in cells if name in CELL_TO_LABEL}
    if len(mapping) < 2:
        print("[fab10c] skip plot: need at least 2 cells with labels", flush=True)
        return 0

    mapping_json = json.dumps(mapping)
    extract_script = f"""
set -euo pipefail
python3 - <<'PY'
import csv, json, re, shutil
from datetime import datetime
from pathlib import Path

_RE_WORKER = re.compile(r"worker-(\\d+)-(\\d+)\\.log$")
_RE_CLIENT = re.compile(r"client-(\\d+)-(\\d+)\\.log$")
_RE_BATCH = re.compile(r"Batch ([^ ]+) contains sample tx (\\d+)")
_RE_SAMPLE = re.compile(r"\\[([^\\s\\]]+Z) .* sample transaction (\\d+)")

def posix_utc(stamp: str) -> float:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()

def extract(run_dir: Path, dest: Path) -> int:
    logs = run_dir / "logs"
    batch_by_sample = {{}}
    if logs.is_dir():
        for path in sorted(logs.glob("worker-*-*.log")):
            name = _RE_WORKER.search(path.name)
            if not name:
                continue
            node, worker = int(name.group(1)), int(name.group(2))
            with path.open(errors="replace") as handle:
                for line in handle:
                    m = _RE_BATCH.search(line)
                    if m:
                        batch_by_sample[(node, worker, int(m.group(2)))] = m.group(1)
    latency_by_batch = {{}}
    with (run_dir / "latency.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("metric") != "consensus_latency":
                continue
            bid, lms = row.get("identifier") or "", row.get("latency_ms")
            if bid and lms:
                latency_by_batch[bid] = float(lms) / 1000.0
    samples, seen = [], set()
    for path in sorted(logs.glob("client-*-*.log")):
        name = _RE_CLIENT.search(path.name)
        if not name:
            continue
        node, worker = int(name.group(1)), int(name.group(2))
        with path.open(errors="replace") as handle:
            for line in handle:
                m = _RE_SAMPLE.search(line)
                if not m:
                    continue
                key = (node, worker, int(m.group(2)))
                if key in seen:
                    continue
                bid = batch_by_sample.get(key)
                lat = latency_by_batch.get(bid or "")
                if bid is None or lat is None:
                    continue
                seen.add(key)
                samples.append((posix_utc(m.group(1)), bid, lat))
    samples.sort()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["send_ts", "batch_id", "latency_s"])
        w.writerows(samples)
    return len(samples)

root = Path({result_root!r})
out = Path({remote_export!r})
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
mapping = json.loads({mapping_json!r})
for load, label in mapping.items():
    runs = sorted((root / load).glob("20*"), key=lambda p: p.name)
    if not runs:
        print(f"{{label}}: NO RUN under {{root / load}}")
        continue
    src = runs[-1]
    dest = out / label
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "latency.csv", dest / "latency.csv")
    meta = src / "run_metadata.json"
    if meta.is_file():
        shutil.copy2(meta, dest / "run_metadata.json")
    n = extract(src, dest / "send_samples.csv")
    print(f"{{label}}: n_send={{n}} from {{src.name}}")
PY
"""
    print("[fab10c] extract send_samples on controller ...", flush=True)
    rc = remote_bash(ssh, extract_script)
    if rc != 0:
        print(f"[fab10c] extract failed rc={rc}", flush=True)
        return rc

    LOCAL_FIG10C.mkdir(parents=True, exist_ok=True)
    for label in mapping.values():
        local_label = LOCAL_FIG10C / label
        local_label.mkdir(parents=True, exist_ok=True)
        for fname in ("latency.csv", "run_metadata.json", "send_samples.csv"):
            cmd = [
                "scp",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "IdentitiesOnly=yes",
                "-i",
                str(key),
                f"{username}@{controller}:{remote_export}/{label}/{fname}",
                str(local_label / fname),
            ]
            src_rc = subprocess.run(cmd, check=False).returncode
            if src_rc != 0 and fname != "run_metadata.json":
                print(f"[fab10c] scp failed for {label}/{fname} rc={src_rc}", flush=True)
                return src_rc
        print(f"[fab10c] synced {local_label}", flush=True)

    run_dirs = [
        LOCAL_FIG10C / CELL_TO_LABEL[name]
        for name in cells
        if name in CELL_TO_LABEL and (LOCAL_FIG10C / CELL_TO_LABEL[name] / "latency.csv").is_file()
    ]
    if len(run_dirs) < 2:
        print("[fab10c] skip plot: fewer than 2 local run dirs with latency.csv", flush=True)
        return 0
    if not PLOT_SCRIPT.is_file():
        print(f"[fab10c] skip plot: missing {PLOT_SCRIPT}", flush=True)
        return 0

    plot_output_dir.mkdir(parents=True, exist_ok=True)
    out_pdf = plot_output_dir / "attack_latency_timeseries_overlay_mean_send_time.pdf"
    merge = "--merge-four-runs" if len(run_dirs) == 4 else "--merge-runs"
    cmd = [
        sys.executable,
        str(PLOT_SCRIPT),
        merge,
        *[str(p) for p in run_dirs],
        "--order",
        ",".join(FIGURE10C_ORDER),
        "--output",
        str(out_pdf),
    ]
    print("[fab10c] plot:", " ".join(cmd), flush=True)
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(PLOT_SCRIPT.parent)
        + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    )
    rc = subprocess.run(cmd, check=False, env=env).returncode
    if rc != 0:
        print(f"[fab10c] plot failed rc={rc}", flush=True)
        return rc
    for src_name, dst_name in (
        ("attack_latency_timeseries_overlay_mean_send_time.pdf", "attack_latency_timeseries_overlay_mean.pdf"),
        ("attack_latency_timeseries_overlay_mean_send_time.png", "attack_latency_timeseries_overlay_mean.png"),
    ):
        src = plot_output_dir / src_name
        if src.is_file():
            shutil.copy2(src, plot_output_dir / dst_name)
    print(f"[fab10c] wrote {out_pdf}", flush=True)
    return 0


def main() -> int:
    args = parse_args()
    settings = load_settings(args.settings)
    key = default_key(settings)
    username = default_username(settings)
    controller = read_controller(args.build_dir)
    password = settings.get("ssh_key_password")
    if password:
        sys.path.insert(0, str(REPO_ROOT))
        from cloudlab.deploy_environment import ensure_ssh_agent

        ensure_ssh_agent(key, password)

    by_name = {c["name"]: c for c in DEFAULT_CELLS}
    order = [x.strip() for x in args.order.split(",") if x.strip()]
    if args.only:
        order = [x for x in order if x in set(args.only)]
        missing = set(args.only) - set(order)
        if missing:
            raise SystemExit(f"unknown --only cells: {sorted(missing)}")
    for name in order:
        if name not in by_name:
            raise SystemExit(f"unknown cell in --order: {name}")

    ssh = ssh_base(username, controller, key, args.connect_timeout)
    repo = args.repo_dir.rstrip("/")
    bench = f"{repo}/benchmark"
    # Absolute path + quoted cd so login-shell / ssh joining cannot drop the path.
    cd_bench = f"cd {shlex.quote(bench)}"

    print(f"[fab10c] controller={controller} user={username}", flush=True)
    print(f"[fab10c] bench={bench}", flush=True)
    print(f"[fab10c] cells={order} design_tag={args.design_tag} network_tag={args.network_tag}", flush=True)

    # Sanity: must see fabfile on the controller before starting cells.
    rc = remote_bash(ssh, f"{cd_bench} && pwd && test -f fabfile.py && echo FABFILE_OK")
    if rc != 0:
        print("[fab10c] controller bench dir / fabfile.py check failed", flush=True)
        return rc

    # Figure 10c fab path always uses experiment2_attack (not experiment2).
    rc = remote_bash(
        ssh,
        f"cd {shlex.quote(repo)} && "
        "git fetch origin experiment2_attack && "
        "git checkout experiment2_attack && "
        "git pull --ff-only origin experiment2_attack && "
        "git rev-parse --abbrev-ref HEAD && git log -1 --oneline",
    )
    if rc != 0:
        print("[fab10c] failed to checkout experiment2_attack on controller", flush=True)
        return rc

    if not args.skip_wan_clear:
        rc = remote_bash(
            ssh,
            f"{cd_bench} && fab cloudlab-wan --action=clear",
        )
        if rc != 0:
            return rc

    for i, name in enumerate(order, 1):
        cell = by_name[name]
        print(f"[fab10c] ========== {i}/{len(order)} {name} ==========", flush=True)
        if args.kill_between and i > 1:
            remote_bash(ssh, f"{cd_bench} && fab cloudlab-kill")
        cmd = fab_args(cell, design_tag=args.design_tag, network_tag=args.network_tag)
        rc = remote_bash(ssh, f"{cd_bench} && {cmd}")
        if rc != 0:
            print(f"[fab10c] FAILED {name} rc={rc}", flush=True)
            return rc
        print(f"[fab10c] DONE {name}", flush=True)

    print(
        f"[fab10c] all done; results under "
        f"{repo}/benchmark/manta_result/{args.design_tag}/{args.network_tag}/",
        flush=True,
    )
    if not args.skip_plot:
        plot_rc = sync_and_plot_figure10c(
            ssh=ssh,
            username=username,
            controller=controller,
            key=key,
            repo=repo,
            design_tag=args.design_tag,
            network_tag=args.network_tag,
            cells=order,
            plot_output_dir=args.plot_output_dir,
        )
        if plot_rc != 0:
            return plot_rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
