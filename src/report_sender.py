import base64
import html
import logging
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _money_yi(value: float) -> str:
    return f"{value / 1e8:.2f}亿元"


def _image_data_uri(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    with open(path, "rb") as file:
        encoded = base64.b64encode(file.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def markdown_to_html(text: str) -> str:
    safe = html.escape(text or "")
    safe = re.sub(r"^### (.+)$", r"<h3>\1</h3>", safe, flags=re.MULTILINE)
    safe = re.sub(r"^## (.+)$", r"<h2>\1</h2>", safe, flags=re.MULTILINE)
    safe = re.sub(r"^- (.+)$", r"<li>\1</li>", safe, flags=re.MULTILINE)
    safe = re.sub(r"(<li>.*?</li>\n?)+", lambda m: f"<ul>{m.group(0)}</ul>", safe, flags=re.DOTALL)
    safe = safe.replace("\n\n", "</p><p>").replace("\n", "<br>")
    return f"<p>{safe}</p>"


def _render_rank_table(title: str, rows: list[dict], rank_key: str, value_key: str | None = None) -> str:
    body = ""
    for row in rows:
        value = ""
        if value_key == "capital_inflow_3d":
            value = _money_yi(float(row.get(value_key, 0)))
        elif value_key:
            value = html.escape(str(row.get(value_key, "")))
        body += f"""
        <tr>
          <td>#{row.get(rank_key, "-")}</td>
          <td>{html.escape(row.get("name", ""))}</td>
          <td>{html.escape(row.get("code", ""))}</td>
          <td>{value}</td>
        </tr>"""
    return f"""
    <section>
      <h2>{html.escape(title)}</h2>
      <table>
        <thead><tr><th>排名</th><th>名称</th><th>代码</th><th>数值</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>"""


def build_html_report(
    date_str: str,
    stocks: list[dict],
    analyses: dict[str, str],
    chart_paths: dict[str, str],
    hot_stocks: list[dict],
    capital_stocks: list[dict],
) -> str:
    cards = ""
    for stock in stocks:
        code = stock["code"]
        image_uri = _image_data_uri(chart_paths.get(code, ""))
        image_html = (
            f'<img class="chart" src="{image_uri}" alt="{html.escape(stock["name"])} K线图">'
            if image_uri
            else '<div class="empty">K线图生成失败</div>'
        )
        analysis_html = markdown_to_html(analyses.get(code, "暂无分析"))
        change = float(stock.get("change_pct", 0))
        change_class = "up" if change >= 0 else "down"
        cards += f"""
        <article class="stock-card">
          <header class="stock-header">
            <div>
              <span class="market">{html.escape(stock.get("market", ""))}</span>
              <strong>{html.escape(stock.get("name", ""))}</strong>
              <span class="code">{html.escape(code)}</span>
            </div>
            <div class="price">
              <b>{float(stock.get("price", 0)):.2f}</b>
              <span class="{change_class}">{change:+.2f}%</span>
            </div>
          </header>
          <div class="metrics">
            <div><span>人气排名</span><b>#{stock.get("hot_rank")}</b></div>
            <div><span>3日资金排名</span><b>#{stock.get("capital_rank")}</b></div>
            <div><span>3日主力净流入</span><b>{_money_yi(float(stock.get("capital_inflow_3d", 0)))}</b></div>
            <div><span>净流入占比</span><b>{float(stock.get("capital_inflow_3d_pct", 0)):.2f}%</b></div>
          </div>
          {image_html}
          <div class="analysis">{analysis_html}</div>
        </article>"""

    if not stocks:
        cards = """
        <div class="no-result">
          <h2>今日没有交集</h2>
          <p>这不一定代表程序异常。报告下方保留了两个原始 Top20 榜单，可检查当天人气榜和3日资金流入榜是否确实没有重合。</p>
        </div>"""

    hot_table = _render_rank_table("东方财富人气榜 Top20", hot_stocks, "hot_rank", "change_pct")
    capital_table = _render_rank_table("近3日主力净流入 Top20", capital_stocks, "capital_rank", "capital_inflow_3d")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ margin:0; background:#f4f6f8; color:#17202a; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; }}
    .wrap {{ max-width:980px; margin:0 auto; padding:24px; }}
    .top {{ background:#ffffff; border:1px solid #dfe5ec; border-radius:8px; padding:22px 24px; margin-bottom:18px; }}
    h1 {{ margin:0 0 8px; font-size:26px; }}
    h2 {{ margin:22px 0 10px; font-size:18px; }}
    h3 {{ margin:16px 0 6px; font-size:15px; }}
    .summary {{ color:#64748b; font-size:14px; line-height:1.7; }}
    .stock-card {{ background:#ffffff; border:1px solid #dfe5ec; border-radius:8px; margin:18px 0; overflow:hidden; }}
    .stock-header {{ display:flex; justify-content:space-between; gap:16px; padding:18px 20px; border-bottom:1px solid #edf1f5; align-items:center; }}
    .stock-header strong {{ font-size:22px; }}
    .market {{ background:#1f6feb; color:white; border-radius:4px; padding:2px 7px; font-size:12px; margin-right:8px; }}
    .code {{ color:#64748b; margin-left:8px; }}
    .price {{ text-align:right; }}
    .price b {{ display:block; font-size:22px; }}
    .up {{ color:#c73838; }}
    .down {{ color:#178a4d; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:1px; background:#edf1f5; }}
    .metrics div {{ background:#fbfcfe; padding:12px; text-align:center; }}
    .metrics span {{ display:block; color:#64748b; font-size:12px; margin-bottom:5px; }}
    .metrics b {{ font-size:16px; }}
    .chart {{ width:100%; display:block; }}
    .analysis {{ padding:18px 22px; line-height:1.75; font-size:14px; }}
    .empty,.no-result {{ background:#ffffff; border:1px solid #dfe5ec; border-radius:8px; padding:28px; text-align:center; color:#64748b; }}
    section {{ background:#ffffff; border:1px solid #dfe5ec; border-radius:8px; padding:16px; margin:18px 0; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ border-bottom:1px solid #edf1f5; padding:8px; text-align:left; }}
    th {{ color:#64748b; font-weight:600; }}
    .footer {{ color:#7b8794; font-size:12px; line-height:1.6; text-align:center; padding:20px 0; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <h1>A股选股日报</h1>
      <div class="summary">
        日期：{html.escape(date_str)}<br>
        策略：东方财富人气榜 Top20 与近3日主力净流入 Top20 取交集。今日入选 {len(stocks)} 只。
      </div>
    </div>
    {cards}
    {hot_table}
    {capital_table}
    <div class="footer">本报告由自动化程序生成，仅供学习和研究，不构成任何投资建议。股市有风险，投资需谨慎。</div>
  </div>
</body>
</html>"""


def send_email(
    html_content: str,
    subject: str,
    to_email: str,
    from_email: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    use_ssl: bool = False,
) -> bool:
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = from_email
        message["To"] = to_email
        message.attach(MIMEText(html_content, "html", "utf-8"))

        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_email, [to_email], message.as_string())
        server.quit()
        logger.info("Email sent to %s", to_email)
        return True
    except Exception as exc:
        logger.exception("Email send failed: %s", exc)
        return False
