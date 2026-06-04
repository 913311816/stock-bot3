import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)


def normalize_code(raw: object) -> str:
    text = str(raw or "").strip().upper()
    text = re.sub(r"^(SH|SZ|BJ)", "", text)
    text = re.sub(r"\.(SH|SZ|BJ)$", "", text)
    match = re.search(r"(\d{6})", text)
    return match.group(1) if match else text.zfill(6)


def market_from_code(code: str) -> str:
    if code.startswith(("5", "6", "9")):
        return "SH"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SZ"


def _pick_column(df: pd.DataFrame, candidates: list[str], contains: list[str] | None = None) -> str:
    for name in candidates:
        if name in df.columns:
            return name
    if contains:
        for col in df.columns:
            if all(part in str(col) for part in contains):
                return str(col)
    raise KeyError(f"Cannot find column. candidates={candidates}, columns={list(df.columns)}")


def _to_float(value: object) -> float:
    if value is None or pd.isna(value):
        return 0.0
    text = str(value).replace(",", "").replace("%", "").strip()
    if text in {"", "-", "--", "None", "nan"}:
        return 0.0
    multiplier = 1.0
    if text.endswith("亿"):
        multiplier = 1e8
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 1e4
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) * multiplier if match else 0.0


def get_hot_stocks(top_n: int = 20) -> list[dict]:
    """东方财富个股人气榜 Top N."""
    logger.info("Fetching Eastmoney hot rank Top %s", top_n)
    df = ak.stock_hot_rank_em()
    if df is None or df.empty:
        raise RuntimeError("Hot rank API returned no data")

    code_col = _pick_column(df, ["代码", "股票代码"])
    name_col = _pick_column(df, ["股票名称", "名称", "证券名称"])
    price_col = _pick_column(df, ["最新价", "最新价格"], contains=["最新"])
    pct_col = _pick_column(df, ["涨跌幅", "涨跌幅%"], contains=["涨跌幅"])

    result: list[dict] = []
    for rank, (_, row) in enumerate(df.head(top_n).iterrows(), start=1):
        code = normalize_code(row[code_col])
        result.append(
            {
                "code": code,
                "name": str(row[name_col]),
                "market": market_from_code(code),
                "hot_rank": rank,
                "price": _to_float(row.get(price_col)),
                "change_pct": _to_float(row.get(pct_col)),
            }
        )
    logger.info("Hot rank codes: %s", [s["code"] for s in result])
    return result


def get_capital_flow_stocks(top_n: int = 20) -> list[dict]:
    """东方财富个股资金流排名，按 3 日主力净流入净额取 Top N."""
    logger.info("Fetching Eastmoney 3-day main fund inflow Top %s", top_n)
    df = ak.stock_individual_fund_flow_rank(indicator="3日")
    if df is None or df.empty:
        raise RuntimeError("3-day fund flow API returned no data")

    code_col = _pick_column(df, ["代码", "股票代码"])
    name_col = _pick_column(df, ["名称", "股票名称", "证券名称"])
    inflow_col = _pick_column(
        df,
        ["3日主力净流入-净额", "主力净流入-净额", "主力净流入净额"],
        contains=["主力", "净流入", "净额"],
    )
    pct_col = None
    try:
        pct_col = _pick_column(
            df,
            ["3日主力净流入-净占比", "主力净流入-净占比", "主力净流入净占比"],
            contains=["主力", "净流入", "净占比"],
        )
    except KeyError:
        pass

    work = df.copy()
    work["_capital_inflow_3d"] = work[inflow_col].map(_to_float)
    work = work.sort_values("_capital_inflow_3d", ascending=False)
    work = work[work["_capital_inflow_3d"] > 0].head(top_n)

    result: list[dict] = []
    for rank, (_, row) in enumerate(work.iterrows(), start=1):
        code = normalize_code(row[code_col])
        result.append(
            {
                "code": code,
                "name": str(row[name_col]),
                "market": market_from_code(code),
                "capital_rank": rank,
                "capital_inflow_3d": float(row["_capital_inflow_3d"]),
                "capital_inflow_3d_pct": _to_float(row[pct_col]) if pct_col else 0.0,
            }
        )
    logger.info("3-day fund flow codes: %s", [s["code"] for s in result])
    return result


def get_intersection(hot_stocks: list[dict], capital_stocks: list[dict]) -> list[dict]:
    hot_by_code = {s["code"]: s for s in hot_stocks}
    capital_by_code = {s["code"]: s for s in capital_stocks}

    selected = []
    for code, hot in hot_by_code.items():
        capital = capital_by_code.get(code)
        if capital:
            selected.append({**hot, **capital})

    selected.sort(key=lambda item: (item.get("hot_rank", 999), item.get("capital_rank", 999)))
    logger.info("Intersection size: %s, codes: %s", len(selected), [s["code"] for s in selected])
    return selected


def get_stock_kline_data(code: str, days: int = 320) -> Optional[pd.DataFrame]:
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq",
        )
        if df is None or df.empty:
            return None
        df = df.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "涨跌幅": "change_pct",
            }
        )
        required = ["date", "open", "close", "high", "low", "volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise KeyError(f"K-line missing columns: {missing}, columns={list(df.columns)}")
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "close", "high", "low", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["open", "close", "high", "low"]).set_index("date").sort_index().tail(days)
    except Exception as exc:
        logger.exception("Failed to fetch K-line for %s: %s", code, exc)
        return None


def get_stock_news(code: str, name: str, limit: int = 8) -> list[dict]:
    try:
        df = ak.stock_news_em(symbol=code)
        if df is None or df.empty:
            return []
        title_col = _pick_column(df, ["新闻标题", "标题"], contains=["标题"])
        date_col = _pick_column(df, ["发布时间", "时间", "日期"], contains=["时间"])
        url_col = None
        for candidate in ["新闻链接", "链接", "url", "URL"]:
            if candidate in df.columns:
                url_col = candidate
                break
        content_col = None
        for candidate in ["新闻内容", "内容", "摘要"]:
            if candidate in df.columns:
                content_col = candidate
                break
        news = []
        for _, row in df.head(limit).iterrows():
            news.append(
                {
                    "title": str(row.get(title_col, "")),
                    "date": str(row.get(date_col, "")),
                    "url": str(row.get(url_col, "")) if url_col else "",
                    "digest": str(row.get(content_col, ""))[:200] if content_col else "",
                }
            )
        return news
    except Exception as exc:
        logger.warning("Failed to fetch news for %s %s: %s", code, name, exc)
        return []


def get_stock_basic_info(code: str) -> dict:
    result = {
        "price": 0.0,
        "change_pct": 0.0,
        "pe_dynamic": 0.0,
        "pb": 0.0,
        "market_cap": 0.0,
        "float_cap": 0.0,
        "turnover_rate": 0.0,
        "volume_ratio": 0.0,
        "industry": "",
    }

    try:
        info = ak.stock_individual_info_em(symbol=code)
        if info is not None and not info.empty:
            info_dict = {str(row.iloc[0]): row.iloc[1] for _, row in info.iterrows()}
            result.update(
                {
                    "market_cap": _to_float(info_dict.get("总市值", 0)) / 1e8,
                    "float_cap": _to_float(info_dict.get("流通市值", 0)) / 1e8,
                    "industry": str(info_dict.get("行业", "") or ""),
                }
            )
    except Exception as exc:
        logger.warning("Failed to fetch basic info for %s: %s", code, exc)

    try:
        spot = ak.stock_zh_a_spot_em()
        if spot is not None and not spot.empty and "代码" in spot.columns:
            row = spot[spot["代码"].astype(str).map(normalize_code) == code]
            if not row.empty:
                row = row.iloc[0]
                result.update(
                    {
                        "price": _to_float(row.get("最新价", 0)),
                        "change_pct": _to_float(row.get("涨跌幅", 0)),
                        "pe_dynamic": _to_float(row.get("市盈率-动态", row.get("市盈率", 0))),
                        "pb": _to_float(row.get("市净率", 0)),
                        "turnover_rate": _to_float(row.get("换手率", 0)),
                        "volume_ratio": _to_float(row.get("量比", 0)),
                    }
                )
    except Exception as exc:
        logger.warning("Failed to fetch spot info for %s: %s", code, exc)

    return result
