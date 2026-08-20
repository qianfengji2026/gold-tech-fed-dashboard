#!/usr/bin/env python3
"""
================================================================================
 🏦 每日高频看板: 黄金通胀预期、美股科技股情绪与美联储降息概率
    Daily Dashboard: Gold · Inflation · Tech Sentiment · Fed Policy

 触发频率: 周一至周五, 美股收盘后 (GitHub Actions cron: UTC 21:00)
 数据源:   Yahoo Finance, FRED, CME FedWatch, CNN Fear & Greed
 输出:      HTML 邮件 → 指定收件人
================================================================================

使用方式:
  1. 本地运行:   python daily_dashboard.py
  2. 环境变量:   见 .env.example
  3. 自动化:     GitHub Actions .github/workflows/daily.yml
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from utils.data_fetchers import fetch_daily_bundle
from utils.email_sender import send_html_email
from utils.html_templates import render_daily_html

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "data" / "daily_dashboard.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("daily_dashboard")

# ============================================================
# 工作日检查
# ============================================================
def is_weekday() -> bool:
    """判断今天是否为工作日 (周一至周五)。"""
    return datetime.now().weekday() < 5  # 0=Mon ... 4=Fri


# ============================================================
# 主流程
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("每日高频看板开始执行")
    logger.info("=" * 60)

    # 环境变量预检
    required_vars = ["SMTP_SERVER", "SMTP_PORT", "SENDER_EMAIL", "SMTP_PASSWORD", "RECEIVER_EMAIL"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"缺少必要环境变量: {', '.join(missing)}")
        logger.error("请检查 .env 文件或 GitHub Secrets 配置")
        sys.exit(1)

    logger.info("环境变量校验通过, 开始抓取数据...")

    # --- 抓取全部数据 ---
    data = fetch_daily_bundle()

    # --- 生成邮件标题 ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_cn = weekday_names[datetime.now().weekday()]
    subject = f"【每日黄金通胀预期、美股科技股情绪、美联储降息概率与美元信用评估看板】{today_str} {weekday_cn}"

    # --- 渲染 HTML ---
    logger.info("渲染 HTML 邮件...")
    html_body = render_daily_html(data)

    # --- 发送邮件 ---
    logger.info(f"发送邮件 → {os.getenv('RECEIVER_EMAIL')}")
    success = send_html_email(subject=subject, html_body=html_body)

    if success:
        logger.info("✅ 每日看板邮件发送成功!")
    else:
        logger.error("❌ 每日看板邮件发送失败!")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("每日高频看板执行完毕")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
