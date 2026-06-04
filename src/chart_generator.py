import logging
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

COLORS = {
    "bg": "#0f1115",
    "panel": "#171a21",
    "grid": "#2a2f3a",
    "text": "#f2f4f8",
    "muted": "#9aa4b2",
    "up": "#d84a4a",
    "down": "#2fa866",
    "ma5": "#f2c94c",
    "ma10": "#56ccf2",
    "ma28": "#bb6bd9",
    "ma250": "#f2994a",
}

plt.rcParams.update(
    {
        "font.family": ["DejaVu Sans", "WenQuanYi Micro Hei", "SimHei", "Microsoft YaHei", "sans-serif"],
        "axes.facecolor": COLORS["panel"],
        "figure.facecolor": COLORS["bg"],
        "axes.edgecolor": COLORS["grid"],
        "axes.labelcolor": COLORS["muted"],
        "xtick.color": COLORS["muted"],
        "ytick.color": COLORS["muted"],
        "text.color": COLORS["text"],
        "axes.unicode_minus": False,
    }
)


def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for window in (5, 10, 28, 250):
        work[f"ma{window}"] = work["close"].rolling(window=window, min_periods=window).mean()
    return work


def plot_kline(
    df: pd.DataFrame,
    code: str,
    name: str,
    output_path: str,
    hot_rank: int,
    capital_rank: int,
    capital_inflow: float,
) -> str:
    if df is None or len(df) < 30:
        raise ValueError(f"K-line data is not enough for {code}")

    df = add_moving_averages(df)
    view = df.tail(160).copy()
    x = np.arange(len(view))

    fig = plt.figure(figsize=(15, 9), dpi=130, facecolor=COLORS["bg"])
    gs = gridspec.GridSpec(2, 1, height_ratios=[3.2, 1], hspace=0.04, left=0.06, right=0.96, top=0.86, bottom=0.08)
    ax_price = fig.add_subplot(gs[0])
    ax_volume = fig.add_subplot(gs[1], sharex=ax_price)

    width = 0.62
    for idx, (_, row) in enumerate(view.iterrows()):
        color = COLORS["up"] if row["close"] >= row["open"] else COLORS["down"]
        ax_price.plot([idx, idx], [row["low"], row["high"]], color=color, linewidth=1.1, zorder=2)
        bottom = min(row["open"], row["close"])
        height = max(abs(row["close"] - row["open"]), row["close"] * 0.001)
        ax_price.add_patch(
            plt.Rectangle((idx - width / 2, bottom), width, height, facecolor=color, edgecolor=color, linewidth=0, zorder=3)
        )
        ax_volume.bar(idx, row["volume"] / 10000, width=width, color=color, alpha=0.75)

    for col, label, color, linewidth in [
        ("ma5", "MA5", COLORS["ma5"], 1.2),
        ("ma10", "MA10", COLORS["ma10"], 1.2),
        ("ma28", "MA28", COLORS["ma28"], 1.25),
        ("ma250", "MA250", COLORS["ma250"], 1.45),
    ]:
        if col in view.columns:
            ax_price.plot(x, view[col].to_numpy(), color=color, linewidth=linewidth, label=label, alpha=0.95)

    last = view.iloc[-1]
    prev = view.iloc[-2]
    change_pct = (last["close"] / prev["close"] - 1) * 100
    ax_price.axhline(last["close"], color=COLORS["muted"], linestyle="--", linewidth=0.7, alpha=0.6)
    ax_price.text(len(view) - 1, last["close"], f" {last['close']:.2f}", va="center", fontsize=9)

    tick_step = max(1, len(view) // 8)
    tick_indices = list(range(0, len(view), tick_step))
    ax_volume.set_xticks(tick_indices)
    ax_volume.set_xticklabels([view.index[i].strftime("%m/%d") for i in tick_indices], fontsize=8)
    plt.setp(ax_price.get_xticklabels(), visible=False)

    ax_price.grid(True, color=COLORS["grid"], alpha=0.45, linewidth=0.6)
    ax_volume.grid(True, color=COLORS["grid"], alpha=0.35, linewidth=0.5)
    ax_price.legend(loc="upper left", fontsize=8, framealpha=0.2)
    ax_volume.set_ylabel("Volume(10k)", fontsize=8)
    ax_price.set_xlim(-1, len(view))

    title = f"{name} ({code})"
    subtitle = (
        f"Hot rank #{hot_rank} | 3-day main fund rank #{capital_rank} | "
        f"3-day main fund inflow {capital_inflow / 1e8:.2f}B CNY | "
        f"Last {last['close']:.2f} ({change_pct:+.2f}%)"
    )
    fig.text(0.06, 0.94, title, fontsize=17, fontweight="bold", color=COLORS["text"])
    fig.text(0.06, 0.90, subtitle, fontsize=9.5, color=COLORS["muted"])
    fig.text(0.96, 0.90, "MA5 / MA10 / MA28 / MA250", fontsize=9, color=COLORS["muted"], ha="right")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    plt.savefig(output_path, dpi=130, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close(fig)
    logger.info("Saved K-line chart: %s", output_path)
    return output_path


def calculate_kline_summary(df: pd.DataFrame | None) -> dict:
    if df is None or len(df) < 2:
        return {}
    enriched = add_moving_averages(df)
    last = enriched.iloc[-1]
    prev = enriched.iloc[-2]
    change_pct = (last["close"] / prev["close"] - 1) * 100
    trend_5d = (last["close"] / enriched["close"].iloc[-5] - 1) * 100 if len(enriched) >= 5 else 0.0

    def fmt(value: object) -> str:
        return "N/A" if pd.isna(value) else f"{float(value):.2f}"

    ma250 = last.get("ma250")
    if pd.isna(ma250):
        vs_ma250 = "MA250 data is not enough"
    else:
        vs_ma250 = "above MA250" if last["close"] > ma250 else "below MA250"

    return {
        "last_price": fmt(last["close"]),
        "change_pct": f"{change_pct:+.2f}",
        "ma5": fmt(last.get("ma5")),
        "ma10": fmt(last.get("ma10")),
        "ma28": fmt(last.get("ma28")),
        "ma250": fmt(ma250),
        "vs_ma250": vs_ma250,
        "trend_5d": f"{trend_5d:+.2f}",
    }
