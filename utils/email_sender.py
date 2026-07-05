"""
邮件发送模块 - 通过 SMTP 发送 HTML 格式看板邮件

敏感信息 (邮箱账号/密码) 从环境变量读取, 禁止硬编码。
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def send_html_email(
    subject: str,
    html_body: str,
    to_email: Optional[str] = None,
) -> bool:
    """
    发送 HTML 格式邮件。

    Args:
        subject:  邮件标题
        html_body: HTML 正文
        to_email: 收件人 (可选, 默认从环境变量 RECEIVER_EMAIL 取)

    Returns:
        True 发送成功, False 发送失败
    """
    smtp_server = os.getenv("SMTP_SERVER", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    sender_email = os.getenv("SENDER_EMAIL", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    receiver_email = (to_email or os.getenv("RECEIVER_EMAIL", "")).strip()

    # --- 配置校验 ---
    missing = []
    if not smtp_server:
        missing.append("SMTP_SERVER")
    if not sender_email:
        missing.append("SENDER_EMAIL")
    if not smtp_password:
        missing.append("SMTP_PASSWORD")
    if not receiver_email:
        missing.append("RECEIVER_EMAIL")

    if missing:
        logger.error(f"邮件发送失败: 缺少环境变量 {', '.join(missing)}")
        return False

    try:
        # 构建邮件
        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = subject
        msg["X-Mailer"] = "Gold-Tech-Fed-Dashboard/1.0"

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # 发送 (支持 SSL/TLS)
        if smtp_port == 465:
            # SSL 直连
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30) as server:
                server.login(sender_email, smtp_password)
                server.sendmail(sender_email, receiver_email, msg.as_string())
        else:
            # STARTTLS
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender_email, smtp_password)
                server.sendmail(sender_email, receiver_email, msg.as_string())

        logger.info(f"邮件发送成功 → {receiver_email} | 主题: {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP 认证失败: 请检查邮箱地址和授权码 (非登录密码)")
    except smtplib.SMTPConnectError:
        logger.error(f"SMTP 连接失败: 无法连接到 {smtp_server}:{smtp_port}")
    except smtplib.SMTPException as e:
        logger.error(f"SMTP 发送异常: {e}")
    except Exception as e:
        logger.error(f"邮件发送未预期错误: {e}", exc_info=True)

    return False
