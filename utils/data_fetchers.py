"""
数据获取核心模块 - 黄金、科技股与美联储宏观数据抓取器

涵盖五大维度:
1. 黄金价格 (GC=F)
2. 通胀预期 (5Y Breakeven / CRB / CPI / PCE)
3. 黄金开采成本 (AISC)
4. 科技股行情与情绪 (QQQ / Mag7 / VXN / Fear&Greed)
5. 美联储政策 (CME FedWatch / FOMC)

每条数据源独立容错, 单项失败不影响整体输出。
"""

import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ============================================================
# 常量与配置
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Mag 7 映射
MAG7_TICKERS: dict[str, str] = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "NVDA": "NVIDIA",
    "META": "Meta",
    "TSLA": "Tesla",
}


# FRED 系列 ID (通过 fredapi 或 CSV 下载)
FRED_SERIES: dict[str, str] = {
    "T5YIE": "5年期平衡通胀率",
    "CPIAUCSL": "消费者物价指数 (CPI)",
    "PCEPILFE": "核心 PCE (不含食品能源)",
    "DFF": "联邦基金有效利率",
}

# 请求超时设置
HTTP_TIMEOUT = 15

# 缓存目录
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 维护中提示
MAINTENANCE_MSG = "该项数据源正在维护中"


# ============================================================
# 工具函数
# ============================================================

def _safe_fetch(fetch_func, source_name: str, default: Any = None) -> Any:
    """通用安全抓取包装器: 捕获所有异常, 返回默认值。"""
    try:
        return fetch_func()
    except Exception as e:
        logger.warning(f"[{source_name}] 抓取失败: {e}", exc_info=True)
        return default


def _fmt_pct(value: Optional[float], decimals: int = 2) -> str:
    """格式化百分比字符串, 带正负号。"""
    if value is None:
        return MAINTENANCE_MSG
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}%"


def _fmt_price(value: Optional[float], decimals: int = 2) -> str:
    """格式化价格字符串。"""
    if value is None:
        return MAINTENANCE_MSG
    return f"${value:,.{decimals}f}"


def _trend_color(pct: Optional[float], reverse: bool = False) -> str:
    """
    涨跌颜色 (中国股市惯例: 涨=红, 跌=绿)。

    reverse=True 用于「坏指标」(如 VIX 涨是恐慌), 此时涨=绿, 跌=红。
    """
    if pct is None:
        return "#888888"
    is_positive = pct > 0
    if reverse:
        is_positive = not is_positive
    return "#E53935" if is_positive else "#43A047"  # red / green


# ============================================================
# 1. 黄金价格 (每日)
# ============================================================

def fetch_gold_price() -> dict:
    """获取黄金期货价格 (GC=F) 与现货 ETF (GLD)。"""
    def _fetch():
        tickers = yf.Tickers("GC=F GLD")
        result = {}
        for sym in ["GC=F", "GLD"]:
            try:
                t = tickers.tickers.get(sym)
                if t is None:
                    continue
                info = t.info if hasattr(t, "info") else {}
                hist = t.history(period="2d")
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
                current = None
                if not hist.empty:
                    current = float(hist["Close"].iloc[-1])
                elif prev_close:
                    current = float(prev_close)
                change_pct = None
                if current and prev_close:
                    change_pct = (current - float(prev_close)) / float(prev_close) * 100
                result[sym] = {
                    "price": current,
                    "prev_close": float(prev_close) if prev_close else None,
                    "change_pct": change_pct,
                    "name": "黄金期货" if sym == "GC=F" else "黄金ETF",
                }
            except Exception as e:
                logger.warning(f"黄金数据 [{sym}] 抓取失败: {e}")
                result[sym] = {"price": None, "prev_close": None, "change_pct": None, "name": sym}
        return result

    return _safe_fetch(_fetch, "黄金价格", {})


# ============================================================
# 2. 通胀数据 (每日预期 + 月度官方)
# ============================================================

def fetch_breakeven_inflation() -> dict:
    """
    获取 5年期平衡通胀率 (T5YIE, 来自 FRED)。

    优先使用 fredapi (需 API Key), 降级使用 FRED CSV 下载。
    """
    def _fetch():
        try:
            # 尝试 fredapi
            import os
            api_key = os.getenv("FRED_API_KEY", "")
            if api_key:
                from fredapi import Fred
                fred = Fred(api_key=api_key)
                series = fred.get_series("T5YIE")
                if not series.empty:
                    latest = float(series.dropna().iloc[-1])
                    prev = float(series.dropna().iloc[-2]) if len(series.dropna()) > 1 else latest
                    return {
                        "value": latest,
                        "prev": prev,
                        "change": latest - prev,
                        "source": "FRED T5YIE (fredapi)",
                    }
            raise RuntimeError("FRED API Key 未配置, 尝试 CSV 下载")
        except Exception as e:
            logger.warning(f"fredapi 失败, 尝试 CSV: {e}")

        try:
            # 降级: FRED 公开 CSV
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T5YIE&cosd=2025-01-01"
            df = pd.read_csv(url)
            df.columns = ["date", "value"]
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df.dropna()
            if not df.empty:
                latest = float(df["value"].iloc[-1])
                prev = float(df["value"].iloc[-2]) if len(df) > 1 else latest
                return {
                    "value": latest,
                    "prev": prev,
                    "change": latest - prev,
                    "source": "FRED T5YIE (CSV)",
                }
        except Exception as e2:
            logger.warning(f"FRED CSV 也失败: {e2}")

        return None

    return _safe_fetch(_fetch, "5Y平衡通胀率")


def fetch_crb_index() -> dict:
    """获取 CRB 大宗商品指数 ETF (DBC)。"""
    def _fetch():
        t = yf.Ticker("DBC")
        hist = t.history(period="5d")
        info = t.info or {}
        if hist.empty:
            return None
        current = float(hist["Close"].iloc[-1])
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        change_pct = None
        if prev_close:
            change_pct = (current - float(prev_close)) / float(prev_close) * 100
        return {"price": current, "prev_close": float(prev_close) if prev_close else None, "change_pct": change_pct}

    return _safe_fetch(_fetch, "CRB大宗商品指数")


def fetch_cpi_pce_data() -> dict:
    """获取最新 CPI 与 核心 PCE 数据 (月度, 来自 FRED)。"""
    def _fetch():
        import os
        api_key = os.getenv("FRED_API_KEY", "")
        result = {"cpi": None, "core_pce": None}

        def _fred_series(series_id: str):
            if api_key:
                from fredapi import Fred
                fred = Fred(api_key=api_key)
                s = fred.get_series(series_id)
                if not s.empty:
                    s = s.dropna()
                    latest_val = float(s.iloc[-1])
                    prev_val = float(s.iloc[-2]) if len(s) > 1 else latest_val
                    mom = (latest_val - prev_val) / prev_val * 100
                    yoy_val = float(s.iloc[-13]) if len(s) > 12 else prev_val
                    yoy = (latest_val - yoy_val) / yoy_val * 100
                    return {
                        "value": latest_val,
                        "date": str(s.index[-1].date()),
                        "mom_pct": mom,
                        "yoy_pct": yoy,
                    }
            return None

        result["cpi"] = _fred_series("CPIAUCSL")
        result["core_pce"] = _fred_series("PCEPILFE")
        return result

    return _safe_fetch(_fetch, "CPI/PCE数据", {"cpi": None, "core_pce": None})


# ============================================================
# 3. 黄金开采成本 AISC (季度)
# ============================================================

def fetch_aisc_data() -> dict:
    """从本地 JSON 文件加载全球黄金 AISC 数据 (按季度手动维护)。"""
    def _fetch():
        aisc_file = DATA_DIR / "aisc_data.json"
        if not aisc_file.exists():
            logger.warning("AISC 数据文件不存在")
            return None
        with open(aisc_file, "r", encoding="utf-8") as f:
            return json.load(f)

    return _safe_fetch(_fetch, "AISC开采成本")


def fetch_wgc_cb_gold() -> dict:
    """从本地 JSON 文件加载 WGC 央行购金数据 (按季度手动维护)。"""
    def _fetch():
        wgc_file = DATA_DIR / "wgc_cb_gold.json"
        if not wgc_file.exists():
            logger.warning("WGC 央行购金数据文件不存在")
            return None
        with open(wgc_file, "r", encoding="utf-8") as f:
            return json.load(f)

    return _safe_fetch(_fetch, "WGC央行购金")


# ============================================================
# 4. 科技股行情与情绪 (每日)
# ============================================================

def fetch_qqq_data() -> dict:
    """获取纳指100 ETF (QQQ) 行情。"""
    def _fetch():
        t = yf.Ticker("QQQ")
        hist = t.history(period="5d")
        info = t.info or {}
        if hist.empty:
            return None
        current = float(hist["Close"].iloc[-1])
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        change_pct = None
        volume = None
        if prev_close:
            change_pct = (current - float(prev_close)) / float(prev_close) * 100
        if "Volume" in hist.columns:
            volume = int(hist["Volume"].iloc[-1])
        high_52w = info.get("fiftyTwoWeekHigh")
        low_52w = info.get("fiftyTwoWeekLow")
        return {
            "ticker": "QQQ",
            "name": "纳斯达克100 ETF",
            "price": current,
            "prev_close": float(prev_close) if prev_close else None,
            "change_pct": change_pct,
            "volume": volume,
            "high_52w": high_52w,
            "low_52w": low_52w,
        }

    return _safe_fetch(_fetch, "QQQ行情")


def fetch_mag7_data() -> list[dict]:
    """获取科技七巨头 (Mag 7) 涨跌幅与成交量。"""
    def _fetch():
        tickers_list = list(MAG7_TICKERS.keys())
        results = []
        for sym in tickers_list:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="5d")
                info = t.info or {}
                if hist.empty:
                    results.append({"ticker": sym, "name": MAG7_TICKERS[sym], "price": None, "change_pct": None, "volume": None, "status": "error"})
                    continue
                current = float(hist["Close"].iloc[-1])
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
                change_pct = None
                if prev_close:
                    change_pct = (current - float(prev_close)) / float(prev_close) * 100
                volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else None
                results.append({
                    "ticker": sym,
                    "name": MAG7_TICKERS[sym],
                    "price": current,
                    "prev_close": float(prev_close) if prev_close else None,
                    "change_pct": change_pct,
                    "volume": volume,
                    "status": "ok",
                })
            except Exception as e:
                logger.warning(f"Mag7 [{sym}] 抓取失败: {e}")
                results.append({"ticker": sym, "name": MAG7_TICKERS[sym], "price": None, "change_pct": None, "volume": None, "status": "error"})
        return results

    return _safe_fetch(_fetch, "科技七巨头", [])


def fetch_vxn_data() -> dict:
    """获取科技股波动率指数 (VXN)。"""
    def _fetch():
        t = yf.Ticker("^VXN")
        hist = t.history(period="5d")
        info = t.info or {}
        if hist.empty:
            return None
        current = float(hist["Close"].iloc[-1])
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        change_pct = None
        if prev_close:
            change_pct = (current - float(prev_close)) / float(prev_close) * 100
        return {
            "value": current,
            "prev_close": float(prev_close) if prev_close else None,
            "change_pct": change_pct,
        }

    return _safe_fetch(_fetch, "VXN波动率")


def fetch_cnn_fear_greed() -> dict:
    """
    获取 CNN 恐慌与贪婪指数。
    使用 fear-greed 包 (调用 CNN 内部 API, 无需 API Key)。
    """
    def _fetch():
        import fear_greed
        data = fear_greed.get()
        return {
            "score": data.get("score"),
            "rating": data.get("rating"),
            "timestamp": data.get("timestamp"),
            "previous_close": data.get("history", {}).get("1d"),
            "previous_1_week": data.get("history", {}).get("1w"),
            "previous_1_month": data.get("history", {}).get("1m"),
            "previous_1_year": data.get("history", {}).get("1y"),
        }

    return _safe_fetch(_fetch, "CNN恐慌贪婪指数")


def analyze_tech_sentiment(mag7: list[dict], qqq: dict, vxn: dict, fg: dict) -> str:
    """
    基于多维数据综合研判科技股市场情绪。

    判定逻辑:
    - QQQ 涨幅 > 2% + Fear&Greed > 75 → "多头狂热"
    - Fear&Greed > 75 → "极度贪婪"
    - Fear&Greed 60-75 + QQQ 上涨 → "乐观偏多"
    - Fear&Greed 40-60 → "中性观望"
    - Fear&Greed 25-40 → "谨慎偏空"
    - VXN > 30 或 Fear&Greed < 25 → "恐慌回调"
    - QQQ 跌幅 > 3% → "恐慌抛售"
    - 默认 → "震荡整理"
    """
    fg_score = fg.get("score") if fg else None
    qqq_pct = qqq.get("change_pct") if qqq else None
    vxn_val = vxn.get("value") if vxn else None

    # 统计 Mag7 涨跌比
    up_count = sum(1 for m in mag7 if m.get("change_pct") and m["change_pct"] > 0)
    down_count = sum(1 for m in mag7 if m.get("change_pct") and m["change_pct"] < 0)

    # 判定逻辑
    if qqq_pct is not None and qqq_pct > 2 and (fg_score is not None and fg_score > 75):
        sentiment = "多头狂热"
        detail = f"QQQ大涨{_fmt_pct(qqq_pct)}, 恐慌贪婪指数{fg_score}(极度贪婪), Mag7中{up_count}涨{down_count}跌"
    elif fg_score is not None and fg_score > 75:
        sentiment = "极度贪婪"
        detail = f"恐慌贪婪指数{fg_score}, 市场情绪过热, QQQ涨跌{_fmt_pct(qqq_pct)}"
    elif fg_score is not None and 60 <= fg_score <= 75:
        sentiment = "乐观偏多"
        detail = f"恐慌贪婪指数{fg_score}(贪婪), QQQ{_fmt_pct(qqq_pct)}, Mag7中{up_count}涨{down_count}跌"
    elif fg_score is not None and 40 <= fg_score < 60:
        sentiment = "中性观望"
        detail = f"恐慌贪婪指数{fg_score}(中性), 市场方向不明"
    elif fg_score is not None and 25 <= fg_score < 40:
        sentiment = "谨慎偏空"
        detail = f"恐慌贪婪指数{fg_score}(恐惧), 需关注下方支撑"
    elif (vxn_val is not None and vxn_val > 30) or (fg_score is not None and fg_score < 25):
        sentiment = "恐慌回调"
        detail = f"VXN={vxn_val or 'N/A'}, 恐慌贪婪指数{fg_score or 'N/A'}, 恐慌情绪蔓延"
    elif qqq_pct is not None and qqq_pct < -3:
        sentiment = "恐慌抛售"
        detail = f"QQQ暴跌{_fmt_pct(qqq_pct)}, Mag7全线下挫"
    else:
        sentiment = "震荡整理"
        detail = f"QQQ{_fmt_pct(qqq_pct)}, 恐慌贪婪指数{fg_score or 'N/A'}, 市场横盘等待方向"

    return f"{sentiment} | {detail}"


# ============================================================
# 5. 美联储政策 (每日概率 + FOMC)
# ============================================================

def fetch_cme_fedwatch() -> dict:
    """
    获取下一次 FOMC 会议的利率概率分布。
    使用 cme-fedwatch 包 (基于 CME 结算价 + FRED 数据计算, 无需 API Key)。
    """
    def _fetch():
        from cme_fedwatch import get_probabilities
        data = get_probabilities("next")

        effr = data.get("effr")
        current_target = data.get("current_target", "")

        meetings = data.get("meetings", [])
        if not meetings:
            return None

        next_meeting = meetings[0]
        meeting_date = next_meeting.get("date", "Unknown")
        probs = next_meeting.get("probabilities", {})

        # 解析概率: 当前利率区间是多少, 然后判断各区间是加息/降息/维持
        current_range = current_target.strip().replace("%", "")
        # current_target 格式如 "3.50%-3.75%"
        try:
            parts = current_range.split("-")
            current_lower = float(parts[0])
        except Exception:
            # fallback: 从 EFFR 推断
            current_lower = effr - 0.125 if effr else None

        probabilities = []
        hike_prob = 0.0
        cut_prob = 0.0
        hold_prob = 0.0

        for rate_range, prob in probs.items():
            prob_val = float(prob)
            clean = rate_range.strip().replace("%", "")
            try:
                r_parts = clean.split("-")
                r_lower = float(r_parts[0])
            except Exception:
                r_lower = None

            if current_lower is not None and r_lower is not None:
                if r_lower > current_lower + 0.01:
                    action = "hike"
                    hike_prob += prob_val
                elif r_lower < current_lower - 0.01:
                    action = "cut"
                    cut_prob += prob_val
                else:
                    action = "unch"
                    hold_prob += prob_val
            else:
                action = "unch"
                hold_prob += prob_val

            probabilities.append({
                "rate_range": rate_range,
                "probability": prob_val,
                "action": action,
            })

        # 降息明细
        cut_details = [p for p in probabilities if p.get("action") == "cut" and p["probability"] > 0.1]

        # 最大概率情景
        max_prob_item = max(probabilities, key=lambda x: x["probability"]) if probabilities else None

        return {
            "meeting_date": meeting_date,
            "current_rate": current_target,
            "hike_prob": round(hike_prob, 1),
            "cut_prob": round(cut_prob, 1),
            "hold_prob": round(hold_prob, 1),
            "max_prob_scenario": max_prob_item,
            "cut_details": cut_details,
            "all_probabilities": probabilities,
        }

    return _safe_fetch(_fetch, "CME FedWatch")


def fetch_fomc_summary() -> dict:
    """
    获取最近一次 FOMC 会议决策摘要。

    通过 FRED 获取有效联邦基金利率 (DFF) 的最新变化,
    结合本地维护的政策声明文件。

    注: FOMC 详细政策声明建议配合本地手动维护的 data/fomc_decisions.json。
    """
    def _fetch():
        result = {
            "effective_rate": None,
            "rate_range": "未知",
            "last_decision_date": "未知",
            "decision_summary": "详见 data/fomc_decisions.json 手动维护",
            "dot_plot_median_2026": "未知",
            "dot_plot_median_2027": "未知",
        }

        # 尝试获取有效联邦基金利率
        try:
            import os
            api_key = os.getenv("FRED_API_KEY", "")
            if api_key:
                from fredapi import Fred
                fred = Fred(api_key=api_key)
                dff = fred.get_series("DFF")
                if not dff.empty:
                    dff = dff.dropna()
                    result["effective_rate"] = float(dff.iloc[-1])
                    result["last_data_date"] = str(dff.index[-1].date())
        except Exception as e:
            logger.warning(f"FRED DFF 获取失败: {e}")

        # 尝试读取本地 FOMC 决策文件
        fomc_file = DATA_DIR / "fomc_decisions.json"
        if fomc_file.exists():
            try:
                with open(fomc_file, "r", encoding="utf-8") as f:
                    local = json.load(f)
                latest = local.get("latest_decision", {})
                result["rate_range"] = latest.get("rate_range", result["rate_range"])
                result["last_decision_date"] = latest.get("date", result["last_decision_date"])
                result["decision_summary"] = latest.get("summary", result["decision_summary"])
                result["dot_plot_median_2026"] = latest.get("dot_plot_2026", result["dot_plot_median_2026"])
                result["dot_plot_median_2027"] = latest.get("dot_plot_2027", result["dot_plot_median_2027"])
            except Exception as e:
                logger.warning(f"本地 FOMC 文件读取失败: {e}")

        return result

    return _safe_fetch(_fetch, "FOMC决策摘要")


# ============================================================
# 批量获取主入口
# ============================================================

def fetch_daily_bundle() -> dict:
    """批量获取每日看板所需全部数据 (带并发优化)。"""
    bundle = {}

    # 逐个获取 (yfinance 不支持并发 Ticker, 使用顺序请求)
    bundle["gold"] = fetch_gold_price()
    bundle["breakeven"] = fetch_breakeven_inflation()
    bundle["crb"] = fetch_crb_index()
    bundle["qqq"] = fetch_qqq_data()
    bundle["mag7"] = fetch_mag7_data()
    bundle["vxn"] = fetch_vxn_data()
    bundle["fear_greed"] = fetch_cnn_fear_greed()
    bundle["fedwatch"] = fetch_cme_fedwatch()

    # 情绪研判
    bundle["tech_sentiment"] = analyze_tech_sentiment(
        bundle["mag7"], bundle["qqq"], bundle["vxn"], bundle["fear_greed"]
    )

    bundle["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC+8")
    return bundle


def fetch_monthly_bundle() -> dict:
    """批量获取月度/季度宏观报告所需全部数据。"""
    bundle = {}

    bundle["aisc"] = fetch_aisc_data()
    bundle["wgc_cb"] = fetch_wgc_cb_gold()
    bundle["cpi_pce"] = fetch_cpi_pce_data()
    bundle["fomc"] = fetch_fomc_summary()
    bundle["gold"] = fetch_gold_price()  # 当月金价参考
    bundle["fedwatch"] = fetch_cme_fedwatch()  # 当前利率概率

    bundle["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC+8")
    return bundle
