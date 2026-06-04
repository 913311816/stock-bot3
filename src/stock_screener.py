"""
股票筛选机器人
数据来源：全部使用 emappdata.eastmoney.com（已验证GitHub Actions可访问）
筛选逻辑：人气榜前20 ∩ 飙升榜前20
  - 人气榜：当前市场热度排名（实时关注人数）
  - 飙升榜：近期热度上升最快的股票（热度加速 ≈ 资金快速涌入）
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

EM_BASE = "https://emappdata.eastmoney.com/stockrank"
EM_PAYLOAD_BASE = {
    "appId": "appId01",
    "globalId": "786e4c21-70dc-435a-93bb-38",
    "marketType": "",
    "pageNo": 1,
    "pageSize": 100,
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
}


def _em_post(endpoint: str, extra: dict = {}) -> dict:
    """统一请求 emappdata 接口"""
    payload = {**EM_PAYLOAD_BASE, **extra}
    r = requests.post(f"{EM_BASE}/{endpoint}", json=payload,
                      headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("data"):
        raise ValueError(f"接口 {endpoint} 返回空数据: {data}")
    return data


def _enrich_with_price(rank_df: pd.DataFrame) -> pd.DataFrame:
    """
    用 emappdata push2 ulist 接口补充价格和涨跌幅数据
    rank_df 需要包含 mark 列（格式：1.600519 或 0.000001）
    """
    marks = ",".join(rank_df["mark"].tolist())
    params = {
        "ut": "f057cbcbce2a86e2866ab8877db1d059",
        "fltt": "2", "invt": "2",
        "fields": "f14,f3,f12,f2,f62",
        "secids": marks + ",?v=08926209912590994",
    }
    try:
        r = requests.get("https://push2.eastmoney.com/api/qt/ulist.np/get",
                         params=params, headers=HEADERS, timeout=12)
        r.raise_for_status()
        diff = r.json().get("data", {}).get("diff", [])
        price_map = {}
        for item in diff:
            code = str(item.get("f12", "")).zfill(6)
            price_map[code] = {
                "price": (item.get("f2") or 0) / 100,
                "change_pct": (item.get("f3") or 0) / 100,
                "today_inflow": item.get("f62") or 0,
            }
        return price_map
    except Exception as e:
        logger.warning(f"补充价格数据失败（不影响主流程）: {e}")
        return {}


def _parse_em_rank_data(data: dict, rank_field: str = "rk") -> tuple[pd.DataFrame, list[dict]]:
    """
    解析 emappdata 人气/飙升榜数据，返回 (rank_df, stocks)
    rank_df 包含 mark 列，用于后续补充价格
    """
    items = data["data"]
    rank_df_rows = []
    for item in items:
        sc = item.get("sc", "")
        market_prefix = "0" if sc.startswith("SZ") else "1"
        pure_code = sc[2:] if sc[:2] in ("SZ", "SH") else sc
        mark = f"{market_prefix}.{pure_code}"
        rank_df_rows.append({
            "sc": sc,
            "mark": mark,
            "code": pure_code.zfill(6),
            "name": item.get("sn", ""),
            "rank": item.get(rank_field, 0),
            "hot": item.get("mk", item.get("mark", 0)),
        })
    rank_df = pd.DataFrame(rank_df_rows)
    return rank_df


# ══════════════════════════════════════════════════════════
#  热度榜：emappdata 人气榜（实时热度排名）
# ══════════════════════════════════════════════════════════

def get_hot_stocks(top_n: int = 20) -> list[dict]:
    """人气榜前N（当前市场最受关注的股票）"""
    logger.info("获取热度榜（东方财富人气榜）...")
    try:
        data = _em_post("getAllCurrentList")
        rank_df = _parse_em_rank_data(data)
        rank_df = rank_df.head(top_n)

        # 补充价格信息
        price_map = _enrich_with_price(rank_df)

        stocks = []
        for i, row in enumerate(rank_df.itertuples(), 1):
            p = price_map.get(row.code, {})
            stocks.append({
                "code": row.code,
                "name": row.name,
                "hot_rank": i,
                "hot_value": row.hot,
                "price": p.get("price", 0),
                "change_pct": p.get("change_pct", 0),
            })
        logger.info(f"人气榜获取 {len(stocks)} 只股票")
        return stocks
    except Exception as e:
        logger.error(f"人气榜获取失败: {e}")
        return []


# ══════════════════════════════════════════════════════════
#  资金流入榜：emappdata 飙升榜（热度急速上升 = 资金快速涌入）
# ══════════════════════════════════════════════════════════

def get_capital_flow_stocks(top_n: int = 20) -> list[dict]:
    """
    飙升榜前N（近期热度上升最快的股票）
    飙升榜逻辑 = 短期内被大量新增关注的股票 ≈ 资金正在快速涌入的股票
    """
    logger.info("获取飙升榜（东方财富热度飙升榜）...")
    try:
        data = _em_post("getAllHisRcList")
        rank_df = _parse_em_rank_data(data, rank_field="rk")
        rank_df = rank_df.head(top_n)

        price_map = _enrich_with_price(rank_df)

        stocks = []
        for i, row in enumerate(rank_df.itertuples(), 1):
            p = price_map.get(row.code, {})
            # capital_inflow_3d 用今日主力净流入估算（或热度值）
            inflow = p.get("today_inflow", 0) or (row.hot * 1000)
            stocks.append({
                "code": row.code,
                "name": row.name,
                "capital_inflow_3d": inflow,
                "capital_inflow_3d_pct": 0,
                "surge_rank": i,
            })
        logger.info(f"飙升榜获取 {len(stocks)} 只股票")
        return stocks
    except Exception as e:
        logger.error(f"飙升榜获取失败: {e}")
        # 最终兜底：用 AKShare hot_rank_em 返回数据里涨幅最大的20只
        return _fallback_by_akshare(top_n)


def _fallback_by_akshare(top_n: int) -> list[dict]:
    """终极兜底：AKShare人气榜 + 按涨幅筛选"""
    logger.info("使用AKShare兜底（人气榜中涨幅最大的股票）...")
    try:
        import akshare as ak
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            return []
        df["涨跌幅"] = pd.to_numeric(df.get("涨跌幅", df.iloc[:, -1]), errors="coerce").fillna(0)
        df = df[df["涨跌幅"] > 0].sort_values("涨跌幅", ascending=False)
        stocks = []
        for i, row in enumerate(df.head(top_n).itertuples(), 1):
            code = str(getattr(row, "代码", "")).replace("SZ", "").replace("SH", "").zfill(6)
            stocks.append({
                "code": code,
                "name": str(getattr(row, "股票名称", "")),
                "capital_inflow_3d": float(getattr(row, "涨跌幅", 0)) * 1e8,
                "capital_inflow_3d_pct": 0,
            })
        logger.info(f"AKShare兜底获取 {len(stocks)} 只")
        return stocks
    except Exception as e:
        logger.error(f"AKShare兜底也失败: {e}")
        return []


# ══════════════════════════════════════════════════════════
#  交集
# ══════════════════════════════════════════════════════════

def get_intersection(hot_stocks: list[dict], capital_stocks: list[dict]) -> list[dict]:
    """取人气榜和飙升榜的交集"""
    hot_codes = {s["code"]: s for s in hot_stocks}
    capital_codes = {s["code"]: s for s in capital_stocks}
    intersection = []
    for code in hot_codes:
        if code in capital_codes:
            intersection.append({**hot_codes[code], **capital_codes[code]})
    logger.info(f"交集结果: {len(intersection)} 只股票")
    for s in intersection:
        logger.info(f"  {s['code']} {s['name']} | 人气排名:{s.get('hot_rank')} | 飙升排名:{s.get('surge_rank','?')}")
    return intersection


# ══════════════════════════════════════════════════════════
#  K线、新闻、基本面（AKShare，GitHub Actions可用）
# ══════════════════════════════════════════════════════════

def get_stock_market(code: str) -> str:
    return "sh" if code.startswith("6") else "sz"


def get_stock_kline_data(code: str, days: int = 300) -> Optional[pd.DataFrame]:
    """K线数据（AKShare，前复权日线）"""
    try:
        import akshare as ak
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty:
            return None
        df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                                "最高": "high", "最低": "low",
                                "成交量": "volume", "成交额": "amount"})
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index().tail(days)
    except Exception as e:
        logger.error(f"K线数据失败 {code}: {e}")
        return None


def get_stock_news(code: str, name: str) -> list[dict]:
    """个股新闻（AKShare东方财富）"""
    try:
        import akshare as ak
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
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=code)
        info_dict = {}
        if info is not None and not info.empty:
            for _, row in info.iterrows():
                info_dict[str(row.iloc[0])] = row.iloc[1]

        def safe_float(val):
            try:
                return float(str(val).replace(",", "").replace("%", "").strip())
            except:
                return 0

        # 实时行情
        try:
            spot = ak.stock_zh_a_spot_em()
            row = spot[spot["代码"] == code]
            price = float(row["最新价"].values[0]) if not row.empty else 0
            change_pct = float(row["涨跌幅"].values[0]) if not row.empty else 0
            turnover = float(row["换手率"].values[0]) if not row.empty and "换手率" in row.columns else 0
            volume_ratio = float(row["量比"].values[0]) if not row.empty and "量比" in row.columns else 0
        except:
            price, change_pct, turnover, volume_ratio = 0, 0, 0, 0

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


if __name__ == "__main__":
    hot = get_hot_stocks(20)
    capital = get_capital_flow_stocks(20)
    result = get_intersection(hot, capital)
    print(f"\n最终筛选结果: {len(result)} 只股票")
    for s in result:
        print(f"  {s['code']} {s['name']}")
