#!/usr/bin/env python3
"""
Animated GIF of 2 m temperature from a WRF output file (wrfout):
map on top, time series at the point of interest below, with a marker
that moves along the curve as the map changes.

Usage:
  python animar_wrfout.py /path/wrfout_d01_YYYY-MM-DD_HH:MM:SS [output.gif]
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graficar_wrfout import (CMAP, POINT, TZ_NAME, draw_map, draw_series,  # noqa: E402
                             load, nearest)

FPS = 1.5
CREDIT = "WRF test run (15 km), NCEP FNL data. Not a forecast."


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else "t2_animation.gif"
    d = load(sys.argv[1])
    t2 = d["t2"]
    j, i = nearest(d["lat"], d["lon"], POINT[1], POINT[2])
    series = t2[:, j, i]
    vmin = np.floor(np.percentile(t2, 1))
    vmax = np.ceil(np.percentile(t2, 99.5))

    fig, (ax_map, ax_ts) = plt.subplots(2, 1, figsize=(7.5, 9.5),
                                        gridspec_kw={"height_ratios": [3, 1.1]})
    m = draw_map(ax_map, d, t2[0], CMAP, vmin=vmin, vmax=vmax)
    fig.colorbar(m, ax=ax_map, label="°C", shrink=0.85)
    title = ax_map.set_title(f"2 m temperature\n{d['local'][0]:%b %d, %Y %H:%M} local time ({TZ_NAME})")
    draw_series(ax_ts, d, series)
    ax_ts.set_title(f"2 m temperature in {POINT[0]}", fontsize=10)
    vline = ax_ts.axvline(d["local"][0], color="gray", lw=1, ls="--")
    (dot,) = ax_ts.plot(d["local"][0], series[0], "o", ms=11, mfc="none", mec="k", mew=1.5)
    fig.text(0.01, 0.005, CREDIT, fontsize=7, color="gray")
    fig.tight_layout()

    def frame(n):
        m.set_array(t2[n].ravel())
        title.set_text(f"2 m temperature\n{d['local'][n]:%b %d, %Y %H:%M} local time ({TZ_NAME})")
        vline.set_xdata([d["local"][n]] * 2)
        dot.set_data([d["local"][n]], [series[n]])
        return m, title, vline, dot

    anim = FuncAnimation(fig, frame, frames=len(t2), blit=False)
    anim.save(out, writer=PillowWriter(fps=FPS), dpi=100)
    plt.close(fig)
    print(f"Animation saved: {out} ({len(t2)} frames)")


if __name__ == "__main__":
    main()
