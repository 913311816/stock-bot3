"""
邮件报告生成与发送模块
生成美观的 HTML 邮件，包含 K 线图（base64 内嵌）和 AI 分析报告
"""

import os
import base64
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def img_to_base64(path: str) -> str:
    """图片转 base64"""
    try:
        with open(path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception:
        return ""


def markdown_to_html(text: str) -> str:
    """简单 Markdown 转 HTML"""
    import re
    # 标题
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    # 加粗
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # 列表
    text = re.sub(r'^[\-\*] (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'(<li>.*</li>\n?)+', lambda m: f'<ul>{m.group()}</ul>', text, flags=re.DOTALL)
    # 换行
    text = text.replace('\n\n', '</p><p>').replace('\n', '<br/>')
    text = f'<p>{text}</p>'
    return text


def build_html_report(
    date_str: str,
    stocks: list[dict],
    analyses: dict,  # code -> analysis text
    chart_paths: dict,  # code -> image path
) -> str:
    """构建完整 HTML 邮件内容"""

    stock_cards = ""
    for i, stock in enumerate(stocks, 1):
        code = stock['code']
        name = stock['name']
        hot_rank = stock.get('hot_rank', '-')
        inflow = stock.get('capital_inflow_3d', 0)
        inflow_bn = inflow / 1e8
        price = stock.get('price', 0)
        change_pct = stock.get('change_pct', 0)
        pe = stock.get('pe_dynamic', 0)
        market_cap = stock.get('market_cap', 0)

        change_color = '#26a641' if change_pct >= 0 else '#f85149'
        change_arrow = '▲' if change_pct >= 0 else '▼'

        # K线图（base64内嵌）
        chart_html = ""
        chart_path = chart_paths.get(code, "")
        if chart_path and os.path.exists(chart_path):
            b64 = img_to_base64(chart_path)
            if b64:
                chart_html = f'<img src="data:image/png;base64,{b64}" style="width:100%;border-radius:8px;margin:12px 0;" alt="K线图"/>'
        else:
            chart_html = '<div style="background:#21262d;padding:20px;text-align:center;color:#8b949e;border-radius:8px;">K线图生成失败</div>'

        # AI分析内容
        analysis_raw = analyses.get(code, "分析数据获取中...")
        analysis_html = markdown_to_html(analysis_raw)

        # 市场标识
        market = "SH" if code.startswith("6") else ("SZ" if code.startswith(("0", "3")) else "BJ")
        market_color = "#e6594a" if market == "SH" else "#3d85c8"

        stock_cards += f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:12px;margin:24px 0;overflow:hidden;">
            <!-- 股票头部 -->
            <div style="background:linear-gradient(135deg,#0d1117 0%,#1a2332 100%);padding:20px 24px;border-bottom:1px solid #30363d;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
                    <div>
                        <span style="background:{market_color};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-right:8px;">{market}</span>
                        <span style="color:#e6edf3;font-size:22px;font-weight:700;">{name}</span>
                        <span style="color:#8b949e;font-size:14px;margin-left:8px;">{code}</span>
                    </div>
                    <div style="text-align:right;">
                        <div style="color:#e6edf3;font-size:24px;font-weight:700;">{price:.2f}</div>
                        <div style="color:{change_color};font-size:14px;">{change_arrow} {abs(change_pct):.2f}%</div>
                    </div>
                </div>

                <!-- 关键指标 -->
                <div style="display:flex;gap:16px;margin-top:16px;flex-wrap:wrap;">
                    <div style="background:#0d1117;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;text-align:center;">
                        <div style="color:#8b949e;font-size:11px;margin-bottom:4px;">热度排名</div>
                        <div style="color:#f0e68c;font-size:18px;font-weight:700;">#{hot_rank}</div>
                    </div>
                    <div style="background:#0d1117;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;text-align:center;">
                        <div style="color:#8b949e;font-size:11px;margin-bottom:4px;">3日主力净流入</div>
                        <div style="color:#26a641;font-size:18px;font-weight:700;">{inflow_bn:.2f}亿</div>
                    </div>
                    <div style="background:#0d1117;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;text-align:center;">
                        <div style="color:#8b949e;font-size:11px;margin-bottom:4px;">动态PE</div>
                        <div style="color:#e6edf3;font-size:18px;font-weight:700;">{pe:.1f}x</div>
                    </div>
                    <div style="background:#0d1117;border-radius:8px;padding:10px 16px;flex:1;min-width:100px;text-align:center;">
                        <div style="color:#8b949e;font-size:11px;margin-bottom:4px;">总市值</div>
                        <div style="color:#e6edf3;font-size:18px;font-weight:700;">{market_cap:.0f}亿</div>
                    </div>
                </div>
            </div>

            <!-- K线图 -->
            <div style="padding:16px 24px;border-bottom:1px solid #30363d;">
                <div style="color:#8b949e;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">K线图（含MA5/MA10/MA20/MA250）</div>
                {chart_html}
            </div>

            <!-- AI分析 -->
            <div style="padding:20px 24px;">
                <div style="color:#8b949e;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;">🤖 AI 深度分析</div>
                <div style="color:#c9d1d9;font-size:14px;line-height:1.8;">
                    {analysis_html}
                </div>
            </div>
        </div>"""

    # 邮件时间戳和统计
    no_result_hint = ""
    if not stocks:
        no_result_hint = """
        <div style="text-align:center;padding:60px;color:#8b949e;">
            <div style="font-size:40px;margin-bottom:16px;">📊</div>
            <div style="font-size:18px;">今日未找到符合条件的股票</div>
            <div style="font-size:13px;margin-top:8px;">热度前20 与 资金流入前20 暂无交集</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body {{ margin:0;padding:0;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
  h2 {{ color:#58a6ff;margin-top:24px;margin-bottom:8px; }}
  h3 {{ color:#79c0ff;margin-top:16px;margin-bottom:6px; }}
  p {{ color:#c9d1d9;margin:4px 0; }}
  ul {{ padding-left:20px; }}
  li {{ color:#c9d1d9;margin:4px 0; }}
  strong {{ color:#e6edf3; }}
  a {{ color:#58a6ff; }}
</style>
</head>
<body>
<div style="max-width:900px;margin:0 auto;padding:20px;">

    <!-- 顶部标题栏 -->
    <div style="background:linear-gradient(135deg,#1a2332 0%,#0d1117 100%);border:1px solid #30363d;border-radius:16px;padding:32px;margin-bottom:24px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#e6edf3;letter-spacing:-0.5px;">
            📈 A股选股日报
        </div>
        <div style="color:#8b949e;font-size:14px;margin-top:8px;">{date_str}｜热度TOP20 ∩ 三日资金流入TOP20</div>
        <div style="display:flex;justify-content:center;gap:32px;margin-top:20px;flex-wrap:wrap;">
            <div style="text-align:center;">
                <div style="color:#58a6ff;font-size:28px;font-weight:700;">{len(stocks)}</div>
                <div style="color:#8b949e;font-size:12px;">今日入选</div>
            </div>
            <div style="text-align:center;">
                <div style="color:#3fb950;font-size:28px;font-weight:700;">20</div>
                <div style="color:#8b949e;font-size:12px;">热度筛选</div>
            </div>
            <div style="text-align:center;">
                <div style="color:#d29922;font-size:28px;font-weight:700;">20</div>
                <div style="color:#8b949e;font-size:12px;">资金筛选</div>
            </div>
        </div>
    </div>

    <!-- 筛选说明 -->
    <div style="background:#161b22;border:1px solid #30363d;border-left:4px solid #58a6ff;border-radius:8px;padding:14px 20px;margin-bottom:24px;font-size:13px;color:#8b949e;">
        <strong style="color:#58a6ff;">筛选逻辑：</strong>
        取「当日东方财富热度榜前20」与「近三日主力资金净流入前20」的交集，同时满足两个条件的股票才会入选本报告。
    </div>

    {no_result_hint}
    {stock_cards}

    <!-- 底部免责声明 -->
    <div style="text-align:center;padding:24px;color:#484f58;font-size:12px;border-top:1px solid #21262d;margin-top:32px;">
        本报告由自动化程序生成，仅供参考学习，不构成任何投资建议。<br/>
        股市有风险，投资需谨慎。数据来源：东方财富，AI 分析：DeepSeek API。
    </div>
</div>
</body>
</html>"""

    return html


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
    """发送 HTML 邮件"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email  # QQ/163等国内邮箱要求From与SMTP账号完全一致
        msg['To'] = to_email

        part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(part)

        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()

        server.login(smtp_user, smtp_password)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()

        logger.info(f"邮件发送成功: {to_email}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False
