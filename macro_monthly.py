#!/usr/bin/env python3
"""
================================================================================
 📊 长周期宏观底牌: 全球央行购金、黄金开采成本与美联储货币政策月度报告
    Monthly Macro Report: CB Gold Purchases · AISC · CPI/PCE · FOMC

 触发频率: 每月1号 (GitHub Actions cron: 每月1号 UTC 01:00)
 数据源:   WGC (本地JSON), FRED, CME FedWatch, Yahoo Finance
 输出:      HTML 邮件 → 指定收件人
================================================================================

使用方式:
  1. 本地运行:   python macro_monthly.py
  2. 环境变量:   见 .env.example
  3. 自动化:     GitHub Actions .github/workflows/monthly.yml
  4. 数据维护:
     - AISC 数据:  data/aisc_data.json (每季度手动更新)
     - WGC 购金:   data/wgc_cb_gold.json (每季度手动更新)
     - FOMC 决策:  data/fomc_decisions.json (每次会议后手动更新)
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

from utils.data_fetchers import fetch_monthly_bundle
from utils.email_sender import send_html_email
from utils.html_templates import render_monthly_html

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "data" / "macro_monthly.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("macro_monthly")

# ============================================================
# 主流程
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("月度宏观底牌报告开始执行")
    logger.info("=" * 60)

    # 环境变量预检
    required_vars = ["SMTP_SERVER", "SMTP_PORT", "SENDER_EMAIL", "SMTP_PASSWORD", "RECEIVER_EMAIL"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"缺少必要环境变量: {', '.join(missing)}")
        logger.error("请检查 .env 文件或 GitHub Secrets 配置")
        sys.exit(1)

    logger.info("环境变量校验通过, 开始抓取宏观数据...")

    # --- 抓取全部数据 ---
    data = fetch_monthly_bundle()

    # --- 检查本地数据文件是否过期 ---
    from utils.data_fetchers import DATA_DIR
    data_files = {
        "aisc_data.json": "AISC开采成本",
        "wgc_cb_gold.json": "WGC央行购金",
        "fomc_decisions.json": "FOMC政策声明",
    }
    for fname, label in data_files.items():
        fpath = DATA_DIR / fname
        if fpath.exists():
            mtime = datetime.fromtimestamp(fpath.stat().st_mtime)
            days_old = (datetime.now() - mtime).days
            if days_old > 90:
                logger.warning(f"⚠️ {label} 数据文件 ({fname}) 已 {days_old} 天未更新, 建议手动维护!")
        else:
            logger.warning(f"⚠️ {label} 数据文件 ({fname}) 不存在!")

    # --- 生成邮件标题 ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    month_cn = datetime.now().strftime("%Y年%m月")
    subject = f"【全球央行购金、黄金硬核开采成本与美联储最新货币政策月度报告】{today_str}"

    # --- 渲染 HTML ---
    logger.info("渲染 HTML 邮件...")
    html_body = render_monthly_html(data)

    # --- 发送邮件 ---
    logger.info(f"发送邮件 → {os.getenv('RECEIVER_EMAIL')}")
    success = send_html_email(subject=subject, html_body=html_body)

    if success:
        logger.info("✅ 月度宏观报告邮件发送成功!")
    else:
        logger.error("❌ 月度宏观报告邮件发送失败!")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("月度宏观底牌报告执行完毕")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
