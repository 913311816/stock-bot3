# 📈 A股选股机器人

自动筛选「当日热度前20 ∩ 近三日资金流入前20」的 A 股，生成包含 K 线图和 AI 深度分析的邮件报告，每个工作日晚上 8 点自动运行。

## 功能特性

- ✅ **双维度筛选**：热度榜 × 资金流入榜取交集，找到市场真正关注的标的
- ✅ **专业 K 线图**：MA5（5日）/ MA10（10日）/ MA20（20日）/ MA250（年线）
- ✅ **AI 深度分析**：调用 Claude API，说明热度理由、资金逻辑、技术面、基本面、风险提示
- ✅ **精美邮件报告**：暗黑金融风 HTML 邮件，图文并茂
- ✅ **全自动运行**：GitHub Actions 定时触发，零成本托管
- ✅ **报告备份**：每次运行产物自动上传 GitHub Artifacts，保留 7 天

---

## 快速部署（5 步）

### 第一步：Fork 本仓库

点击右上角 **Fork** 按钮，将仓库复制到你的 GitHub 账号。

### 第二步：配置 GitHub Secrets

进入你 Fork 后的仓库 → **Settings → Secrets and variables → Actions → New repository secret**，逐一添加以下密钥：

| Secret 名称 | 说明 | 示例 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API 密钥（[获取地址](https://console.anthropic.com/)） | `sk-ant-api03-...` |
| `TO_EMAIL` | 收件人邮箱 | `you@example.com` |
| `FROM_EMAIL` | 发件人邮箱 | `bot@gmail.com` |
| `SMTP_HOST` | SMTP 服务器地址 | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 端口 | `587` |
| `SMTP_USER` | SMTP 登录用户名 | `bot@gmail.com` |
| `SMTP_PASSWORD` | SMTP 密码或应用专用密码 | `xxxx xxxx xxxx xxxx` |
| `SMTP_SSL` | 是否使用 SSL（465 端口需要） | `false` |

### 第三步：常见邮箱 SMTP 配置参考

**Gmail（推荐）**
```
SMTP_HOST:     smtp.gmail.com
SMTP_PORT:     587
SMTP_SSL:      false
SMTP_PASSWORD: 需要开启两步验证后生成「应用专用密码」
```
> Gmail 设置路径：Google 账号 → 安全性 → 两步验证 → 应用密码

**QQ邮箱**
```
SMTP_HOST:     smtp.qq.com
SMTP_PORT:     587
SMTP_SSL:      false
SMTP_PASSWORD: 需要在 QQ 邮箱设置中获取「授权码」（非登录密码）
```

**163邮箱**
```
SMTP_HOST:     smtp.163.com
SMTP_PORT:     994
SMTP_SSL:      true
SMTP_PASSWORD: 需要在 163 邮箱设置中开启 SMTP 并获取授权码
```

### 第四步：启用 GitHub Actions

1. 进入仓库 **Actions** 标签页
2. 如有提示点击 **"I understand my workflows, go ahead and enable them"**
3. 找到 **"A股选股日报"** workflow，点击右侧 **Enable workflow**

### 第五步：手动测试

1. 在 Actions 页面找到 **"A股选股日报"**
2. 点击 **"Run workflow"** → **"Run workflow"**
3. 等待约 3-5 分钟，检查邮件是否收到

---

## 运行时间

```
每个工作日（周一至周五）晚上 20:00（北京时间）自动运行
```

可在 `.github/workflows/daily_report.yml` 中修改 cron 表达式：

```yaml
- cron: '0 12 * * 1-5'   # UTC 12:00 = 北京时间 20:00
```

---

## 项目结构

```
stock-bot/
├── .github/
│   └── workflows/
│       └── daily_report.yml    # GitHub Actions 定时任务
├── src/
│   ├── stock_screener.py       # 数据抓取（热度榜 + 资金流入榜）
│   ├── chart_generator.py      # K线图绘制（含四条均线）
│   ├── ai_analyzer.py          # Claude AI 深度分析
│   └── report_sender.py        # HTML 邮件生成与发送
├── main.py                     # 主程序入口
├── requirements.txt            # Python 依赖
└── README.md                   # 本文档
```

---

## 数据来源

| 数据类型 | 来源 |
|---|---|
| 热度榜 | 东方财富人气榜 / 热门股票接口 |
| 资金流入 | 东方财富主力资金净流入（3日） |
| K线数据 | 东方财富历史行情接口 |
| 股票资讯 | 东方财富新闻搜索接口 |
| AI 分析 | Anthropic Claude API |

---

## 常见问题

**Q：没有 Anthropic API Key 也能用吗？**  
A：可以。不配置时会跳过 AI 分析，使用基础模板生成分析摘要，其他功能不受影响。

**Q：如果当天热度前20与资金流入前20无交集怎么办？**  
A：会发送一封空报告邮件，说明当天无符合条件的股票。

**Q：K线图中为什么有时候 MA250 不准确？**  
A：MA250 需要约一年的历史数据，接口默认拉取 300 个交易日，极少数情况下历史数据不足会导致偏差。

**Q：如何修改筛选数量（比如改为前50）？**  
A：修改 `main.py` 中 `get_hot_stocks(top_n=20)` 和 `get_capital_flow_stocks(top_n=20)` 的参数。

---

## 免责声明

本项目仅用于学习和技术研究目的，生成的报告**不构成任何投资建议**。股市有风险，投资需谨慎。
