#!/usr/bin/env python3
"""Figure (a): mean consensus latency vs reference, by sigma.

Fixed: kappa=2, coverage=7. Curves: sigma in {1..6}. X: ref in {2,4,7,10}.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42

from dataset_config import select_lowest_latency_runs
from plot_style import finish_figure, make_figure, plot_series


REFERENCES = [2, 4, 7, 10]
KAPPA = 2
COVERAGE = 7
SERIES_SPEC = [
    (1, r"$\sigma=1$", "#1b9e77", "-"),
    (2, r"$\sigma=2$", "#7570b3", "--"),
    (3, r"$\sigma=3$", "#d95f02", "-."),
    (4, r"$\sigma=4$", "#e7298a", ":"),
    (5, r"$\sigma=5$", "#66a61e", (0, (5, 1))),
    (6, r"$\sigma=6$", "#a6761d", (0, (1, 1))),
]


def load_means_from_export(means_csv: Path) -> dict[tuple[int, int], float]:
    """Use curated fig_a_means.csv (respects exclusions / original averaging)."""
    means: dict[tuple[int, int], float] = {}
    with means_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["kappa"]) != KAPPA or int(row["coverage"]) != COVERAGE:
                continue
            key = (int(row["sigma"]), int(row["reference"]))
            means[key] = float(row["mean_consensus_latency_s"])
    if not means:
        raise SystemExit(f"no fig-a rows in {means_csv}")
    return means


def load_means(summary_csv: Path) -> dict[tuple[int, int], float]:
    """Mean latency (s) keyed by (sigma, reference), filtered to kappa/cov."""
    grouped: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    with summary_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["kappa"]) != KAPPA or int(row["coverage"]) != COVERAGE:
                continue
            if float(row["consensus_tps"]) <= 0 or float(row["consensus_latency_ms"]) <= 0:
                continue
            key = (int(row["sigma"]), int(row["reference"]))
            grouped[key].append(row)
    if not grouped:
        raise SystemExit(f"no fig-a rows in {summary_csv}")
    means = {}
    for key, rows in grouped.items():
        selected = select_lowest_latency_runs(rows)
        means[key] = sum(float(r["consensus_latency_ms"]) for r in selected) / (
            1000.0 * len(selected)
        )
    return means


def build_series(means: dict[tuple[int, int], float]):
    series = []
    missing = []
    references = sorted({reference for _, reference in means})
    for sigma, label, color, linestyle in SERIES_SPEC:
        xs, ys = [], []
        for reference in references:
            key = (sigma, reference)
            if key not in means:
                missing.append(key)
                continue
            xs.append(reference)
            ys.append(means[key])
        if ys:
            series.append((label, color, linestyle, xs, ys))
    if missing:
        print(f"[warn] fig-a missing: {missing}")
    if not series:
        raise SystemExit("fig-a: no series to plot")
    return series


def draw(
    series,
    output_path: Path,
    *,
    also_png: bool = False,
    ylim: tuple[float, float] | None = None,
    yticks: list[float] | None = None,
    yticklabels: list[str] | None = None,
    legend_kwargs: dict | None = None,
) -> None:
    fig, ax = make_figure()
    plot_series(ax, series)
    ax.set_xlabel(r"Reference $ref$", fontsize=37.368)
    ax.set_ylabel("Latency (s)", fontsize=37.368)
    # Only label refs that appear in the plotted series (often {2,4,7}).
    plotted_refs = sorted({x for _, _, _, xs, _ in series for x in xs})
    ax.set_xticks(plotted_refs or REFERENCES)
    ax.margins(x=0.08, y=0.12)
    if ylim is not None:
        ax.set_ylim(*ylim)
    if yticks is not None:
        ax.set_yticks(yticks)
        if yticklabels is not None:
            ax.set_yticklabels(yticklabels)
    # Default: 2 columns × 3 rows for σ=1..6; caller can override loc/fontsize.
    legend = {"ncol": 2, "fontsize": 24.0, "loc": "best", "columnspacing": 1.0}
    if legend_kwargs:
        legend.update(legend_kwargs)
    return finish_figure(
        fig, ax, output_path, also_png=also_png, legend_kwargs=legend
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", type=Path)
    parser.add_argument(
        "--means-csv",
        type=Path,
        help="Prefer curated fig_a_means.csv over re-averaging consensus_summary.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--also-png",
        action="store_true",
        help="Also write a PNG alongside the PDF.",
    )
    parser.add_argument(
        "--ylim",
        type=float,
        nargs=2,
        metavar=("LO", "HI"),
        help="Optional fixed y-axis limits (latency seconds).",
    )
    parser.add_argument(
        "--yticks",
        type=float,
        nargs="+",
        help="Optional y-axis tick positions.",
    )
    parser.add_argument(
        "--yticklabels",
        type=str,
        nargs="+",
        help="Optional y-axis tick labels (use '' to hide a label).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.means_csv is not None:
        means = load_means_from_export(args.means_csv.resolve())
    elif args.summary_csv is not None:
        means = load_means(args.summary_csv.resolve())
    else:
        raise SystemExit("provide --means-csv or --summary-csv")
    series = build_series(means)
    output = args.output.resolve()
    ylim = tuple(args.ylim) if args.ylim is not None else None
    yticks = list(args.yticks) if args.yticks is not None else None
    yticklabels = list(args.yticklabels) if args.yticklabels is not None else None
    if yticklabels is not None and yticks is not None and len(yticklabels) != len(yticks):
        raise SystemExit("--yticklabels length must match --yticks")
    for path in draw(
        series,
        output,
        also_png=args.also_png,
        ylim=ylim,
        yticks=yticks,
        yticklabels=yticklabels,
    ):
        print(path)


if __name__ == "__main__":
    main()
