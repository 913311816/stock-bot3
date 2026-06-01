"""
主程序入口
协调：数据获取 → K线绘制 → AI分析 → 邮件发送
"""

import os
import sys
import logging
import time
from datetime import datetime
from pathlib import Path

# 添加 src 到路径（支持直接运行和 GitHub Actions 两种方式）
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from src.stock_screener import (
    get_hot_stocks,
    get_capital_flow_stocks,
    get_intersection,
    get_stock_kline_data,
    get_stock_news,
    get_stock_basic_info,
)
from src.chart_generator import plot_kline
from src.ai_analyzer import analyze_stock, calculate_kline_summary
from src.report_sender import build_html_report, send_email

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def run():
    logger.info("=" * 60)
    logger.info("A股选股机器人启动")
    logger.info("=" * 60)

    # ── 1. 筛选股票 ────────────────────────────────────────
    logger.info("【步骤1/4】获取热度榜和资金流入榜...")
    hot_stocks = get_hot_stocks(top_n=20)
    time.sleep(1)
    capital_stocks = get_capital_flow_stocks(top_n=20)
    time.sleep(1)

    selected = get_intersection(hot_stocks, capital_stocks)

    if not selected:
        logger.warning("今日热度前20与资金流入前20无交集，将发送空报告")

    # ── 2. 获取详细数据 + 绘图 ─────────────────────────────
    logger.info("【步骤2/4】获取K线、基本面、新闻数据...")
    output_dir = Path("output") / datetime.now().strftime("%Y%m%d")
    output_dir.mkdir(parents=True, exist_ok=True)

    chart_paths = {}
    analyses = {}

    for stock in selected:
        code = stock['code']
        name = stock['name']
        logger.info(f"  处理: {code} {name}")

        # 基本信息
        basic_info = get_stock_basic_info(code)
        stock.update(basic_info)
        time.sleep(0.5)

        # K线数据
        kline_df = get_stock_kline_data(code, days=300)
        time.sleep(0.5)

        # 绘制K线图
        if kline_df is not None and len(kline_df) >= 10:
            chart_path = str(output_dir / f"{code}_kline.png")
            try:
                plot_kline(
                    df=kline_df,
                    code=code,
                    name=name,
                    output_path=chart_path,
                    hot_rank=stock.get('hot_rank', 0),
                    capital_inflow=stock.get('capital_inflow_3d', 0),
                )
                chart_paths[code] = chart_path
            except Exception as e:
                logger.error(f"K线图绘制失败 {code}: {e}")
        else:
            logger.warning(f"K线数据不足，跳过绘图: {code}")

        # 新闻
        news = get_stock_news(code, name)
        time.sleep(0.5)

        # AI 分析
        kline_summary = calculate_kline_summary(kline_df) if kline_df is not None else {}
        analyses[code] = analyze_stock(
            code=code,
            name=name,
            hot_rank=stock.get('hot_rank', 0),
            capital_inflow_3d=stock.get('capital_inflow_3d', 0),
            basic_info=basic_info,
            news_list=news,
            kline_summary=kline_summary,
        )
        logger.info(f"  ✓ {code} {name} 分析完成")
        time.sleep(1)

    # ── 3. 生成 HTML 报告 ──────────────────────────────────
    logger.info("【步骤3/4】生成 HTML 报告...")
    date_str = datetime.now().strftime("%Y年%m月%d日 %A")

    # 按热度排名排序
    selected.sort(key=lambda x: x.get('hot_rank', 999))

    html_content = build_html_report(
        date_str=date_str,
        stocks=selected,
        analyses=analyses,
        chart_paths=chart_paths,
    )

    # 保存 HTML 备份
    html_path = output_dir / "report.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"HTML 报告已保存: {html_path}")

    # ── 4. 发送邮件 ────────────────────────────────────────
    logger.info("【步骤4/4】发送邮件...")

    to_email = os.environ.get("TO_EMAIL", "")
    from_email = os.environ.get("FROM_EMAIL", "")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    use_ssl = os.environ.get("SMTP_SSL", "false").lower() == "true"

    if not all([to_email, from_email, smtp_user, smtp_password]):
        logger.warning("邮件配置不完整，跳过发送。请在 GitHub Secrets 中配置邮件参数。")
        logger.info("需要配置: TO_EMAIL, FROM_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD")
    else:
        today = datetime.now().strftime("%Y/%m/%d")
        subject = f"📈 A股选股日报 {today}｜{len(selected)} 只股票入选"

        success = send_email(
            html_content=html_content,
            subject=subject,
            to_email=to_email,
            from_email=from_email,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            use_ssl=use_ssl,
        )

        if success:
            logger.info(f"✅ 邮件已发送至 {to_email}")
        else:
            logger.error("❌ 邮件发送失败，请检查 SMTP 配置")
            sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"全部完成！共选出 {len(selected)} 只股票")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
