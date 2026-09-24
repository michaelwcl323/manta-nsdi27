#!/usr/bin/env python3
"""Plot latency for the requested (sigma, kappa) pairs at coverage 7 and 10."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt

from paper_figure_save import savefig_tight_target_aspect


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_SUMMARY = REPO_ROOT / "paper_data" / "original_data" / "Figure10a_10b" / "consensus_summary.csv"
DEFAULT_OUTPUT = REPO_ROOT / "results" / "regenerate_graphs" / "coverage_impact_by_sigma_kappa.pdf"

REFERENCE = 4
COVERAGES = [7, 10]
PAIRS = [(1, 4), (2, 2), (4, 1), (1, 2), (4, 2), (2, 4)]
STYLES = {
    7: (r"$cov=7$", "#1b9e77", "-", "o"),
    10: (r"$cov=10$", "#7570b3", "--", "s"),
}


def load_means(
    summary_csv: Path,
    *,
    network: str,
) -> dict[tuple[int, int, int, int], float]:
    if not summary_csv.is_file():
        raise SystemExit(f"missing summary csv: {summary_csv}")
    grouped: dict[tuple[int, int, int, int], list[float]] = defaultdict(list)
    with summary_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if str(row.get("network") or "geo") != network:
                continue
            key = (
                int(row["sigma"]),
                int(row["kappa"]),
                int(row["reference"]),
                int(row.get("coverage") or 7),
            )
            grouped[key].append(float(row["consensus_latency_ms"]) / 1000.0)
    return {key: sum(values) / len(values) for key, values in grouped.items()}


def draw(
    means: dict[tuple[int, int, int, int], float],
    output: Path,
    *,
    allow_partial: bool,
) -> None:
    fig, ax = plt.subplots(figsize=(13.2, 8.8), dpi=180)
    missing: list[tuple[int, int, int, int]] = []
    plotted = 0
    for coverage in COVERAGES:
        label, color, linestyle, marker = STYLES[coverage]
        xs: list[int] = []
        ys: list[float] = []
        for index, (sigma, kappa) in enumerate(PAIRS):
            key = (sigma, kappa, REFERENCE, coverage)
            if key not in means:
                missing.append(key)
                continue
            xs.append(index)
            ys.append(means[key])
        if ys:
            plotted += 1
            ax.plot(
                xs,
                ys,
                label=label,
                color=color,
                linestyle=linestyle,
                marker=marker,
                linewidth=4.6,
                markersize=11,
                markeredgewidth=1.4,
            )

    if missing and not allow_partial:
        raise SystemExit(f"missing requested coverage-comparison cells: {missing}")
    if not plotted:
        raise SystemExit("no requested coverage-comparison cells found")
    if missing:
        print(f"[warn] plotting a partial coverage grid; missing cells: {missing}")

    ax.set_xlabel(r"$(\sigma,\kappa)$", fontsize=34)
    ax.set_ylabel("Latency (s)", fontsize=34)
    ax.set_xticks(range(len(PAIRS)), [f"({sigma},{kappa})" for sigma, kappa in PAIRS])
    ax.tick_params(axis="both", labelsize=28, width=2.2)
    for spine in ax.spines.values():
        spine.set_linewidth(2.2)
    ax.grid(True, linestyle=(0, (1, 2)), linewidth=1.25, color="0.78")
    ax.legend(fontsize=27, frameon=True, loc="best")
    ax.margins(x=0.06, y=0.12)
    ax.set_box_aspect(1 / 1.5)

    output.parent.mkdir(parents=True, exist_ok=True)
    savefig_tight_target_aspect(fig, output, 1.5, pad_inches=0.03, dpi=180)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--network", choices=["geo", "lan"], default="geo")
    parser.add_argument(
        "--auto-limits",
        action="store_true",
        help="Allow an incomplete grid while a resumable campaign is in progress.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    draw(
        load_means(args.summary_csv.resolve(), network=args.network),
        args.output.resolve(),
        allow_partial=args.auto_limits,
    )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
