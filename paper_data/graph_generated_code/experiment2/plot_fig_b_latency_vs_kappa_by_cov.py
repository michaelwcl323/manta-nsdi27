#!/usr/bin/env python3
"""Figure (b): grouped bar chart of latency vs coverage, by kappa.

Fixed: sigma=1, coverage == reference.
X: cov in {2, 4, 7, 10}. Bars: kappa in {2, 4, 5} side-by-side. Y: Latency (s).
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42

from plot_style import FONTSIZE, finish_figure, make_figure


SIGMA = 1
COVERAGES = [2, 4, 7, 10]
KAPPAS = {2, 4, 5}
SERIES_SPEC = [
    # (kappa, label, color)
    (2, r"$\kappa=2$", "#1b9e77"),
    (4, r"$\kappa=4$", "#7570b3"),
    (5, r"$\kappa=5$", "#d95f02"),
]


def load_means_from_export(means_csv: Path) -> dict[tuple[int, int], float]:
    means: dict[tuple[int, int], float] = {}
    with means_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (int(row["coverage"]), int(row["kappa"]))
            means[key] = float(row["mean_consensus_latency_s"])
    if not means:
        raise SystemExit(f"no fig-b rows in {means_csv}")
    return means


def load_means(summary_csv: Path) -> dict[tuple[int, int], float]:
    """Mean latency (s) keyed by (coverage, kappa); requires cov == ref, sigma=1."""
    grouped: dict[tuple[int, int], list[float]] = defaultdict(list)
    with summary_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["sigma"]) != SIGMA:
                continue
            cov = int(row["coverage"])
            ref = int(row["reference"])
            if cov != ref:
                continue
            kappa = int(row["kappa"])
            if cov not in COVERAGES or kappa not in KAPPAS:
                continue
            key = (cov, kappa)
            grouped[key].append(float(row["consensus_latency_ms"]) / 1000.0)
    if not grouped:
        raise SystemExit(f"no fig-b rows in {summary_csv}")
    return {k: sum(v) / len(v) for k, v in grouped.items()}


def draw(means: dict[tuple[int, int], float], output_path: Path, *, also_png: bool = False):
    fig, ax = make_figure()

    n_groups = len(COVERAGES)
    n_series = len(SERIES_SPEC)
    x = np.arange(n_groups, dtype=float)
    width = 0.22
    offsets = (np.arange(n_series) - (n_series - 1) / 2.0) * width

    for i, (kappa, label, color) in enumerate(SERIES_SPEC):
        heights = []
        for cov in COVERAGES:
            key = (cov, kappa)
            heights.append(means[key] if key in means else np.nan)
        ax.bar(
            x + offsets[i],
            heights,
            width=width * 0.92,
            color=color,
            edgecolor="black",
            linewidth=1.2,
            label=label,
            zorder=3,
        )

    ax.set_xlabel(r"Coverage $cov$", fontsize=FONTSIZE)
    ax.set_ylabel("Latency (s)", fontsize=FONTSIZE)
    ax.set_xticks(x)
    ax.set_xticklabels([str(c) for c in COVERAGES])
    finite = []
    for cov in COVERAGES:
        for kappa, _, _ in SERIES_SPEC:
            v = means.get((cov, kappa), np.nan)
            if np.isfinite(v):
                finite.append(v)
    ymax = 2.25
    if finite and max(finite) > 2.25:
        ymax = max(finite) * 1.05
    ax.set_ylim(0.0, ymax)
    if ymax == 2.25:
        yticks = [0.0, 0.5, 1.0, 1.5, 2.0]
    else:
        # Lan (taller): integer steps, shown with one decimal.
        yticks = list(np.arange(0.0, ymax + 1e-9, 1.0))
        if yticks and abs(yticks[-1] - ymax) < 1e-9:
            yticks = yticks[:-1]  # no label on the top spine
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{t:.1f}" for t in yticks])
    ax.set_axisbelow(True)

    # Prefer upper-left; if a tall bar would sit under that corner, put legend mid-plot.
    legend_loc = "upper left"
    if finite and max(finite) > 1.7:
        legend_loc = "upper center"

    return finish_figure(
        fig,
        ax,
        output_path,
        also_png=also_png,
        legend_kwargs={"loc": legend_loc, "fontsize": 26.0},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", type=Path)
    parser.add_argument("--means-csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--also-png",
        action="store_true",
        help="Also write a PNG alongside the PDF.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.means_csv is not None:
        means_path = args.means_csv.resolve()
        if not means_path.exists() or means_path.stat().st_size == 0:
            print(f"[skip] no fig-b means at {means_path}")
            return
        with means_path.open(newline="", encoding="utf-8") as f:
            if not list(csv.DictReader(f)):
                print(f"[skip] empty fig-b means at {means_path}")
                return
        means = load_means_from_export(means_path)
    elif args.summary_csv is not None:
        try:
            means = load_means(args.summary_csv.resolve())
        except SystemExit as exc:
            print(f"[skip] {exc}")
            return
    else:
        raise SystemExit("provide --means-csv or --summary-csv")
    output = args.output.resolve()
    for path in draw(means, output, also_png=args.also_png):
        print(path)


if __name__ == "__main__":
    main()
