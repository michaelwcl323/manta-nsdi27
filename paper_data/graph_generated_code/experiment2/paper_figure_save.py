"""Helpers for paper exports: tight content bbox, then pad to a target page size."""

from __future__ import annotations

from matplotlib.figure import Figure
from matplotlib.transforms import Bbox


def savefig_tight_target_aspect(
    fig: Figure,
    path,
    target_wh: float,
    *,
    pad_inches: float = 0.03,
    dpi: int | None = None,
    width_in: float | None = None,
    height_in: float | None = None,
) -> None:
    """
    Save *fig* so the page has aspect width/height == *target_wh*.

    Starts from the usual tight bounding box (plus *pad_inches*), then expands
    the saved bbox with whitespace on one axis (never crops artists).

    If *width_in* and *height_in* are both set, the page is forced to that exact
    size (same aspect as target_wh). Extra whitespace is added when content is
    smaller; if content is larger, the figure is scaled down uniformly to fit.
    """

    def _content_page():
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        bb = fig.get_tightbbox(renderer)
        if bb is None or bb.width <= 0 or bb.height <= 0:
            return None
        bb = bb.padded(pad_inches)
        w, h = float(bb.width), float(bb.height)
        cx = float(bb.x0) + 0.5 * w
        cy = float(bb.y0) + 0.5 * h
        if w / h > target_wh:
            new_w, new_h = w, w / target_wh
        else:
            new_w, new_h = h * target_wh, h
        return cx, cy, new_w, new_h

    page = _content_page()
    if page is None:
        fig.savefig(path, bbox_inches="tight", pad_inches=pad_inches, dpi=dpi)
        return
    cx, cy, new_w, new_h = page

    if width_in is not None and height_in is not None:
        if abs(width_in / height_in - target_wh) > 1e-6:
            raise ValueError(
                f"width_in/height_in ({width_in}/{height_in}) must match "
                f"target_wh={target_wh}"
            )
        if new_w > width_in + 1e-9 or new_h > height_in + 1e-9:
            scale = min(width_in / new_w, height_in / new_h)
            w0, h0 = fig.get_size_inches()
            fig.set_size_inches(w0 * scale, h0 * scale)
            page = _content_page()
            if page is None:
                fig.savefig(path, bbox_inches="tight", pad_inches=pad_inches, dpi=dpi)
                return
            cx, cy, new_w, new_h = page
        new_w, new_h = width_in, height_in

    out = Bbox.from_bounds(cx - 0.5 * new_w, cy - 0.5 * new_h, new_w, new_h)
    kw: dict = {"bbox_inches": out, "pad_inches": 0}
    if dpi is not None:
        kw["dpi"] = dpi
    fig.savefig(path, **kw)


def savefig_tight_target_size(
    fig: Figure,
    path,
    width_in: float,
    height_in: float,
    *,
    pad_inches: float = 0.03,
    dpi: int | None = None,
) -> None:
    """Save *fig* to an exact page size (width_in x height_in inches)."""
    savefig_tight_target_aspect(
        fig,
        path,
        width_in / height_in,
        pad_inches=pad_inches,
        dpi=dpi,
        width_in=width_in,
        height_in=height_in,
    )
