#!/usr/bin/env python3
"""Regenerate the eight archived Fig A/B/C GEO/LAN panels as PDF and PNG.

plot_style.py provides the shared canvas and style; the original per-figure
modules provide the plotting functions. Inputs stay under original_data and
outputs default to results/regenerate_graphs/experiment2_fig_abc.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42

import plot_fig_a_latency_vs_ref_by_sigma as fig_a
import plot_fig_b_latency_vs_kappa_by_cov as fig_b
import plot_fig_c as fig_c
from fig_abc_data import aggregate_runs, load_exported_runs, load_original_runs, write_tables


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_ROOT = REPO_ROOT / "paper_data" / "original_data" / "Figure10abc"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "results" / "regenerate_graphs" / "experiment2_fig_abc"
DEFAULT_PROCESSED_ROOT = REPO_ROOT / "results" / "processed_data" / "Figure10abc"
SETTINGS = json.loads(Path(__file__).with_name("fig_abc_settings.json").read_text())


def draw_a(directory: Path, network: str, output_dir: Path, processed_root: Path) -> list[Path]:
    settings = SETTINGS["fig_a"][network]
    rows = load_original_runs(directory, settings["excluded_run_names"])
    aggregated = aggregate_runs(rows)
    write_tables(processed_root / "fig_a" / network, "a", rows, aggregated)
    means = {(row["sigma"], row["reference"]): row["mean_consensus_latency_s"]
             for row in aggregated}
    axes = settings["latency_axes"]
    # The sized originals show every other tick on the latency axis.
    return fig_a.draw(
        fig_a.build_series(means),
        output_dir / f"fig_a_{network}_latency_vs_ref_by_sigma.pdf",
        also_png=True,
        ylim=tuple(axes["limits"]),
        yticks=axes["ticks"][::2],
        legend_kwargs={"loc": "lower right" if network == "geo" else "upper right"},
    )


def draw_b(directory: Path, network: str, output_dir: Path, processed_root: Path) -> list[Path]:
    processed = processed_root / "fig_b" / network
    # Use the original per-run CSV available for Fig B and recompute its means.
    rows = load_exported_runs(directory / "fig_b_runs.csv")
    aggregated = aggregate_runs(rows, round_seconds=True)
    write_tables(processed, "b", rows, aggregated)
    means = {(row["coverage"], row["kappa"]): row["mean_consensus_latency_s"]
             for row in aggregated}
    return fig_b.draw(
        means,
        output_dir / f"fig_b_{network}_latency_vs_cov_by_kappa.pdf",
        also_png=True,
    )


def draw_c(directory: Path, network: str, output_dir: Path, processed_root: Path) -> list[Path]:
    rows = load_original_runs(directory)
    means = aggregate_runs(rows, keep_lowest=3)
    write_tables(processed_root / "fig_c" / network, "c", rows, means)
    written = []
    for metric in ("latency", "tps"):
        fig, ax = fig_c.draw(means, metric)
        written.extend(
            fig_c.finish_figure(
                fig,
                ax,
                output_dir / f"fig_c_{network}_{metric}_vs_sigma_kappa_by_cov.pdf",
                also_png=True,
                legend_kwargs={"fontsize": 24, "loc": "best"},
            )
        )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--processed-data-root", type=Path, default=DEFAULT_PROCESSED_ROOT)
    parser.add_argument("--figure", choices=("a", "b", "c", "all"), default="all")
    parser.add_argument("--network", choices=("geo", "lan", "all"), default="all")
    args = parser.parse_args()
    figures = ("a", "b", "c") if args.figure == "all" else (args.figure,)
    networks = ("geo", "lan") if args.network == "all" else (args.network,)
    drawers = {"a": draw_a, "b": draw_b, "c": draw_c}
    for figure in figures:
        for network in networks:
            directory = args.data_root.resolve() / f"fig_{figure}" / network
            for output in drawers[figure](
                directory, network, args.output_dir.resolve(), args.processed_data_root.resolve()
            ):
                print(output)


if __name__ == "__main__":
    main()
