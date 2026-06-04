"""
股票筛选机器人
数据源：AKShare（专为境外服务器设计的A股数据库，GitHub Actions 可用）
筛选条件：当天热度前20 ∩ 近三天资金流入前20
"""

import re
import time
import logging
import requests
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  热度榜：新浪财经 + 雪球 热门股票（境外可访问）
# ══════════════════════════════════════════════════════════

def get_hot_stocks(top_n: int = 20) -> list[dict]:
    """热度榜：依次尝试多个境外可访问的接口"""
    for fn, name in [
        (_get_hot_xueqiu, "雪球热帖榜"),
        (_get_hot_akshare_baidu, "百度热搜榜(AKShare)"),
        (_get_hot_akshare_sina, "新浪热门榜(AKShare)"),
    ]:
        try:
            result = fn(top_n)
            if result:
                logger.info(f"热度榜成功来源：{name}，获取 {len(result)} 只")
                return result
        except Exception as e:
            logger.warning(f"{name} 失败: {e}")
    logger.error("所有热度接口均失败")
    return []


def _get_hot_xueqiu(top_n: int) -> list[dict]:
    """雪球热门股票榜（需要先获取cookie）"""
    logger.info("获取热度榜（雪球）...")
    session = requests.Session()
    # 先访问首页获取cookie
    session.get("https://xueqiu.com", timeout=10,
                 headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"})
    time.sleep(1)
    url = "https://stock.xueqiu.com/v5/stock/hot_stock/list.json"
    params = {"size": top_n, "_type": 10, "type": 10}
    resp = session.get(url, params=params, timeout=12,
                       headers={"User-Agent": "Mozilla/5.0", "Referer": "https://xueqiu.com/"})
    resp.raise_for_status()
    data = resp.json()
    items = data.get("data", {}).get("items", [])
    if not items:
        raise ValueError("雪球返回空数据")
    stocks = []
    for i, item in enumerate(items[:top_n], 1):
        code_raw = item.get("code", "")
        code = re.sub(r'^[A-Z]{2}', '', code_raw).zfill(6)
        stocks.append({
            "code": code,
            "name": item.get("name", ""),
            "hot_rank": i,
            "hot_value": item.get("hot", 0),
        })
    return stocks


def _get_hot_akshare_baidu(top_n: int) -> list[dict]:
    """百度股市通热门股票（通过AKShare接口）"""
    logger.info("获取热度榜（百度热搜/AKShare）...")
    import akshare as ak
    df = ak.stock_hot_search_baidu(symbol="A股", date=datetime.now().strftime("%Y-%m-%d"), time="今日")
    if df is None or df.empty:
        raise ValueError("百度热搜返回空")
    stocks = []
    for i, row in enumerate(df.head(top_n).itertuples(), 1):
        code = str(getattr(row, '代码', '') or getattr(row, 'code', '')).zfill(6)
        name = str(getattr(row, '名称', '') or getattr(row, 'name', ''))
        if code and name:
            stocks.append({"code": code, "name": name, "hot_rank": i, "hot_value": i})
    return stocks


def _get_hot_akshare_sina(top_n: int) -> list[dict]:
    """新浪热门A股（AKShare）"""
    logger.info("获取热度榜（新浪/AKShare）...")
    import akshare as ak
    df = ak.stock_hot_rank_em()  # 东方财富人气榜（AKShare封装版，处理了境外访问）
    if df is None or df.empty:
        raise ValueError("AKShare东方财富人气榜返回空")
    stocks = []
    for i, row in enumerate(df.head(top_n).itertuples(), 1):
        code = str(getattr(row, '代码', '')).zfill(6)
        name = str(getattr(row, '名称', ''))
        stocks.append({"code": code, "name": name, "hot_rank": i, "hot_value": i})
    return stocks


# ══════════════════════════════════════════════════════════
#  资金流入榜：AKShare 东方财富资金流向（境外可用）
# ══════════════════════════════════════════════════════════

def get_capital_flow_stocks(top_n: int = 20) -> list[dict]:
    """近三天主力资金净流入前N：使用AKShare"""
    for fn, name in [
        (_get_capital_akshare_3d, "AKShare-3日资金流"),
        (_get_capital_akshare_today, "AKShare-今日资金流"),
    ]:
        try:
            result = fn(top_n)
            if result:
                logger.info(f"资金流榜成功来源：{name}，获取 {len(result)} 只")
                return result
        except Exception as e:
            logger.warning(f"{name} 失败: {e}")
    logger.error("所有资金流接口均失败")
    return []


def _get_capital_akshare_3d(top_n: int) -> list[dict]:
    """AKShare 个股资金流向-3日（东方财富数据源，AKShare已处理境外访问）"""
    logger.info("获取近三天资金流入榜（AKShare 3日）...")
    import akshare as ak
    df = ak.stock_individual_fund_flow_rank(indicator="3日")
    if df is None or df.empty:
        raise ValueError("AKShare 3日资金流返回空")

    # 找到主力净流入列（不同版本列名可能不同）
    inflow_col = None
    for col in df.columns:
        if "主力" in col and "净" in col:
            inflow_col = col
            break
    if not inflow_col:
        # 取第一个包含"净"的列
        for col in df.columns:
            if "净" in col:
                inflow_col = col
                break
    if not inflow_col:
        raise ValueError(f"找不到资金流入列，现有列: {list(df.columns)}")

    logger.info(f"使用资金流列: {inflow_col}")
    df[inflow_col] = pd.to_numeric(df[inflow_col], errors='coerce').fillna(0)
    df = df[df[inflow_col] > 0].sort_values(inflow_col, ascending=False)

    stocks = []
    for row in df.head(top_n).itertuples():
        code = str(getattr(row, '代码', '') or getattr(row, 'code', '')).zfill(6)
        name = str(getattr(row, '名称', '') or getattr(row, 'name', ''))
        inflow = float(getattr(row, inflow_col, 0) or 0)
        if code:
            stocks.append({
                "code": code,
                "name": name,
                "capital_inflow_3d": inflow * 1e4,  # AKShare单位是万元，转为元
                "capital_inflow_3d_pct": 0,
            })
    return stocks


def _get_capital_akshare_today(top_n: int) -> list[dict]:
    """备用：AKShare 今日资金流向"""
    logger.info("获取资金流入榜（AKShare 今日）...")
    import akshare as ak
    df = ak.stock_individual_fund_flow_rank(indicator="今日")
    if df is None or df.empty:
        raise ValueError("AKShare 今日资金流返回空")

    inflow_col = None
    for col in df.columns:
        if "主力" in col and "净" in col:
            inflow_col = col
            break
    if not inflow_col:
        for col in df.columns:
            if "净" in col:
                inflow_col = col
                break
    if not inflow_col:
        raise ValueError(f"找不到资金流入列: {list(df.columns)}")

    df[inflow_col] = pd.to_numeric(df[inflow_col], errors='coerce').fillna(0)
    df = df[df[inflow_col] > 0].sort_values(inflow_col, ascending=False)

    stocks = []
    for row in df.head(top_n).itertuples():
        code = str(getattr(row, '代码', '') or getattr(row, 'code', '')).zfill(6)
        name = str(getattr(row, '名称', '') or getattr(row, 'name', ''))
        inflow = float(getattr(row, inflow_col, 0) or 0)
        if code:
            stocks.append({
                "code": code,
                "name": name,
                "capital_inflow_3d": inflow * 1e4,
                "capital_inflow_3d_pct": 0,
            })
    return stocks


# ══════════════════════════════════════════════════════════
#  交集 + K线 + 新闻 + 基本面（AKShare）
# ══════════════════════════════════════════════════════════

def get_intersection(hot_stocks: list[dict], capital_stocks: list[dict]) -> list[dict]:
    hot_codes = {s["code"]: s for s in hot_stocks}
    capital_codes = {s["code"]: s for s in capital_stocks}
    intersection = []
    for code in hot_codes:
        if code in capital_codes:
            intersection.append({**hot_codes[code], **capital_codes[code]})
    logger.info(f"交集结果: {len(intersection)} 只股票")
    for s in intersection:
        logger.info(f"  {s['code']} {s['name']} | 热度:{s.get('hot_rank')} | 3日流入:{s.get('capital_inflow_3d',0)/1e8:.2f}亿")
    return intersection


def get_stock_market(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    return "sz"


def get_stock_kline_data(code: str, days: int = 300) -> Optional[pd.DataFrame]:
    """获取K线数据（AKShare，境外可用）"""
    logger.info(f"获取K线数据: {code}")
    try:
        import akshare as ak
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty:
            return None
        # 统一列名
        col_map = {"日期": "date", "开盘": "open", "收盘": "close",
                   "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"}
        df = df.rename(columns=col_map)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df.tail(days)
    except Exception as e:
        logger.error(f"K线数据失败 {code}: {e}")
        return None


def get_stock_news(code: str, name: str) -> list[dict]:
    """获取个股新闻（AKShare）"""
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
        if df is None or df.empty:
            return []
        news = []
        for row in df.head(8).itertuples():
            news.append({
                "title": str(getattr(row, '新闻标题', '') or ''),
                "date": str(getattr(row, '发布时间', '') or ''),
                "url": str(getattr(row, '新闻链接', '') or ''),
                "digest": str(getattr(row, '新闻内容', '') or '')[:150],
            })
        return news
    except Exception as e:
        logger.error(f"获取新闻失败 {code}: {e}")
        return []


def get_stock_basic_info(code: str) -> dict:
    """获取股票基本面数据（AKShare）"""
    try:
        import akshare as ak
        # 实时行情
        market = get_stock_market(code)
        symbol = f"{'sh' if market == 'sh' else 'sz'}{code}"
        df = ak.stock_bid_ask_em(symbol=code)
        # 用个股信息接口
        info = ak.stock_individual_info_em(symbol=code)
        info_dict = {}
        if info is not None and not info.empty:
            for _, row in info.iterrows():
                info_dict[str(row.iloc[0])] = row.iloc[1]

        # 实时价格
        spot = ak.stock_zh_a_spot_em()
        row = spot[spot['代码'] == code]
        price = float(row['最新价'].values[0]) if not row.empty else 0
        change_pct = float(row['涨跌幅'].values[0]) if not row.empty else 0
        turnover = float(row['换手率'].values[0]) if not row.empty else 0
        volume_ratio = float(row['量比'].values[0]) if not row.empty and '量比' in row.columns else 0

        def safe_float(val):
            try: return float(str(val).replace(',', '').replace('%', ''))
            except: return 0

        return {
            "price": price,
            "change_pct": change_pct,
            "pe_dynamic": safe_float(info_dict.get("市盈率(动态)", 0)),
            "pe_static": safe_float(info_dict.get("市盈率(静态)", 0)),
            "pb": safe_float(info_dict.get("市净率", 0)),
            "market_cap": safe_float(info_dict.get("总市值", 0)) / 1e8,
            "float_cap": safe_float(info_dict.get("流通市值", 0)) / 1e8,
            "turnover_rate": turnover,
            "52w_high": 0,
            "52w_low": 0,
            "volume_ratio": volume_ratio,
        }
    except Exception as e:
        logger.error(f"获取基本信息失败 {code}: {e}")
        return {}
