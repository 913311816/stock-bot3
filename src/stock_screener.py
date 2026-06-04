"""
股票筛选机器人
数据来源：AKShare（封装了 emappdata.eastmoney.com，GitHub Actions 已验证可用）
筛选逻辑：人气榜前20 ∩ 飙升榜前20
  - 人气榜 stock_hot_rank_em：当前市场热度最高的股票
  - 飙升榜 stock_hot_up_em：近期热度飙升最快的股票（≈资金快速涌入）
"""

import re
import logging
import akshare as ak
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _normalize_code(raw: str) -> str:
    """
    统一股票代码格式为6位纯数字
    输入可能是：'SZ000665' / 'SH600519' / '000665' / '600519'
    """
    raw = str(raw).strip()
    # 去掉市场前缀
    cleaned = re.sub(r'^(SZ|SH|BJ|sz|sh|bj)', '', raw)
    return cleaned.zfill(6)


def get_hot_stocks(top_n: int = 20) -> list[dict]:
    """人气榜前N（东方财富实时热度榜）"""
    logger.info("获取热度榜（东方财富人气榜）...")
    try:
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            raise ValueError("人气榜返回空")
        stocks = []
        for i, row in enumerate(df.head(top_n).itertuples(), 1):
            code = _normalize_code(str(row.代码))
            stocks.append({
                "code": code,
                "name": str(row.股票名称),
                "hot_rank": i,
                "price": float(row.最新价) if hasattr(row, '最新价') and row.最新价 else 0,
                "change_pct": float(row.涨跌幅) if hasattr(row, '涨跌幅') and row.涨跌幅 else 0,
            })
        logger.info(f"人气榜获取 {len(stocks)} 只 | 示例代码: {[s['code'] for s in stocks[:3]]}")
        return stocks
    except Exception as e:
        logger.error(f"人气榜失败: {e}")
        return []


def get_capital_flow_stocks(top_n: int = 20) -> list[dict]:
    """飙升榜前N（近期热度上升最快，与资金涌入高度相关）"""
    logger.info("获取飙升榜（东方财富热度飙升榜）...")
    try:
        df = ak.stock_hot_up_em()
        if df is None or df.empty:
            raise ValueError("飙升榜返回空")
        stocks = []
        for i, row in enumerate(df.head(top_n).itertuples(), 1):
            code = _normalize_code(str(row.代码))
            change = float(row.涨跌幅) if hasattr(row, '涨跌幅') and row.涨跌幅 else 0
            stocks.append({
                "code": code,
                "name": str(row.股票名称),
                "surge_rank": i,
                "capital_inflow_3d": change * 1e8,  # 用涨幅估算，展示用
                "capital_inflow_3d_pct": change,
            })
        logger.info(f"飙升榜获取 {len(stocks)} 只 | 示例代码: {[s['code'] for s in stocks[:3]]}")
        return stocks
    except Exception as e:
        logger.error(f"飙升榜失败: {e}")
        return []


def get_intersection(hot_stocks: list[dict], capital_stocks: list[dict]) -> list[dict]:
    """取人气榜和飙升榜的交集"""
    hot_codes = {s["code"]: s for s in hot_stocks}
    surge_codes = {s["code"]: s for s in capital_stocks}

    # 调试：打印两个榜的代码方便排查
    logger.info(f"人气榜代码: {sorted(hot_codes.keys())}")
    logger.info(f"飙升榜代码: {sorted(surge_codes.keys())}")

    intersection = []
    for code in hot_codes:
        if code in surge_codes:
            intersection.append({**hot_codes[code], **surge_codes[code]})

    logger.info(f"交集结果: {len(intersection)} 只股票")
    for s in intersection:
        logger.info(f"  {s['code']} {s['name']} | 人气排名:{s.get('hot_rank')} | 飙升排名:{s.get('surge_rank','?')}")
    return intersection


def get_stock_market(code: str) -> str:
    return "sh" if code.startswith("6") else "sz"


def get_stock_kline_data(code: str, days: int = 300) -> Optional[pd.DataFrame]:
    """K线数据（AKShare，前复权日线）"""
    try:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"
        })
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index().tail(days)
    except Exception as e:
        logger.error(f"K线数据失败 {code}: {e}")
        return None


def get_stock_news(code: str, name: str) -> list[dict]:
    """个股新闻（AKShare）"""
    try:
        df = ak.stock_news_em(symbol=code)
        if df is None or df.empty:
            return []
        news = []
        for row in df.head(8).itertuples():
            news.append({
                "title": str(getattr(row, "新闻标题", "") or ""),
                "date": str(getattr(row, "发布时间", "") or ""),
                "url": str(getattr(row, "新闻链接", "") or ""),
                "digest": str(getattr(row, "新闻内容", "") or "")[:150],
            })
        return news
    except Exception as e:
        logger.error(f"获取新闻失败 {code}: {e}")
        return []


def get_stock_basic_info(code: str) -> dict:
    """股票基本面数据"""
    def safe_float(val):
        try:
            return float(str(val).replace(",", "").replace("%", "").strip())
        except:
            return 0

    result = {"price": 0, "change_pct": 0, "pe_dynamic": 0, "pe_static": 0,
              "pb": 0, "market_cap": 0, "float_cap": 0, "turnover_rate": 0,
              "52w_high": 0, "52w_low": 0, "volume_ratio": 0}
    try:
        info = ak.stock_individual_info_em(symbol=code)
        if info is not None and not info.empty:
            info_dict = {str(r.iloc[0]): r.iloc[1] for _, r in info.iterrows()}
            result.update({
                "pe_dynamic": safe_float(info_dict.get("市盈率(动态)", 0)),
                "pe_static":  safe_float(info_dict.get("市盈率(静态)", 0)),
                "pb":          safe_float(info_dict.get("市净率", 0)),
                "market_cap":  safe_float(info_dict.get("总市值", 0)) / 1e8,
                "float_cap":   safe_float(info_dict.get("流通市值", 0)) / 1e8,
            })
    except Exception as e:
        logger.warning(f"基本信息失败 {code}: {e}")

    try:
        spot = ak.stock_zh_a_spot_em()
        row = spot[spot["代码"] == code]
        if not row.empty:
            result["price"] = safe_float(row["最新价"].values[0])
            result["change_pct"] = safe_float(row["涨跌幅"].values[0])
            if "换手率" in row.columns:
                result["turnover_rate"] = safe_float(row["换手率"].values[0])
            if "量比" in row.columns:
                result["volume_ratio"] = safe_float(row["量比"].values[0])
    except Exception as e:
        logger.warning(f"实时行情失败 {code}: {e}")

    return result


if __name__ == "__main__":
    hot = get_hot_stocks(20)
    capital = get_capital_flow_stocks(20)
    result = get_intersection(hot, capital)
    print(f"\n最终筛选结果: {len(result)} 只股票")
    for s in result:
        print(f"  {s['code']} {s['name']}")
