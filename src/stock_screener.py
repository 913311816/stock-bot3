"""
股票筛选机器人 - 主程序
筛选条件：当天热度前20 ∩ 近三天资金流入前20
"""

import re
import json
import time
import logging
import requests
import pandas as pd
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://quote.eastmoney.com/',
    'Accept': 'application/json, text/plain, */*',
}


def _parse_jsonp(text: str) -> dict:
    """解析 JSONP 响应，兼容多种回调名格式"""
    # 尝试标准 JSONP
    match = re.search(r'[A-Za-z_$][A-Za-z0-9_$]*\((.*)\)\s*;?\s*$', text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # 尝试直接 JSON
    return json.loads(text)


def get_hot_stocks(top_n: int = 20) -> list[dict]:
    """
    热度榜：优先用同花顺人气榜，失败则回落到东方财富资金活跃榜
    """
    result = _get_hot_ths(top_n)
    if result:
        return result
    logger.warning("同花顺热度接口失败，切换备用...")
    return _get_hot_eastmoney_active(top_n)


def _get_hot_ths(top_n: int) -> list[dict]:
    """同花顺热门股票榜"""
    logger.info("获取热度榜单（同花顺）...")
    url = "https://apphq.10jqka.com.cn/wap/hotrank/rank_data.json"
    params = {"page": 1, "limit": top_n, "type": "hot"}
    try:
        resp = requests.get(url, params=params, headers={
            **HEADERS,
            'Referer': 'https://www.10jqka.com.cn/',
        }, timeout=12)
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        if not items:
            return []
        stocks = []
        for i, item in enumerate(items[:top_n], 1):
            code = str(item.get("code", "")).zfill(6)
            if code:
                stocks.append({
                    "code": code,
                    "name": item.get("name", ""),
                    "hot_rank": i,
                    "hot_value": item.get("hot", 0),
                })
        logger.info(f"同花顺热度榜获取 {len(stocks)} 只")
        return stocks
    except Exception as e:
        logger.error(f"同花顺接口失败: {e}")
        return []


def _get_hot_eastmoney_active(top_n: int) -> list[dict]:
    """
    东方财富：按当日主力净流入排序，作为热度榜备用
    （当日资金活跃 = 市场关注度高）
    """
    logger.info("获取热度榜单（东方财富当日资金活跃）...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": top_n, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2,
        "fid": "f62",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f62,f3",
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
        data = _parse_jsonp(resp.text)
        items = data.get("data", {}).get("diff", [])
        stocks = []
        for i, item in enumerate(items[:top_n], 1):
            code = str(item.get("f12", "")).zfill(6)
            stocks.append({
                "code": code,
                "name": item.get("f14", ""),
                "hot_rank": i,
                "hot_value": item.get("f62", 0),
            })
        logger.info(f"东方财富活跃榜获取 {len(stocks)} 只")
        return stocks
    except Exception as e:
        logger.error(f"东方财富活跃榜也失败: {e}")
        return []


def get_capital_flow_stocks(top_n: int = 20) -> list[dict]:
    """
    近三天主力资金净流入前N：
    优先用东方财富资金流向专题接口，失败则用通用列表接口
    """
    result = _get_capital_flow_v2(top_n)
    if result:
        return result
    logger.warning("资金流接口v2失败，切换备用...")
    return _get_capital_flow_v1(top_n)


def _get_capital_flow_v2(top_n: int) -> list[dict]:
    """东方财富 个股资金流向 专题页接口（更稳定）"""
    logger.info("获取近三天资金流入榜（东方财富专题）...")
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPT_MUTUAL_STOCK_NORTHDATE",
        "columns": "ALL",
        "pageNumber": 1,
        "pageSize": top_n,
        "sortColumns": "INTERVAL3_MAIN_NET_INFLOW",
        "sortTypes": -1,
        "source": "WEB",
        "client": "WEB",
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
        data = resp.json()
        items = data.get("result", {}).get("data", [])
        if not items:
            raise ValueError("无数据")
        stocks = []
        for item in items[:top_n]:
            inflow = item.get("INTERVAL3_MAIN_NET_INFLOW", 0) or 0
            if inflow > 0:
                code = str(item.get("SECURITY_CODE", "")).zfill(6)
                stocks.append({
                    "code": code,
                    "name": item.get("SECURITY_NAME_ABBR", ""),
                    "capital_inflow_3d": inflow,
                    "capital_inflow_3d_pct": item.get("INTERVAL3_MAIN_NET_INFLOW_RATE", 0),
                })
        stocks.sort(key=lambda x: x["capital_inflow_3d"], reverse=True)
        logger.info(f"资金流入榜v2获取 {len(stocks)} 只")
        return stocks[:top_n]
    except Exception as e:
        logger.error(f"资金流v2失败: {e}")
        return []


def _get_capital_flow_v1(top_n: int) -> list[dict]:
    """备用：东方财富 push2 列表接口，按3日净流入排序"""
    logger.info("获取近三天资金流入榜（东方财富列表）...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": 200, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2,
        "fid": "f267",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f267,f268",
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
        data = _parse_jsonp(resp.text)
        items = data.get("data", {}).get("diff", [])
        if not items:
            raise ValueError("无数据")
        stocks = []
        for item in items:
            inflow = item.get("f267", 0) or 0
            if inflow > 0:
                code = str(item.get("f12", "")).zfill(6)
                stocks.append({
                    "code": code,
                    "name": item.get("f14", ""),
                    "capital_inflow_3d": inflow,
                    "capital_inflow_3d_pct": item.get("f268", 0),
                })
        stocks.sort(key=lambda x: x["capital_inflow_3d"], reverse=True)
        logger.info(f"资金流入榜v1获取 {len(stocks[:top_n])} 只")
        return stocks[:top_n]
    except Exception as e:
        logger.error(f"资金流v1也失败: {e}")
        return []


def get_intersection(hot_stocks: list[dict], capital_stocks: list[dict]) -> list[dict]:
    """取热度榜和资金流入榜的交集"""
    hot_codes = {s["code"]: s for s in hot_stocks}
    capital_codes = {s["code"]: s for s in capital_stocks}

    intersection = []
    for code in hot_codes:
        if code in capital_codes:
            merged = {**hot_codes[code], **capital_codes[code]}
            intersection.append(merged)

    logger.info(f"交集结果: {len(intersection)} 只股票")
    for s in intersection:
        logger.info(f"  {s['code']} {s['name']} | 热度排名:{s.get('hot_rank')} | 3日资金流入:{s.get('capital_inflow_3d', 0)/1e8:.2f}亿")
    return intersection


def get_stock_market(code: str) -> str:
    if code.startswith("6"):
        return "sh"
    elif code.startswith(("0", "3")):
        return "sz"
    return "sh"


def get_stock_kline_data(code: str, days: int = 300) -> Optional[pd.DataFrame]:
    """获取股票K线数据（日线，前复权）"""
    market = get_stock_market(code)
    secid = f"{'1' if market == 'sh' else '0'}.{code}"
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": 101, "fqt": 1,
        "end": "20500101", "lmt": days,
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = _parse_jsonp(resp.text)
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None
        records = []
        for k in klines:
            p = k.split(",")
            records.append({
                "date": p[0], "open": float(p[1]), "close": float(p[2]),
                "high": float(p[3]), "low": float(p[4]),
                "volume": float(p[5]), "amount": float(p[6]),
            })
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()
    except Exception as e:
        logger.error(f"获取K线数据失败 {code}: {e}")
        return None


def get_stock_news(code: str, name: str) -> list[dict]:
    """获取股票相关新闻（东方财富资讯）"""
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {
        "cb": "jQuery",
        "param": json.dumps({
            "uid": "", "keyword": name,
            "type": ["cmsArticleWebOld"],
            "client": "web", "clientType": "web", "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {
                "searchScope": "default", "sort": "time",
                "pageIndex": 1, "pageSize": 10,
                "preTag": "<em>", "postTag": "</em>",
            }},
        }),
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
        data = _parse_jsonp(resp.text)
        articles = data.get("result", {}).get("cmsArticleWebOld", {}).get("data", [])
        news = []
        for a in articles[:8]:
            title = re.sub(r'<[^>]+>', '', a.get("title", ""))
            news.append({
                "title": title,
                "date": a.get("date", ""),
                "url": a.get("url", ""),
                "digest": re.sub(r'<[^>]+>', '', a.get("digest", "")),
            })
        return news
    except Exception as e:
        logger.error(f"获取新闻失败 {code}: {e}")
        return []


def get_stock_basic_info(code: str) -> dict:
    """获取股票基本信息（市盈率、市值等）"""
    market = get_stock_market(code)
    secid = f"{'1' if market == 'sh' else '0'}.{code}"
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "invt": 2, "fltt": 2,
        "fields": "f43,f44,f45,f50,f116,f117,f162,f163,f167,f168,f170",
        "secid": secid,
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
        d = resp.json().get("data", {})
        def v(key, div=100): return d.get(key, 0) / div if d.get(key) else 0
        return {
            "price": v("f43"), "change_pct": v("f170"),
            "pe_dynamic": v("f162"), "pe_static": v("f163"),
            "pb": v("f167"), "market_cap": v("f116", 1e8),
            "float_cap": v("f117", 1e8), "turnover_rate": v("f168"),
            "52w_high": v("f44"), "52w_low": v("f45"),
            "volume_ratio": v("f50"),
        }
    except Exception as e:
        logger.error(f"获取基本信息失败 {code}: {e}")
        return {}


if __name__ == "__main__":
    hot = get_hot_stocks(20)
    capital = get_capital_flow_stocks(20)
    result = get_intersection(hot, capital)
    print(f"\n最终筛选结果: {len(result)} 只股票")
    for s in result:
        print(f"  {s['code']} {s['name']}")
