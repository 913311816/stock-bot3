"""
股票筛选机器人 - 主程序
筛选条件：当天热度前20 ∩ 近三天资金流入前20
"""

import os
import json
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.eastmoney.com/',
    'Accept': 'application/json, text/plain, */*',
}


def get_hot_stocks(top_n: int = 20) -> list[dict]:
    """获取东方财富人气榜 - 热度前N股票"""
    logger.info("获取热度榜单...")
    url = "https://emappdata.eastmoney.com/stockact/getAllCurrentList"
    params = {
        "appId": "appId01",
        "pageIndex": 1,
        "pageSize": 100,
    }
    try:
        resp = requests.post(url, json=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        stocks = []
        if data.get("success") and data.get("data"):
            for item in data["data"][:top_n]:
                stocks.append({
                    "code": item.get("sc", ""),
                    "name": item.get("sn", ""),
                    "hot_rank": item.get("rank", 0),
                    "hot_value": item.get("mark", 0),
                })
        logger.info(f"热度榜获取 {len(stocks)} 只股票")
        return stocks
    except Exception as e:
        logger.error(f"获取热度榜失败: {e}")
        return _get_hot_stocks_fallback(top_n)


def _get_hot_stocks_fallback(top_n: int = 20) -> list[dict]:
    """备用：东方财富热门股票接口"""
    logger.info("使用备用热度接口...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "cb": "jQuery",
        "pn": 1,
        "pz": top_n,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f62",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13",
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        text = resp.text
        import re
        match = re.search(r'jQuery\d*\((.*)\)', text)
        if match:
            data = json.loads(match.group(1))
            items = data.get("data", {}).get("diff", [])
            stocks = []
            for i, item in enumerate(items[:top_n]):
                code = str(item.get("f12", "")).zfill(6)
                stocks.append({
                    "code": code,
                    "name": item.get("f14", ""),
                    "hot_rank": i + 1,
                    "hot_value": item.get("f62", 0),
                })
            logger.info(f"备用接口获取 {len(stocks)} 只股票")
            return stocks
    except Exception as e:
        logger.error(f"备用热度接口也失败: {e}")
    return []


def get_capital_flow_stocks(top_n: int = 20) -> list[dict]:
    """获取近三天主力资金净流入前N股票（东方财富）"""
    logger.info("获取近三天资金流入榜单...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "cb": "jQuery",
        "pn": 1,
        "pz": 100,
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2,
        "invt": 2,
        "fid": "f267",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f2,f3,f267,f268,f269,f270,f271,f272,f273,f274,f275,f276",
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        text = resp.text
        import re
        match = re.search(r'jQuery\d*\((.*)\)', text)
        if not match:
            raise ValueError("响应格式错误")
        data = json.loads(match.group(1))
        items = data.get("data", {}).get("diff", [])

        stocks = []
        for item in items:
            inflow_3d = item.get("f267", 0) or 0
            if inflow_3d > 0:
                code = str(item.get("f12", "")).zfill(6)
                stocks.append({
                    "code": code,
                    "name": item.get("f14", ""),
                    "capital_inflow_3d": inflow_3d,
                    "capital_inflow_3d_pct": item.get("f268", 0),
                })

        stocks.sort(key=lambda x: x["capital_inflow_3d"], reverse=True)
        result = stocks[:top_n]
        logger.info(f"资金流入榜获取 {len(result)} 只股票")
        return result
    except Exception as e:
        logger.error(f"获取资金流入榜失败: {e}")
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
    """判断股票市场（sh/sz）"""
    if code.startswith("6"):
        return "sh"
    elif code.startswith(("0", "3")):
        return "sz"
    elif code.startswith("8") or code.startswith("4"):
        return "bj"
    return "sh"


def get_stock_kline_data(code: str, days: int = 300) -> Optional[pd.DataFrame]:
    """获取股票K线数据（日线）"""
    market = get_stock_market(code)
    secid = f"{'1' if market == 'sh' else '0'}.{code}"
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "cb": "jQuery",
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": 101,
        "fqt": 1,
        "end": "20500101",
        "lmt": days,
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        import re
        match = re.search(r'jQuery\d*\((.*)\)', resp.text)
        if not match:
            return None
        data = json.loads(match.group(1))
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None

        records = []
        for k in klines:
            parts = k.split(",")
            records.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]),
            })

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df
    except Exception as e:
        logger.error(f"获取K线数据失败 {code}: {e}")
        return None


def get_stock_news(code: str, name: str) -> list[dict]:
    """获取股票相关新闻"""
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {
        "cb": "jQuery",
        "param": json.dumps({
            "uid": "",
            "keyword": name,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "time",
                    "pageIndex": 1,
                    "pageSize": 10,
                    "preTag": "<em>",
                    "postTag": "</em>",
                }
            }
        }),
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        import re
        match = re.search(r'jQuery\d*\((.*)\)', resp.text)
        if not match:
            return []
        data = json.loads(match.group(1))
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
        "invt": 2,
        "fltt": 2,
        "fields": "f57,f58,f107,f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f55,f57,f58,f59,f60,f85,f86,f92,f105,f116,f117,f162,f163,f164,f165,f167,f168,f169,f170,f171",
        "secid": secid,
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        d = data.get("data", {})
        return {
            "price": d.get("f43", 0) / 100 if d.get("f43") else 0,
            "change_pct": d.get("f170", 0) / 100 if d.get("f170") else 0,
            "pe_dynamic": d.get("f162", 0) / 100 if d.get("f162") else 0,
            "pe_static": d.get("f163", 0) / 100 if d.get("f163") else 0,
            "pb": d.get("f167", 0) / 100 if d.get("f167") else 0,
            "market_cap": d.get("f116", 0) / 1e8 if d.get("f116") else 0,
            "float_cap": d.get("f117", 0) / 1e8 if d.get("f117") else 0,
            "turnover_rate": d.get("f168", 0) / 100 if d.get("f168") else 0,
            "52w_high": d.get("f44", 0) / 100 if d.get("f44") else 0,
            "52w_low": d.get("f45", 0) / 100 if d.get("f45") else 0,
            "volume_ratio": d.get("f50", 0) / 100 if d.get("f50") else 0,
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
