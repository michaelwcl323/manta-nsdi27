"""Shared helpers for latency plots (time-axis alignment with benchmark logs)."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.logs import parse_primary_log_markers


def resolve_primary_start_ts(run_dir: Path, fallback_min_proposal_ts: float) -> float:
    """
    Unix timestamp for t=0 on the x-axis: earliest primary boot from primary-0.log
    if available, else ``fallback_min_proposal_ts`` (typically min Created time in CSV).
    Matches latency export when boot is used as primary_start.
    """
    log = run_dir / "logs" / "primary-0.log"
    if log.exists():
        markers = parse_primary_log_markers(log)
        boot = markers.get("boot_ts")
        if boot is not None:
            return float(boot)
    metadata = run_dir / "run_metadata.json"
    if metadata.is_file():
        timing = json.loads(metadata.read_text()).get("derived_timing", {})
        for key in ("primary0_boot_ts", "primary_boot_ts"):
            if timing.get(key) is not None:
                return float(timing[key])
    return float(fallback_min_proposal_ts)
