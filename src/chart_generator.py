"""
K线图生成模块
包含5日、10日、20日、250日均线
"""

import os
import logging
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.gridspec as gridspec
from datetime import datetime

logger = logging.getLogger(__name__)

# 配色方案（专业金融风格）
COLORS = {
    'bg': '#0d1117',
    'bg_panel': '#161b22',
    'grid': '#21262d',
    'text': '#e6edf3',
    'text_dim': '#8b949e',
    'up': '#26a641',       # 涨 - 绿色
    'down': '#f85149',     # 跌 - 红色
    'ma5': '#f0e68c',      # 5日线 - 金黄
    'ma10': '#00bfff',     # 10日线 - 天蓝
    'ma20': '#ff69b4',     # 20日线 - 粉红（原28日改为20日，更标准）
    'ma250': '#ff8c00',    # 250日线 - 橙色
    'volume_up': '#26a641',
    'volume_down': '#f85149',
    'border': '#30363d',
}

plt.rcParams.update({
    'font.family': ['DejaVu Sans', 'WenQuanYi Micro Hei', 'SimHei', 'Arial Unicode MS', 'sans-serif'],
    'axes.facecolor': COLORS['bg_panel'],
    'figure.facecolor': COLORS['bg'],
    'text.color': COLORS['text'],
    'axes.labelcolor': COLORS['text_dim'],
    'xtick.color': COLORS['text_dim'],
    'ytick.color': COLORS['text_dim'],
    'axes.edgecolor': COLORS['border'],
    'grid.color': COLORS['grid'],
    'grid.linewidth': 0.5,
    'grid.alpha': 0.6,
})


def calculate_ma(df: pd.DataFrame, window: int) -> pd.Series:
    """计算移动平均线"""
    return df['close'].rolling(window=window, min_periods=1).mean()


def plot_kline(df: pd.DataFrame, code: str, name: str, output_path: str,
               hot_rank: int = 0, capital_inflow: float = 0) -> str:
    """
    绘制专业K线图（含均线+成交量+技术指标面板）
    :param df: OHLCV数据
    :param code: 股票代码
    :param name: 股票名称
    :param output_path: 输出路径
    :param hot_rank: 热度排名
    :param capital_inflow: 三日资金流入（元）
    :return: 图片路径
    """
    # 只显示最近120个交易日
    df = df.tail(120).copy()
    n = len(df)
    if n < 5:
        logger.warning(f"K线数据不足: {code}")
        return ""

    # 计算均线
    df['ma5'] = calculate_ma(df, 5)
    df['ma10'] = calculate_ma(df, 10)
    df['ma20'] = calculate_ma(df, 20)
    df['ma250'] = calculate_ma(df, 250)  # 需要更多历史数据才准确

    # 创建画布
    fig = plt.figure(figsize=(16, 10), dpi=120, facecolor=COLORS['bg'])
    gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 0.08], hspace=0.04,
                           left=0.06, right=0.96, top=0.88, bottom=0.08)

    ax_k = fig.add_subplot(gs[0])
    ax_v = fig.add_subplot(gs[1], sharex=ax_k)
    ax_info = fig.add_subplot(gs[2])

    # ── K线主图 ──────────────────────────────────────────
    x = np.arange(n)
    width = 0.7
    width_shadow = 0.15

    for i in range(n):
        row = df.iloc[i]
        color = COLORS['up'] if row['close'] >= row['open'] else COLORS['down']

        # 实体
        bottom = min(row['open'], row['close'])
        height = abs(row['close'] - row['open'])
        if height < row['close'] * 0.001:
            height = row['close'] * 0.001

        rect = plt.Rectangle((x[i] - width / 2, bottom), width, height,
                              facecolor=color, edgecolor=color, linewidth=0, zorder=3)
        ax_k.add_patch(rect)

        # 上下影线
        ax_k.plot([x[i], x[i]], [row['low'], row['high']],
                  color=color, linewidth=width_shadow * 8, zorder=2)

    # 均线
    for ma_col, color, label, lw in [
        ('ma5', COLORS['ma5'], 'MA5', 1.2),
        ('ma10', COLORS['ma10'], 'MA10', 1.2),
        ('ma20', COLORS['ma20'], 'MA20', 1.2),
        ('ma250', COLORS['ma250'], 'MA250', 1.5),
    ]:
        valid = df[ma_col].dropna()
        if len(valid) > 0:
            valid_idx = [i for i, v in enumerate(df[ma_col]) if not np.isnan(v)]
            ax_k.plot(valid_idx, df[ma_col].iloc[valid_idx],
                      color=color, linewidth=lw, label=label, zorder=4, alpha=0.9)

    ax_k.set_xlim(-1, n)
    ax_k.grid(True, alpha=0.3)
    ax_k.legend(loc='upper left', fontsize=9, framealpha=0.3,
                 facecolor=COLORS['bg_panel'], edgecolor=COLORS['border'])

    # 当前价格标注
    last_price = df['close'].iloc[-1]
    ax_k.axhline(y=last_price, color=COLORS['text_dim'], linewidth=0.5, linestyle='--', alpha=0.5)
    ax_k.text(n - 0.5, last_price, f'  {last_price:.2f}',
              color=COLORS['text'], fontsize=9, va='center', zorder=5)

    # ── 成交量图 ──────────────────────────────────────────
    for i in range(n):
        row = df.iloc[i]
        color = COLORS['volume_up'] if row['close'] >= row['open'] else COLORS['volume_down']
        ax_v.bar(x[i], row['volume'] / 1e4, width=width, color=color, alpha=0.8, zorder=2)

    ax_v.set_ylabel('成交量(万手)', fontsize=8, color=COLORS['text_dim'])
    ax_v.grid(True, alpha=0.3)
    ax_v.yaxis.set_label_position('right')
    ax_v.yaxis.tick_right()

    # ── X轴标签 ──────────────────────────────────────────
    tick_indices = list(range(0, n, max(1, n // 8)))
    ax_v.set_xticks(tick_indices)
    ax_v.set_xticklabels(
        [df.index[i].strftime('%m/%d') for i in tick_indices],
        fontsize=8, rotation=0
    )
    plt.setp(ax_k.get_xticklabels(), visible=False)

    # ── 信息栏 ────────────────────────────────────────────
    ax_info.axis('off')
    price_change = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100
    change_color = COLORS['up'] if price_change >= 0 else COLORS['down']
    info_text = (
        f"今收: {last_price:.2f}   "
        f"涨跌: {'▲' if price_change >= 0 else '▼'}{abs(price_change):.2f}%   "
        f"5日线: {df['ma5'].iloc[-1]:.2f}   "
        f"10日线: {df['ma10'].iloc[-1]:.2f}   "
        f"20日线: {df['ma20'].iloc[-1]:.2f}"
    )
    ax_info.text(0.01, 0.5, info_text, transform=ax_info.transAxes,
                 fontsize=9, color=COLORS['text_dim'], va='center')

    # ── 标题 ──────────────────────────────────────────────
    last_date = df.index[-1].strftime('%Y-%m-%d')
    title_line1 = f"{name}（{code}）"
    title_line2 = f"热度排名 #{hot_rank}  |  三日主力净流入 {capital_inflow / 1e8:.2f} 亿元  |  更新日期 {last_date}"

    fig.text(0.06, 0.95, title_line1, fontsize=16, fontweight='bold',
             color=COLORS['text'], va='top')
    fig.text(0.06, 0.91, title_line2, fontsize=10,
             color=COLORS['text_dim'], va='top')

    # 均线图例说明
    legend_text = "■ MA5(金)  ■ MA10(蓝)  ■ MA20(粉)  ■ MA250(橙)"
    fig.text(0.96, 0.91, legend_text, fontsize=8,
             color=COLORS['text_dim'], va='top', ha='right')

    # 保存
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    plt.savefig(output_path, dpi=120, bbox_inches='tight',
                facecolor=COLORS['bg'], edgecolor='none')
    plt.close(fig)
    logger.info(f"K线图已保存: {output_path}")
    return output_path
