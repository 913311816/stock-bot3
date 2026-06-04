import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from src.ai_analyzer import analyze_stock
from src.chart_generator import calculate_kline_summary, plot_kline
from src.report_sender import build_html_report, send_email
from src.stock_screener import (
    get_capital_flow_stocks,
    get_hot_stocks,
    get_intersection,
    get_stock_basic_info,
    get_stock_kline_data,
    get_stock_news,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def run() -> None:
    top_n = int(os.environ.get("TOP_N", "20"))
    output_dir = Path("output") / datetime.now().strftime("%Y%m%d")
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting A-share stock bot")
    logger.info("Rule: hot rank Top %s INTERSECT 3-day main fund inflow Top %s", top_n, top_n)

    hot_stocks = get_hot_stocks(top_n=top_n)
    time.sleep(1)
    capital_stocks = get_capital_flow_stocks(top_n=top_n)
    selected = get_intersection(hot_stocks, capital_stocks)

    chart_paths: dict[str, str] = {}
    analyses: dict[str, str] = {}

    for stock in selected:
        code = stock["code"]
        name = stock["name"]
        logger.info("Processing %s %s", code, name)

        basic_info = get_stock_basic_info(code)
        stock.update({k: v for k, v in basic_info.items() if k not in {"price", "change_pct"} or not stock.get(k)})
        time.sleep(0.6)

        kline_df = get_stock_kline_data(code, days=320)
        time.sleep(0.6)

        if kline_df is not None and len(kline_df) >= 30:
            chart_path = str(output_dir / f"{code}_kline.png")
            try:
                chart_paths[code] = plot_kline(
                    df=kline_df,
                    code=code,
                    name=name,
                    output_path=chart_path,
                    hot_rank=int(stock.get("hot_rank", 0)),
                    capital_rank=int(stock.get("capital_rank", 0)),
                    capital_inflow=float(stock.get("capital_inflow_3d", 0)),
                )
            except Exception as exc:
                logger.warning("Chart failed for %s: %s", code, exc)
        else:
            logger.warning("K-line data not enough for %s", code)

        news = get_stock_news(code, name)
        time.sleep(0.6)
        kline_summary = calculate_kline_summary(kline_df)
        analyses[code] = analyze_stock(stock=stock, basic_info=basic_info, news_list=news, kline_summary=kline_summary)
        time.sleep(1)

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    html_content = build_html_report(
        date_str=date_str,
        stocks=selected,
        analyses=analyses,
        chart_paths=chart_paths,
        hot_stocks=hot_stocks,
        capital_stocks=capital_stocks,
    )

    html_path = output_dir / "report.html"
    html_path.write_text(html_content, encoding="utf-8")
    logger.info("Saved report: %s", html_path)

    to_email = os.environ.get("TO_EMAIL", "")
    from_email = os.environ.get("FROM_EMAIL", "")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    use_ssl = _env_bool("SMTP_SSL", False)

    if not all([to_email, from_email, smtp_user, smtp_password]):
        logger.warning("Email settings are incomplete. Report was generated but not sent.")
        return

    subject = f"A股选股日报 {datetime.now().strftime('%Y-%m-%d')} - 入选{len(selected)}只"
    if not send_email(
        html_content=html_content,
        subject=subject,
        to_email=to_email,
        from_email=from_email,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        use_ssl=use_ssl,
    ):
        raise RuntimeError("Email send failed")

    logger.info("Done. Selected %s stocks.", len(selected))


if __name__ == "__main__":
    run()
