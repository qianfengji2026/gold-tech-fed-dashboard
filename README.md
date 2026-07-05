# 🏦 黄金、美股科技股与美联储宏观自动追踪看板系统

> Gold · US Tech Stocks · Fed Policy — Macro Auto-Tracking Dashboard

---

## 📁 项目目录结构

```
gold-tech-fed-dashboard/
├── daily_dashboard.py          # 🚀 轨道A: 每日高频看板 (工作日自动发送)
├── macro_monthly.py            # 📊 轨道B: 长周期宏观底牌 (每月1号自动发送)
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
├── .gitignore
├── README.md
│
├── utils/                      # 核心工具模块
│   ├── __init__.py
│   ├── data_fetchers.py        # 五大维度数据抓取器 (独立容错)
│   ├── email_sender.py         # SMTP 邮件发送
│   └── html_templates.py       # HTML 邮件模板渲染
│
├── data/                       # 手动维护的结构化数据
│   ├── aisc_data.json          # 全球黄金 AISC 开采成本 (季度更新)
│   ├── wgc_cb_gold.json        # WGC 央行购金数据 (季度更新)
│   └── fomc_decisions.json     # FOMC 政策声明 (每次会议后更新)
│
└── .github/workflows/          # GitHub Actions 自动化
    ├── daily.yml               # 每日定时任务 (Mon-Fri 21:00 UTC)
    └── monthly.yml             # 月度定时任务 (每月1日 01:00 UTC)
```

---

## 🎯 五大核心数据维度

| 维度 | 更新频率 | 数据源 | 轨道 |
|------|---------|--------|------|
| **黄金价格** | 每日 | Yahoo Finance (GC=F, GLD) | A |
| **通胀预期** | 每日+月度 | FRED (T5YIE) / DBC / CPI / PCE | A+B |
| **央行购金** | 季度 | WGC 官方 (本地 JSON) | B |
| **黄金 AISC 成本** | 季度 | WGC / S&P Global (本地 JSON) | B |
| **科技股行情+情绪** | 每日 | Yahoo Finance (QQQ, Mag7, VXN) / CNN F&G | A |
| **美联储政策** | 每日概率+议息 | CME FedWatch / FRED / FOMC | A+B |

---

## 🚀 快速开始

### 1. 克隆并配置

```bash
cd gold-tech-fed-dashboard

# 复制环境变量模板
cp .env.example .env

# 编辑 .env, 填入真实邮箱和 API Key
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 本地测试

```bash
# 测试每日看板
python daily_dashboard.py

# 测试月度报告
python macro_monthly.py
```

### 4. GitHub Actions 部署

1. 将项目 Push 到 GitHub 仓库
2. 在仓库 `Settings → Secrets and variables → Actions` 添加以下 Secrets:

| Secret | 说明 | 示例 |
|--------|------|------|
| `SMTP_SERVER` | SMTP 服务器地址 | `smtp.qq.com` |
| `SMTP_PORT` | SMTP 端口 | `587` |
| `SENDER_EMAIL` | 发件人邮箱 | `your@qq.com` |
| `SMTP_PASSWORD` | SMTP 授权码 (非登录密码) | `xxxxx` |
| `RECEIVER_EMAIL` | 收件人邮箱 | `receiver@example.com` |
| `FRED_API_KEY` | (可选) FRED API Key | 免费注册获取 |

3. GitHub Actions 将按 `cron` 自动触发, 无需服务器, 完全免费。

---

## 📧 邮件投递规范

### 轨道 A: 每日高频看板

- **触发**: 周一至周五 UTC 21:00 (北京时间次日 05:00)
- **标题**: `【每日黄金通胀预期、美股科技股情绪与美联储降息概率看板】2026-07-06`
- **内容**: 黄金价格、5Y平衡通胀率、QQQ/Mag7涨跌、科技股情绪定性、CME降息概率

### 轨道 B: 长周期宏观底牌

- **触发**: 每月1号 UTC 01:00 (北京时间 09:00)
- **标题**: `【全球央行购金、黄金硬核开采成本与美联储最新货币政策月度报告】2026-07-01`
- **内容**: WGC央行购金明细、AISC成本利润率、CPI/PCE通胀、FOMC决策全文要点

---

## 🛡️ 容错设计

- **独立抓取**: 每个数据源独立 `try/except`, 单项失败不影响整体
- **级联降级**: FRED 数据优先 `fredapi` → 降级 CSV 下载 → 显示"维护中"
- **本地兜底**: AISC/央行购金/FOMC 使用本地 JSON 文件, 避免上游 API 依赖
- **邮件保护**: 任何数据异常都不会导致脚本崩溃或邮件中断

---

## 📊 数据维护指南

以下数据文件需要**手动维护** (这些数据无公开实时 API):

| 文件 | 更新频率 | 数据来源 |
|------|---------|---------|
| `data/aisc_data.json` | 每季度 | [WGC Gold Demand Trends](https://www.gold.org/goldhub/data/gold-demand-trends) |
| `data/wgc_cb_gold.json` | 每季度 | [WGC Central Bank Gold Reserves](https://www.gold.org/goldhub/data/gold-reserves-by-country) |
| `data/fomc_decisions.json` | 每次FOMC会后 | [美联储 FOMC 日历](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) |

---

## 🔑 API Key 获取

- **FRED API Key** (免费): https://fred.stlouisfed.org/docs/api/api_key.html
- **SMTP 授权码**: QQ邮箱 → 设置 → 账户 → POP3/SMTP服务 → 生成授权码

---

## 📝 技术栈

- **Python 3.12+**: `yfinance`, `fredapi`, `pandas`, `requests`, `python-dotenv`
- **数据源**: Yahoo Finance, FRED, CME FedWatch, CNN Fear & Greed
- **自动化**: GitHub Actions (cron 定时调度, 零服务器成本)
- **邮件**: SMTP (smtplib + email.mime), HTML 内联样式

---

## ⚠️ 免责声明

本系统仅供信息参考, 不构成任何投资建议。所有数据来源于公开渠道, 不保证准确性和完整性。
投资有风险, 入市需谨慎。
