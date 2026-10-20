#!/usr/bin/env python3
"""Draw Fig C latency and throughput from the archived per-configuration means.

Adapted from new_experiment2/new0903/plot_fig_c.py. The original draw function
is retained; inputs and outputs are explicit so no sibling checkout is needed.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import numpy as np

from plot_style import FONTSIZE, finish_figure, make_figure

PAIRS = [(1, 2), (1, 4), (2, 2), (2, 4), (4, 1), (4, 2)]
COVERAGES = [7, 10]
COLORS = {7: "#1b9e77", 10: "#7570b3"}


def load_means(path: Path) -> list[dict]:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ("sigma", "kappa", "reference", "coverage"):
            row[key] = int(row[key])
    return rows


def draw(means, metric):
    field = "mean_consensus_latency_ms" if metric == "latency" else "mean_consensus_tps"
    values = {(r["sigma"], r["kappa"], r["coverage"]): float(r[field]) / 1000 for r in means}
    pairs = [pair for pair in PAIRS if any((*pair, c) in values for c in COVERAGES)]
    fig, ax = make_figure()
    x = np.arange(len(pairs), dtype=float)
    width = 0.32
    for i, coverage in enumerate(COVERAGES):
        ax.bar(
            x + (i - 0.5) * width,
            [values.get((*pair, coverage), np.nan) for pair in pairs],
            width=width * 0.92, color=COLORS[coverage], edgecolor="black",
            linewidth=1.2, label=rf"$cov={coverage}$", zorder=3,
        )
    # Separate groups of equal sigma without annotations above the axes.
    for i in range(1, len(pairs)):
        if pairs[i][0] != pairs[i - 1][0]:
            ax.axvline(i - 0.5, color="0.75", linewidth=1.6, linestyle="--", zorder=2)
    ax.set_xlabel(r"$(\sigma,\kappa)$", fontsize=FONTSIZE)
    ax.set_xticks(x, [rf"$({s},{k})$" for s, k in pairs], fontsize=FONTSIZE * 0.72)
    ax.set_ylabel("Latency (s)" if metric == "latency" else "Throughput (KTps)", fontsize=FONTSIZE)
    lo, hi = min(values.values()), max(values.values())
    if metric == "latency":
        ax.set_ylim(0, hi * 1.15)
    else:
        pad = max(0.08 * (hi - lo), 2)
        ax.set_ylim(max(0, lo - pad), hi + max(0.25 * (hi - lo), 3))
    ax.set_axisbelow(True)
    return fig, ax


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--means-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--network", choices=("geo", "lan"), required=True)
    args = parser.parse_args()
    means = load_means(args.means_csv)
    for metric in ("latency", "tps"):
        fig, ax = draw(means, metric)
        output = args.output_dir / f"fig_c_{args.network}_{metric}_vs_sigma_kappa_by_cov.pdf"
        for path in finish_figure(
            fig, ax, output, also_png=True,
            legend_kwargs={"fontsize": 24, "loc": "best"},
        ):
            print(path)


if __name__ == "__main__":
    main()
