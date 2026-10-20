"""Shared matplotlib style for new_experiment2 paper figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt


FONTSIZE = 37.368
LEGEND_FONTSIZE = 29.894
LINEWIDTH = 5.397
MARKERSIZE = 13.493
MARKEREDGEWIDTH = 1.619
SPINEWIDTH = 2.429
GRIDWIDTH = 1.349
# Fixed canvas sized for Flexible_DAG_Consensus.pdf layout (letter, ~7.02in text).
# Row plans: [2 half + attack] or [4 half] → 4 equal slots across text width.
# Attack spans 2 slots (2× half width). Same height for every figure.
# RENDER_SCALE keeps large fonts; LaTeX shrinks to textwidth/4 or textwidth/2.
PAPER_TEXTWIDTH_IN = 7.02
FIG_SLOTS_PER_ROW = 4
RENDER_SCALE = 5.5
FIG_HEIGHT_IN = 7.83
FIG_WIDTH_IN = (PAPER_TEXTWIDTH_IN / FIG_SLOTS_PER_ROW) * RENDER_SCALE  # ~9.6525
FIG_WIDTH_DOUBLE_IN = 2.0 * FIG_WIDTH_IN
FIGSIZE = (FIG_WIDTH_IN, FIG_HEIGHT_IN)
DPI = 180

SCRIPT_DIR = Path(__file__).resolve().parent


def apply_axes_style(ax) -> None:
    # Never set_box_aspect: x/y axis lengths are independent on the fixed canvas.
    ax.tick_params(axis="both", labelsize=FONTSIZE, width=SPINEWIDTH)
    for spine in ax.spines.values():
        spine.set_linewidth(SPINEWIDTH)
    ax.grid(True, linestyle=(0, (1, 2)), linewidth=GRIDWIDTH, color="0.78")


def plot_series(ax, series: list[tuple[str, str, str, list, list]]) -> None:
    for label, color, linestyle, xs, ys in series:
        ax.plot(
            xs,
            ys,
            color=color,
            linewidth=LINEWIDTH,
            linestyle=linestyle,
            marker="o",
            markersize=MARKERSIZE,
            markeredgewidth=MARKEREDGEWIDTH,
            label=label,
        )


def plot_scatter(
    ax,
    points: list[tuple[str, str, str, float, float]],
    *,
    markersize: float = MARKERSIZE * 1.35,
) -> None:
    """Scatter points as (label, color, marker, x, y)."""
    for label, color, marker, x, y in points:
        ax.scatter(
            [x],
            [y],
            s=markersize**2,
            color=color,
            marker=marker,
            edgecolors="black",
            linewidths=MARKEREDGEWIDTH,
            label=label,
            zorder=3,
        )


def fit_axes_in_canvas(fig, ax, *, keep_inches: float = 0.06) -> None:
    """Keep canvas size fixed; shrink/grow axes so all labels fit inside.

    Does not enforce any x/y aspect ratio — only adjusts the axes rectangle.
    """
    fig.set_layout_engine(None)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for _ in range(24):
        bb = fig.get_tightbbox(renderer)
        if bb is None:
            break
        fw, fh = fig.get_size_inches()
        # Overflow past the canvas (negative => room to spare).
        left_over = max(0.0, keep_inches - float(bb.x0))
        bottom_over = max(0.0, keep_inches - float(bb.y0))
        right_over = max(0.0, float(bb.x1) - (fw - keep_inches))
        top_over = max(0.0, float(bb.y1) - (fh - keep_inches))

        left_extra = max(0.0, float(bb.x0) - keep_inches)
        bottom_extra = max(0.0, float(bb.y0) - keep_inches)
        right_extra = max(0.0, (fw - keep_inches) - float(bb.x1))
        top_extra = max(0.0, (fh - keep_inches) - float(bb.y1))

        # Prefer fixing overflow by shrinking axes; only then reclaim spare margin.
        dx0 = (left_over - 0.35 * left_extra) / fw
        dy0 = (bottom_over - 0.35 * bottom_extra) / fh
        dx1 = (right_over - 0.35 * right_extra) / fw
        dy1 = (top_over - 0.35 * top_extra) / fh
        if abs(dx0) + abs(dy0) + abs(dx1) + abs(dy1) < 5e-4:
            break

        pos = ax.get_position()
        new_x0 = pos.x0 + dx0
        new_y0 = pos.y0 + dy0
        new_w = pos.width - dx0 - dx1
        new_h = pos.height - dy0 - dy1
        # Keep a usable plot area.
        if new_w < 0.35 or new_h < 0.35:
            break
        ax.set_position([new_x0, new_y0, new_w, new_h])
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()


def finish_figure(
    fig,
    ax,
    output_path: Path,
    *,
    legend_kwargs: dict | None = None,
    also_png: bool = False,
    fig_width_in: float = FIG_WIDTH_IN,
    fig_height_in: float = FIG_HEIGHT_IN,
) -> list[Path]:
    apply_axes_style(ax)
    kw = {"fontsize": LEGEND_FONTSIZE, "frameon": True, "loc": "best"}
    if legend_kwargs:
        kw.update(legend_kwargs)
    ax.legend(**kw)
    fig.set_size_inches(fig_width_in, fig_height_in, forward=True)
    # Start with a long x-axis box on the narrower half-width canvas, then fit labels.
    ax.set_position([0.16, 0.17, 0.80, 0.76])
    fit_axes_in_canvas(fig, ax, keep_inches=0.06)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI)
    written = [output_path.resolve()]
    if also_png:
        png_path = output_path.with_suffix(".png")
        fig.savefig(png_path, dpi=DPI)
        written.append(png_path.resolve())
    plt.close(fig)
    return written


def make_figure():
    return plt.subplots(figsize=FIGSIZE, dpi=DPI)
