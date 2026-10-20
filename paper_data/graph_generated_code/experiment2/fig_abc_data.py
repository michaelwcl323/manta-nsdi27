"""Read original experiment runs and write derived tables outside original_data."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path


PARAMETERS = ("sigma", "kappa", "reference", "coverage")


def load_original_runs(directory: Path, excluded_names=()) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("*/*/summary.txt")):
        if path.parent.name in excluded_names:
            continue
        text = path.read_text()
        metadata = json.loads(path.with_name("run_metadata.json").read_text())

        def number(label: str) -> int:
            match = re.search(rf"^\s*{re.escape(label)}:\s*([\d,]+)", text, re.M)
            if match is None:
                raise ValueError(f"Missing {label}: {path}")
            return int(match[1].replace(",", ""))

        row = {key: number(key.capitalize()) for key in PARAMETERS}
        for key in PARAMETERS:
            if row[key] != metadata["node_params"][key]:
                raise ValueError(f"Metadata disagrees with summary ({key}): {path}")
        no_commits = "no committed vertices were observed" in text
        row.update(
            input_rate=number("Input rate"),
            run=metadata["bench_params"]["run"],
            consensus_tps=number("Consensus TPS"),
            consensus_latency_ms=None if no_commits else number("Consensus latency"),
            source=path.relative_to(directory).as_posix(),
        )
        if row["input_rate"] != metadata["bench_params"]["rate"]:
            raise ValueError(f"Metadata disagrees with input rate: {path}")
        rows.append(row)
    if not rows:
        raise ValueError(f"No original run summaries found in {directory}")
    return rows


def load_exported_runs(path: Path) -> list[dict]:
    """Fallback for Fig B, whose original logs/summaries have not been located."""
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"No exported runs found in {path}")
    for row in rows:
        for key in (*PARAMETERS, "input_rate", "run"):
            row[key] = int(row[key])
        for key in ("consensus_tps", "consensus_latency_ms"):
            row[key] = float(row[key])
    return rows


def aggregate_runs(rows: list[dict], *, keep_lowest: int | None = None,
                   round_seconds: bool = False) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in PARAMETERS)].append(row)
    means = []
    for key, runs in sorted(grouped.items()):
        if keep_lowest is not None:
            runs = sorted(runs, key=lambda row: row["consensus_latency_ms"])[:keep_lowest]
        latencies = [row["consensus_latency_ms"] for row in runs
                     if row["consensus_latency_ms"] is not None]
        tps = sum(row["consensus_tps"] for row in runs) / len(runs)
        latency = sum(latencies) / len(latencies) if latencies else float("nan")
        latency_s = latency / 1000
        if round_seconds:
            # The archived Fig B panels used exported values rounded to 1 ms.
            latency_s = float(f"{latency_s:.3f}")
        means.append(dict(
            zip(PARAMETERS, key),
            n_runs=len(runs),
            mean_consensus_tps=tps,
            mean_consensus_latency_ms=latency,
            mean_consensus_tps_ktps=tps / 1000,
            mean_consensus_latency_s=latency_s,
        ))
    return means


def write_tables(directory: Path, figure: str, rows: list[dict], means: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for suffix, records in (("runs", rows), ("means", means)):
        path = directory / f"fig_{figure}_{suffix}.csv"
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
