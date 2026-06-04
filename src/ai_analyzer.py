import logging
import os

import requests

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def analyze_stock(stock: dict, basic_info: dict, news_list: list[dict], kline_summary: dict) -> str:
    if not DEEPSEEK_API_KEY:
        return fallback_analysis(stock, basic_info, news_list, kline_summary)

    news_text = "\n".join(
        f"{idx}. [{item.get('date', '')}] {item.get('title', '')}\n{item.get('digest', '')}"
        for idx, item in enumerate(news_list[:6], start=1)
    )
    if not news_text:
        news_text = "No recent Eastmoney news was returned by the data API."

    prompt = f"""
你是一名谨慎的A股研究员。请基于下面的数据，写一份中文深度报告。

股票: {stock.get('name')} ({stock.get('code')})
人气排名: #{stock.get('hot_rank')}
近3日主力净流入排名: #{stock.get('capital_rank')}
近3日主力净流入: {stock.get('capital_inflow_3d', 0) / 1e8:.2f} 亿元
近3日主力净流入占比: {stock.get('capital_inflow_3d_pct', 0):.2f}%

技术面:
- 最新价: {kline_summary.get('last_price', 'N/A')}
- 当日涨跌幅: {kline_summary.get('change_pct', 'N/A')}%
- MA5: {kline_summary.get('ma5', 'N/A')}
- MA10: {kline_summary.get('ma10', 'N/A')}
- MA28: {kline_summary.get('ma28', 'N/A')}
- MA250: {kline_summary.get('ma250', 'N/A')}
- 与年线关系: {kline_summary.get('vs_ma250', 'N/A')}
- 近5日涨跌幅: {kline_summary.get('trend_5d', 'N/A')}%

基本面:
- 行业: {basic_info.get('industry', '')}
- 总市值: {basic_info.get('market_cap', 0):.1f} 亿元
- 流通市值: {basic_info.get('float_cap', 0):.1f} 亿元
- 动态PE: {basic_info.get('pe_dynamic', 0):.1f}
- PB: {basic_info.get('pb', 0):.2f}
- 换手率: {basic_info.get('turnover_rate', 0):.2f}%
- 量比: {basic_info.get('volume_ratio', 0):.2f}

近期资讯:
{news_text}

请输出5个部分，每部分80到150字：
1. 热度高的原因，明确说明它正在炒什么题材或事件
2. 近3日资金流入逻辑
3. 技术面分析，必须提到MA5/MA10/MA28/MA250
4. 基本面简评
5. 主要风险

语气客观，不要给买入卖出指令，不构成投资建议。
"""

    try:
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1800},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("DeepSeek analysis failed for %s: %s", stock.get("code"), exc)
        return fallback_analysis(stock, basic_info, news_list, kline_summary)


def fallback_analysis(stock: dict, basic_info: dict, news_list: list[dict], kline_summary: dict) -> str:
    titles = "\n".join(f"- {item.get('title', '')}" for item in news_list[:5]) or "- 暂无接口返回的近期资讯"
    return f"""
### 1. 热度高的原因
该股进入东方财富人气榜第 {stock.get('hot_rank')} 名，说明短线关注度较高。近期资讯线索如下：
{titles}

### 2. 近3日资金流入逻辑
该股近3日主力净流入排名第 {stock.get('capital_rank')} 名，净流入约 {stock.get('capital_inflow_3d', 0) / 1e8:.2f} 亿元，净占比约 {stock.get('capital_inflow_3d_pct', 0):.2f}%。

### 3. 技术面分析
最新价 {kline_summary.get('last_price', 'N/A')}，MA5 {kline_summary.get('ma5', 'N/A')}，MA10 {kline_summary.get('ma10', 'N/A')}，MA28 {kline_summary.get('ma28', 'N/A')}，MA250 {kline_summary.get('ma250', 'N/A')}，价格目前 {kline_summary.get('vs_ma250', 'N/A')}。

### 4. 基本面简评
行业为 {basic_info.get('industry', '') or '未知'}，总市值约 {basic_info.get('market_cap', 0):.1f} 亿元，动态PE {basic_info.get('pe_dynamic', 0):.1f}，PB {basic_info.get('pb', 0):.2f}。

### 5. 主要风险
热门股波动通常较大，资金流入不等于后续价格必然上涨；如果题材热度退潮、成交量萎缩或跌破关键均线，短线风险会明显上升。本报告仅供研究参考，不构成投资建议。
""".strip()
