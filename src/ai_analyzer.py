"""
AI 分析模块
调用 DeepSeek API 对每只股票生成深度分析报告（技术面 + 基本面 + 热度理由）
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"  # DeepSeek-V3，性价比最高


def analyze_stock(
    code: str,
    name: str,
    hot_rank: int,
    capital_inflow_3d: float,
    basic_info: dict,
    news_list: list[dict],
    kline_summary: dict,
) -> str:
    """
    调用 DeepSeek API 生成股票深度分析报告
    """
    if not DEEPSEEK_API_KEY:
        logger.warning("未配置 DEEPSEEK_API_KEY，使用备用模板")
        return _generate_fallback_analysis(code, name, hot_rank, capital_inflow_3d, basic_info, news_list)

    # 构建新闻摘要
    news_text = ""
    for i, n in enumerate(news_list[:6], 1):
        news_text += f"{i}. [{n.get('date', '')}] {n.get('title', '')}\n   {n.get('digest', '')[:150]}\n\n"

    # K线技术摘要
    tech_text = f"""
- 当前价格: {kline_summary.get('last_price', 'N/A')} 元
- 5日均线: {kline_summary.get('ma5', 'N/A')} 元
- 10日均线: {kline_summary.get('ma10', 'N/A')} 元
- 20日均线: {kline_summary.get('ma20', 'N/A')} 元
- 250日均线（年线）: {kline_summary.get('ma250', 'N/A')} 元
- 当日涨跌幅: {kline_summary.get('change_pct', 'N/A')}%
- 价格位于年线{kline_summary.get('vs_ma250', '')}
- 近5日涨跌: {kline_summary.get('trend_5d', 'N/A')}
"""

    fundamental_text = f"""
- 总市值: {basic_info.get('market_cap', 0):.1f} 亿元
- 流通市值: {basic_info.get('float_cap', 0):.1f} 亿元
- 动态市盈率(PE): {basic_info.get('pe_dynamic', 0):.1f} 倍
- 市净率(PB): {basic_info.get('pb', 0):.2f} 倍
- 换手率: {basic_info.get('turnover_rate', 0):.2f}%
- 量比: {basic_info.get('volume_ratio', 0):.2f}
- 52周最高: {basic_info.get('52w_high', 0):.2f} 元
- 52周最低: {basic_info.get('52w_low', 0):.2f} 元
"""

    prompt = f"""你是一位专业A股分析师，请对以下股票进行深度分析报告。

## 股票基本信息
- 股票代码: {code}
- 股票名称: {name}
- 今日热度排名: 第 {hot_rank} 名（全市场热度榜）
- 近三日主力资金净流入: {capital_inflow_3d / 1e8:.2f} 亿元

## 技术面数据
{tech_text}

## 基本面数据
{fundamental_text}

## 最新市场资讯（近期新闻标题）
{news_text if news_text else "暂无最新资讯"}

## 分析要求
请生成一份专业的深度分析报告，包含以下5个部分：

### 1. 🔥 热度飙升原因
结合新闻资讯，分析该股票今日热度排名靠前的核心驱动力。是政策利好、业绩爆发、行业风口、还是资金炒作？要指出具体在"炒什么"。

### 2. 💰 资金流入逻辑
分析为何近三日有大量主力资金净流入，是机构建仓、游资炒作、还是北向资金青睐？结合换手率和量比给出判断。

### 3. 📈 技术面分析
分析当前K线形态、均线多空排列（MA5/MA10/MA20/MA250关系）、支撑压力位、是否处于突破形态。

### 4. 🏢 基本面评估
结合市值、PE、PB等估值指标，评估当前估值水平（偏高/合理/低估），以及公司所处行业地位。

### 5. ⚠️ 主要风险提示
列出2-3个主要投资风险。

---
**注意**：请用简洁专业的语言，每个部分100-150字，全文不超过600字。语气客观，不构成投资建议。"""

    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"DeepSeek API 调用失败: {e}")
        return _generate_fallback_analysis(code, name, hot_rank, capital_inflow_3d, basic_info, news_list)


def _generate_fallback_analysis(
    code: str, name: str, hot_rank: int, capital_inflow_3d: float,
    basic_info: dict, news_list: list[dict]
) -> str:
    """API 不可用时的备用分析"""
    news_titles = "\n".join(f"• {n['title']}" for n in news_list[:4]) if news_list else "暂无资讯"
    return f"""## {name}（{code}）分析摘要

### 🔥 热度飙升原因
该股今日热度排名第 {hot_rank} 名。相关近期资讯：
{news_titles}

### 💰 资金流入逻辑
近三日主力资金净流入 **{capital_inflow_3d / 1e8:.2f} 亿元**，换手率 {basic_info.get('turnover_rate', 0):.2f}%，量比 {basic_info.get('volume_ratio', 0):.2f}，显示资金活跃度较高。

### 📈 技术面
当前价格 {basic_info.get('price', 0):.2f} 元，当日涨跌 {basic_info.get('change_pct', 0):+.2f}%。请参考K线图了解均线形态。

### 🏢 基本面
总市值 {basic_info.get('market_cap', 0):.1f} 亿元，动态PE {basic_info.get('pe_dynamic', 0):.1f} 倍，PB {basic_info.get('pb', 0):.2f} 倍。

### ⚠️ 风险提示
1. 热门股追高风险较大，注意回调风险
2. 主力资金流入不代表股价必然上涨
3. 本报告仅供参考，不构成投资建议

*（注：AI深度分析需配置 DEEPSEEK_API_KEY）*"""


def calculate_kline_summary(df) -> dict:
    """从K线数据计算技术摘要"""
    if df is None or len(df) < 2:
        return {}

    import numpy as np

    last = df.iloc[-1]
    prev = df.iloc[-2]
    change_pct = (last['close'] - prev['close']) / prev['close'] * 100

    ma5 = df['close'].rolling(5).mean().iloc[-1]
    ma10 = df['close'].rolling(10).mean().iloc[-1]
    ma20 = df['close'].rolling(20).mean().iloc[-1]
    ma250 = df['close'].rolling(250).mean().iloc[-1] if len(df) >= 250 else df['close'].rolling(len(df)).mean().iloc[-1]

    if not np.isnan(ma250):
        vs_ma250 = "上方（强势）" if last['close'] > ma250 else "下方（偏弱）"
    else:
        vs_ma250 = "（数据不足）"

    trend_5d = f"{(last['close'] / df['close'].iloc[-5] - 1) * 100:+.2f}%" if len(df) >= 5 else "N/A"

    return {
        "last_price": f"{last['close']:.2f}",
        "ma5": f"{ma5:.2f}" if not np.isnan(ma5) else "N/A",
        "ma10": f"{ma10:.2f}" if not np.isnan(ma10) else "N/A",
        "ma20": f"{ma20:.2f}" if not np.isnan(ma20) else "N/A",
        "ma250": f"{ma250:.2f}" if not np.isnan(ma250) else "N/A",
        "change_pct": f"{change_pct:.2f}",
        "vs_ma250": vs_ma250,
        "trend_5d": trend_5d,
    }
