#!/usr/bin/env python3
"""Redraw corrected Figure 10(c) with the Figure 10(a)/(b) visual style.

The data loading and cumulative-mean calculation are deliberately reused from
MANTA's Figure 10(c) plotting code. This file only changes presentation and
uses the fixed canvas from ``new_experiment2/paper_figs_sized``: Figure 10(c)
is twice a regular panel's width while retaining the same height.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator


SCRIPT_DIR = Path(__file__).resolve().parent
MANTA_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_DATA_ROOT = MANTA_ROOT / "paper_data" / "original_data" / "Figure10_attack"
DEFAULT_OUTPUT_STEM = (
    MANTA_ROOT / "results" / "regenerate_graphs" / "experiment2_fig_abc"
    / "attack_latency_timeseries_overlay_mean_send_time_fig10ab_style"
)

MANTA_PLOT_DIR = SCRIPT_DIR
MANTA_ATTACK_SCRIPT = MANTA_PLOT_DIR / "plot_attack_latency_timeseries.py"
SAMPLES_ROOT = MANTA_ROOT / "paper_data" / "processed_data" / "Figure10_attack"

# Match the series order, colors, markers, and solid lines in the attack template.
SERIES = [
    ("k2c4", "k2-c4", r"$\kappa = 2,\ \mathit{cov} = 4$", "#1399b2", "D", "-"),
    ("k2c7", "k2-c7", r"$\kappa = 2,\ \mathit{cov} = 7$", "#8b5fbf", "o", "-"),
    ("k3c7", "k3-c7", r"$\kappa = 3,\ \mathit{cov} = 7$", "#c24e6a", "v", "-"),
    ("k3c10", "k3-c10", r"$\kappa = 3,\ \mathit{cov} = 10$", "#8f3131", "s", "-"),
]

# Typography and strokes measured from the sized attack template.
FONT_SIZE = 37.368
LEGEND_FONT_SIZE = 29.894
LINE_WIDTH = 2.761
MARKER_SIZE = 5.26
MARKER_EDGE_WIDTH = 0.789
SPINE_WIDTH = 1.183
TICK_WIDTH = 1.052
GRID_WIDTH = 0.657

# Exact canvas used by new_experiment2/paper_figs_sized. A regular panel is
# 9.6525 x 7.83 inches; attack latency occupies two horizontal slots.
OUTPUT_WIDTH_IN = 19.305
OUTPUT_HEIGHT_IN = 7.83


def load_manta_plot_module():
    """Load the canonical Figure 10(c) data-processing implementation."""
    if not MANTA_ATTACK_SCRIPT.is_file():
        raise SystemExit(f"missing MANTA plot script: {MANTA_ATTACK_SCRIPT}")
    sys.path.insert(0, str(MANTA_ROOT))
    sys.path.insert(0, str(MANTA_PLOT_DIR))
    spec = importlib.util.spec_from_file_location("manta_plot_attack_latency", MANTA_ATTACK_SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import MANTA plot script: {MANTA_ATTACK_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_run_dirs(data_root: Path) -> list[Path]:
    """Return one latency run for every paper configuration, in paper order."""
    run_dirs: list[Path] = []
    for directory_name, _, _, _, _, _ in SERIES:
        candidates = sorted((data_root / directory_name).rglob("latency.csv"))
        if len(candidates) != 1:
            raise SystemExit(
                f"expected exactly one latency.csv under {data_root / directory_name}, "
                f"found {len(candidates)}"
            )
        run_dirs.append(candidates[0].parent)
    return run_dirs


def build_series(data_root: Path):
    """Use the same send-time alignment and expanding mean as the source PNG."""
    manta = load_manta_plot_module()
    run_dirs = resolve_run_dirs(data_root)
    # Join the original run records with the exported send samples in a
    # temporary view. The committed inputs can be plotted without log files.
    with tempfile.TemporaryDirectory(prefix="manta-attack-inputs-") as temporary:
        inputs = []
        for spec, run_dir in zip(SERIES, run_dirs):
            samples = SAMPLES_ROOT / spec[0] / run_dir.name / "send_samples.csv"
            if not samples.is_file():
                inputs.append(run_dir)
                continue
            view = Path(temporary) / spec[0] / run_dir.name
            view.mkdir(parents=True)
            for name in ("latency.csv", "run_metadata.json"):
                (view / name).symlink_to(run_dir / name)
            (view / "send_samples.csv").symlink_to(samples)
            inputs.append(view)
        aggregated, attack_windows = manta.aggregate_runs_disjoint(
            inputs,
            manta.TIME_AXIS_SEND,
            5.0,       # Unused for the expanding mean, retained for source parity.
            1.0,       # One cumulative-mean point per second.
            25,
            None,
            "mean",
            60.0,
            None,
            120.0,
            None,
        )
    if not aggregated:
        raise SystemExit("no consensus-latency samples were recovered")
    return manta, aggregated, attack_windows


def draw(data_root: Path, output_stem: Path) -> tuple[Path, Path]:
    manta, aggregated, attack_windows = build_series(data_root)

    fig, ax = plt.subplots(figsize=(OUTPUT_WIDTH_IN, OUTPUT_HEIGHT_IN), dpi=180)

    legend_handles: list[Line2D] = []
    for _, data_label, display_label, color, marker, linestyle in SERIES:
        points = aggregated.get(data_label, [])
        if not points:
            raise SystemExit(f"missing aggregated series: {data_label}")
        xs = [float(point["x"]) for point in points]
        ys = [float(point["mean"]) for point in points]
        markevery = 1 if len(xs) <= 40 else max(2, len(xs) // 18)
        ax.plot(
            xs,
            ys,
            color=color,
            linestyle=linestyle,
            linewidth=LINE_WIDTH,
            marker=marker,
            markersize=MARKER_SIZE,
            markeredgewidth=MARKER_EDGE_WIDTH,
            markeredgecolor=color,
            markevery=markevery,
            clip_on=True,
            zorder=3,
        )
        legend_handles.append(
            Line2D(
                [],
                [],
                color=color,
                linestyle=linestyle,
                linewidth=LINE_WIDTH,
                marker=marker,
                markersize=MARKER_SIZE,
                markeredgewidth=MARKER_EDGE_WIDTH,
                label=display_label,
            )
        )

    starts = [
        float(window["start"])
        for window in attack_windows.values()
        if window.get("start") is not None
    ]
    attack_start = 60.0 if not starts else float(sorted(starts)[len(starts) // 2])
    attack_end = 120.0
    attack_color = "#dc2626"
    ax.axvspan(attack_start, attack_end, color="#b91c1c", alpha=0.025, zorder=0)
    attack_dash = (0, (1.5, 6.0))
    ax.axvline(attack_start, color=attack_color, linestyle=attack_dash, linewidth=LINE_WIDTH, zorder=2)
    ax.axvline(attack_end, color=attack_color, linestyle=attack_dash, linewidth=LINE_WIDTH, zorder=2)

    # Preserve the source plot's composition-based y range.
    y_min, y_max = manta.composition_y_limits_from_aggregated(
        aggregated,
        y_key="mean",
        y_log_scale=False,
        low_pct=0.5,
        high_pct=99.5,
        top_headroom=0.42,
        bottom_pad=0.0,
    )
    ax.set_xlim(0.0, 123.0)
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel("Time (s)", fontsize=FONT_SIZE)
    ax.set_ylabel("Latency (s)", fontsize=FONT_SIZE)
    ax.set_xticks([0, 20, 40, 60, 80, 100, 120])
    ax.tick_params(
        axis="both", labelsize=FONT_SIZE, width=TICK_WIDTH, direction="in"
    )
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=4))
    for spine in ax.spines.values():
        spine.set_linewidth(SPINE_WIDTH)
    ax.grid(True, linestyle="--", linewidth=GRID_WIDTH, color="0.69", alpha=0.5)
    ax.legend(
        handles=legend_handles,
        fontsize=LEGEND_FONT_SIZE,
        frameon=True,
        fancybox=False,
        framealpha=0.8,
        facecolor="white",
        edgecolor="0.8",
        loc="upper left",
        ncol=1,
        handlelength=2.0,
    )

    y_span = y_max - y_min
    arrow_y = y_min + 0.88 * y_span
    label_y = y_min + 0.930 * y_span
    ax.annotate(
        "",
        xy=(attack_end, arrow_y),
        xytext=(attack_start, arrow_y),
        arrowprops={
            "arrowstyle": "<->",
            "color": attack_color,
            "linewidth": 2.2,
            "mutation_scale": 20,
        },
        zorder=4,
    )
    ax.text(
        0.5 * (attack_start + attack_end),
        label_y,
        "Attack Window",
        color=attack_color,
        fontsize=33.632,
        ha="center",
        va="center",
        zorder=4,
    )

    output_stem.parent.mkdir(parents=True, exist_ok=True)
    output_png = output_stem.with_suffix(".png")
    output_pdf = output_stem.with_suffix(".pdf")
    # Exact axes rectangle measured from the reference attack PDF.
    fig.set_size_inches(OUTPUT_WIDTH_IN, OUTPUT_HEIGHT_IN, forward=True)
    ax.set_position([0.07746, 0.1490, 0.9160, 0.8430])
    for output in (output_png, output_pdf):
        fig.savefig(output, dpi=180)
    plt.close(fig)
    return output_png, output_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--output-stem",
        type=Path,
        default=DEFAULT_OUTPUT_STEM,
        help="Output path without extension; both PNG and PDF are written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    png, pdf = draw(args.data_root.resolve(), args.output_stem.resolve())
    print(png)
    print(pdf)


if __name__ == "__main__":
    main()
