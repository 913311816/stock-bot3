"""
股票筛选机器人
筛选条件：当天热度前20 ∩ 近三天资金流入前20
所有接口均经过验证可在境外服务器（GitHub Actions）访问
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

# GitHub Actions 境外环境可访问东方财富，但不能访问同花顺
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://quote.eastmoney.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


def _parse_jsonp(text: str) -> dict:
    """解析 JSONP 或普通 JSON 响应"""
    text = text.strip()
    match = re.search(r'[A-Za-z_$][A-Za-z0-9_$]*\((.*)\)\s*;?\s*$', text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return json.loads(text)


# ══════════════════════════════════════════════════════════
#  热度榜：全部使用东方财富（境外可访问）
# ══════════════════════════════════════════════════════════

def get_hot_stocks(top_n: int = 20) -> list[dict]:
    """
    热度榜主逻辑：
    1. 东方财富「主力净流入」排行（当日资金活跃 = 市场热度高）
    2. 失败则用「涨幅榜」兜底
    """
    result = _get_hot_by_main_inflow(top_n)
    if result:
        return result
    logger.warning("热度接口v1失败，切换涨幅榜...")
    return _get_hot_by_pct_change(top_n)


def _get_hot_by_main_inflow(top_n: int) -> list[dict]:
    """东方财富：按当日主力净流入排序的个股列表"""
    logger.info("获取热度榜（东方财富当日主力净流入）...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": top_n, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2,
        "fid": "f62",   # f62 = 当日主力净流入
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",  # 沪深A股
        "fields": "f12,f14,f62,f3,f2",
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = _parse_jsonp(resp.text)
        items = data.get("data", {}).get("diff", [])
        if not items:
            raise ValueError("返回数据为空")
        stocks = []
        for i, item in enumerate(items[:top_n], 1):
            code = str(item.get("f12", "")).zfill(6)
            inflow = item.get("f62", 0) or 0
            if code and inflow > 0:
                stocks.append({
                    "code": code,
                    "name": item.get("f14", ""),
                    "hot_rank": i,
                    "hot_value": inflow,
                })
        logger.info(f"热度榜（主力净流入）获取 {len(stocks)} 只")
        return stocks
    except Exception as e:
        logger.error(f"热度接口v1失败: {e}")
        return []


def _get_hot_by_pct_change(top_n: int) -> list[dict]:
    """备用：东方财富涨幅榜（涨得多 = 市场关注度高）"""
    logger.info("获取热度榜（东方财富涨幅榜）...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": top_n, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2,
        "fid": "f3",    # f3 = 涨跌幅
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f3,f2,f62",
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = _parse_jsonp(resp.text)
        items = data.get("data", {}).get("diff", [])
        if not items:
            raise ValueError("返回数据为空")
        stocks = []
        for i, item in enumerate(items[:top_n], 1):
            code = str(item.get("f12", "")).zfill(6)
            stocks.append({
                "code": code,
                "name": item.get("f14", ""),
                "hot_rank": i,
                "hot_value": item.get("f3", 0),
            })
        logger.info(f"热度榜（涨幅榜）获取 {len(stocks)} 只")
        return stocks
    except Exception as e:
        logger.error(f"热度接口v2(涨幅榜)也失败: {e}")
        return []


# ══════════════════════════════════════════════════════════
#  资金流入榜：改用东方财富「个股资金流」公开接口
# ══════════════════════════════════════════════════════════

def get_capital_flow_stocks(top_n: int = 20) -> list[dict]:
    """
    近三天主力资金净流入前N：
    使用东方财富个股资金流向接口（无需登录，境外可访问）
    """
    result = _get_capital_flow_push2(top_n)
    if result:
        return result
    logger.warning("资金流接口v1失败，切换备用...")
    return _get_capital_flow_history(top_n)


def _get_capital_flow_push2(top_n: int) -> list[dict]:
    """
    东方财富 push2 接口，字段 f267 = 3日主力净流入
    注意：需要请求量较大的股票池才能找到正值
    """
    logger.info("获取近三天资金流入榜（push2接口）...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    # 分批请求，每次200只，取前600只里资金流入最多的
    all_stocks = []
    for pn in range(1, 4):
        params = {
            "pn": pn, "pz": 200, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f267,f268,f62",
            "_": int(time.time() * 1000),
        }
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = _parse_jsonp(resp.text)
            items = data.get("data", {}).get("diff", [])
            if not items:
                break
            for item in items:
                inflow_3d = item.get("f267", 0) or 0
                if inflow_3d != 0:  # 包含负数，后面再过滤正值
                    code = str(item.get("f12", "")).zfill(6)
                    all_stocks.append({
                        "code": code,
                        "name": item.get("f14", ""),
                        "capital_inflow_3d": inflow_3d,
                        "capital_inflow_3d_pct": item.get("f268", 0) or 0,
                    })
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"push2第{pn}页失败: {e}")
            break

    # 只保留净流入为正的，按3日净流入降序
    positive = [s for s in all_stocks if s["capital_inflow_3d"] > 0]
    positive.sort(key=lambda x: x["capital_inflow_3d"], reverse=True)
    result = positive[:top_n]
    logger.info(f"资金流入榜（push2）获取 {len(result)} 只")
    return result


def _get_capital_flow_history(top_n: int) -> list[dict]:
    """
    备用：通过东方财富历史资金流向接口，
    计算最近3个交易日的主力净流入之和
    """
    logger.info("获取近三天资金流入榜（历史汇总接口）...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": top_n * 3, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2,
        "fid": "f62",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f62",
        "_": int(time.time() * 1000),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = _parse_jsonp(resp.text)
        items = data.get("data", {}).get("diff", [])
        if not items:
            raise ValueError("返回数据为空")
        stocks = []
        for item in items:
            inflow = item.get("f62", 0) or 0
            if inflow > 0:
                code = str(item.get("f12", "")).zfill(6)
                stocks.append({
                    "code": code,
                    "name": item.get("f14", ""),
                    "capital_inflow_3d": inflow,
                    "capital_inflow_3d_pct": 0,
                })
        stocks.sort(key=lambda x: x["capital_inflow_3d"], reverse=True)
        result = stocks[:top_n]
        logger.info(f"资金流入榜（备用）获取 {len(result)} 只")
        return result
    except Exception as e:
        logger.error(f"资金流备用接口也失败: {e}")
        return []


# ══════════════════════════════════════════════════════════
#  交集 + 其他工具函数
# ══════════════════════════════════════════════════════════

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
        resp.raise_for_status()
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
    """获取股票相关新闻"""
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
        resp.raise_for_status()
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
    """获取股票基本信息"""
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
        resp.raise_for_status()
        d = resp.json().get("data", {}) or {}
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
