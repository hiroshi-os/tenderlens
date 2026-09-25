"""Server-side charts. Matplotlib's Agg backend needs no display."""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def bar_chart(labels: list[str], values: list[float], title: str, xlabel: str) -> bytes:
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    fig.patch.set_facecolor("#f6f4ef")
    ax.set_facecolor("#f6f4ef")
    if not labels:
        ax.text(
            0.5,
            0.5,
            "Nothing to plot yet",
            ha="center",
            va="center",
            transform=ax.transAxes,
            color="#57534e",
        )
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        shown = [label if len(label) <= 42 else label[:39] + "…" for label in labels]
        ax.barh(shown[::-1], list(values)[::-1], color="#0f6e6e")
        ax.set_xlabel(xlabel)
        ax.tick_params(colors="#1c1917")
    ax.set_title(title, loc="left", color="#1c1917", pad=10)
    for spine in ax.spines.values():
        spine.set_color("#d6d3d1")
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=120)
    plt.close(fig)
    return buffer.getvalue()
