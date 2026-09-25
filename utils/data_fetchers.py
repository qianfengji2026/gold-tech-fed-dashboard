"""
数据获取核心模块 - 黄金、科技股与美联储宏观数据抓取器

涵盖七大维度:
1. 黄金价格 (GC=F) + 通胀预期 (5Y Breakeven / CRB / CPI / PCE)
2. 黄金开采成本 (AISC) + 央行购金 (WGC)
3. 科技股行情与情绪 (QQQ / Mag7 / VXN / Fear&Greed)
4. 美联储政策 (CME FedWatch / FOMC)
5. 美元信用评估 (美债收益率 / DXY / 美联储资产负债表 / TIPS实际利率)
6. 贵金属持仓 (COT 报告 / SPDR 黄金 ETF 持仓)
7. 衍生指标 (金银比 / 美元指数独立分析)

每条数据源独立容错, 单项失败不影响整体输出。
"""

import json
import time
import logging
from datetime import datetime, timedelta, timezone, timezone
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
# 1.5 白银价格 (用于金银比计算)
# ============================================================

def fetch_silver_price() -> dict:
    """获取白银期货价格 (SI=F)。"""
    def _fetch():
        # 尝试多个可能的 ticker
        ticker_candidates = ["SI=F", "SIL=F"]
        for sym in ticker_candidates:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="2d")
                if hist.empty:
                    continue
                info = t.info if hasattr(t, "info") else {}
                prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
                current = float(hist["Close"].iloc[-1])
                if not prev_close and len(hist) >= 2:
                    prev_close = float(hist["Close"].iloc[-2])
                change_pct = None
                if current and prev_close:
                    change_pct = (current - float(prev_close)) / float(prev_close) * 100
                return {
                    "price": current,
                    "prev_close": float(prev_close) if prev_close else None,
                    "change_pct": change_pct,
                    "ticker": sym,
                    "name": "白银期货",
                }
            except Exception as e:
                logger.warning(f"白银数据 [{sym}] 抓取失败: {e}")
                continue
        return None
    return _safe_fetch(_fetch, "白银价格")


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
# 6. 美元信用涨跌评估 (每日)
# ============================================================

def fetch_treasury_yields() -> dict:
    """
    获取美债收益率: 2年期、10年期、30年期及期限利差。

    数据源: FRED (优先 fredapi, 降级 CSV) + yfinance 备用。
    """
    def _fetch():
        import os
        api_key = os.getenv("FRED_API_KEY", "")
        result = {}

        # FRED 系列
        fred_series = {
            "DGS2": "yield_2y",
            "DGS10": "yield_10y",
            "DGS30": "yield_30y",
        }

        use_fred = False
        if api_key:
            try:
                from fredapi import Fred
                fred = Fred(api_key=api_key)
                for sid, key in fred_series.items():
                    s = fred.get_series(sid)
                    if not s.empty:
                        s = s.dropna()
                        latest = float(s.iloc[-1])
                        prev = float(s.iloc[-2]) if len(s) > 1 else latest
                        result[key] = {
                            "value": latest,
                            "prev": prev,
                            "change": round(latest - prev, 3),
                            "date": str(s.index[-1].date()),
                            "source": "FRED",
                        }
                use_fred = True
            except Exception as e:
                logger.warning(f"FRED 国债收益率获取失败, 尝试 yfinance: {e}")

        if not use_fred or not result:
            # 降级: yfinance
            yf_map = {"^IRX": "yield_2y", "^TNX": "yield_10y", "^TYX": "yield_30y"}
            # ^IRX 是13周, 用 ^FVX (5年) 不对, 2Y 用 IEF 近似不行
            # 实际: ^IRX=13周, ^FVX=5年, ^TNX=10年, ^TYX=30年
            # 对于2年期, yfinance 没有 ^TWO, 但可以用 ETF "TU" 近似, 这里用 ^TNX + ^TYX 作主要
            yf_map_actual = {"^TNX": "yield_10y", "^TYX": "yield_30y"}
            for sym, key in yf_map_actual.items():
                try:
                    t = yf.Ticker(sym)
                    hist = t.history(period="2d")
                    if not hist.empty:
                        current = float(hist["Close"].iloc[-1])
                        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                        result[key] = {
                            "value": current,
                            "prev": prev,
                            "change": round(current - prev, 3),
                            "source": "yfinance",
                        }
                except Exception as e:
                    logger.warning(f"yfinance {sym} 获取失败: {e}")

            # 2年期从 FRED CSV 降级
            if "yield_2y" not in result:
                try:
                    df = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2&cosd=2025-01-01")
                    df.columns = ["date", "value"]
                    df["value"] = pd.to_numeric(df["value"], errors="coerce")
                    df = df.dropna()
                    if not df.empty:
                        latest = float(df["value"].iloc[-1])
                        prev = float(df["value"].iloc[-2]) if len(df) > 1 else latest
                        result["yield_2y"] = {
                            "value": latest,
                            "prev": prev,
                            "change": round(latest - prev, 3),
                            "source": "FRED CSV",
                        }
                except Exception as e:
                    logger.warning(f"FRED CSV DGS2 失败: {e}")

        # 计算利差
        y2 = result.get("yield_2y", {}).get("value")
        y10 = result.get("yield_10y", {}).get("value")
        y30 = result.get("yield_30y", {}).get("value")
        if y2 is not None and y10 is not None:
            result["spread_2y_10y"] = round(y10 - y2, 3)
        if y10 is not None and y30 is not None:
            result["spread_10y_30y"] = round(y30 - y10, 3)

        return result if result else None

    return _safe_fetch(_fetch, "美债收益率")


def fetch_dxy_data() -> dict:
    """
    获取美元指数 (DXY) 行情。

    数据源: yfinance (DX-Y.NYB)
    """
    def _fetch():
        t = yf.Ticker("DX-Y.NYB")
        hist = t.history(period="5d")
        info = t.info or {}
        if hist.empty:
            return None
        current = float(hist["Close"].iloc[-1])
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        if not prev_close and len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
        change_pct = None
        if prev_close:
            change_pct = (current - float(prev_close)) / float(prev_close) * 100
        return {
            "value": current,
            "prev_close": float(prev_close) if prev_close else None,
            "change_pct": change_pct,
        }

    return _safe_fetch(_fetch, "美元指数DXY")


def fetch_fed_balance_sheet() -> dict:
    """
    获取美联储资产负债表规模 (WALCL) 及周变化。

    数据源: FRED WALCL (周更)
    """
    def _fetch():
        import os
        api_key = os.getenv("FRED_API_KEY", "")
        result = {"total": None, "weekly_change": None, "source": "FRED"}

        if api_key:
            try:
                from fredapi import Fred
                fred = Fred(api_key=api_key)
                s = fred.get_series("WALCL")
                if not s.empty:
                    s = s.dropna()
                    latest = float(s.iloc[-1])
                    prev = float(s.iloc[-2]) if len(s) > 1 else latest
                    weekly_change = latest - prev
                    result["total"] = latest
                    result["weekly_change"] = weekly_change
                    result["date"] = str(s.index[-1].date())
                    result["total_bn"] = latest / 1000  # 十亿美元 (WALCL原始单位: 百万美元)
                    result["weekly_change_bn"] = weekly_change / 1000
            except Exception as e:
                logger.warning(f"FRED WALCL 获取失败, 尝试 CSV: {e}")
                try:
                    df = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL&cosd=2025-01-01")
                    df.columns = ["date", "value"]
                    df["value"] = pd.to_numeric(df["value"], errors="coerce")
                    df = df.dropna()
                    if not df.empty:
                        latest = float(df["value"].iloc[-1])
                        prev = float(df["value"].iloc[-2]) if len(df) > 1 else latest
                        result["total"] = latest
                        result["weekly_change"] = latest - prev
                        result["total_bn"] = latest / 1000  # 十亿美元 (WALCL原始单位: 百万美元)
                        result["weekly_change_bn"] = (latest - prev) / 1000
                        result["date"] = df["date"].iloc[-1]
                        result["source"] = "FRED CSV"
                except Exception as e2:
                    logger.warning(f"FRED WALCL CSV 也失败: {e2}")
        else:
            try:
                df = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL&cosd=2025-01-01")
                df.columns = ["date", "value"]
                df["value"] = pd.to_numeric(df["value"], errors="coerce")
                df = df.dropna()
                if not df.empty:
                    latest = float(df["value"].iloc[-1])
                    prev = float(df["value"].iloc[-2]) if len(df) > 1 else latest
                    result["total"] = latest
                    result["weekly_change"] = latest - prev
                    result["total_bn"] = latest / 1000  # 十亿美元 (WALCL原始单位: 百万美元)
                    result["weekly_change_bn"] = (latest - prev) / 1000
                    result["date"] = df["date"].iloc[-1]
                    result["source"] = "FRED CSV"
            except Exception as e:
                logger.warning(f"FRED WALCL CSV 失败: {e}")

        return result if result.get("total") else None

    return _safe_fetch(_fetch, "美联储资产负债表")


def fetch_tips_spread() -> dict:
    """
    获取 10年期TIPS-通胀保值国债收益率 (DFII10), 用于衡量实际利率。

    实际利率上升 = 美元信用走强信号之一。
    数据源: FRED DFII10
    """
    def _fetch():
        import os
        api_key = os.getenv("FRED_API_KEY", "")
        result = {"value": None, "prev": None, "change": None, "source": "FRED"}

        if api_key:
            try:
                from fredapi import Fred
                fred = Fred(api_key=api_key)
                s = fred.get_series("DFII10")
                if not s.empty:
                    s = s.dropna()
                    latest = float(s.iloc[-1])
                    prev = float(s.iloc[-2]) if len(s) > 1 else latest
                    result["value"] = latest
                    result["prev"] = prev
                    result["change"] = round(latest - prev, 3)
                    result["date"] = str(s.index[-1].date())
            except Exception as e:
                logger.warning(f"FRED DFII10 获取失败: {e}")

        if result.get("value") is None:
            try:
                df = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10&cosd=2025-01-01")
                df.columns = ["date", "value"]
                df["value"] = pd.to_numeric(df["value"], errors="coerce")
                df = df.dropna()
                if not df.empty:
                    latest = float(df["value"].iloc[-1])
                    prev = float(df["value"].iloc[-2]) if len(df) > 1 else latest
                    result["value"] = latest
                    result["prev"] = prev
                    result["change"] = round(latest - prev, 3)
                    result["date"] = df["date"].iloc[-1]
                    result["source"] = "FRED CSV"
            except Exception as e:
                logger.warning(f"FRED DFII10 CSV 失败: {e}")

        return result if result.get("value") is not None else None

    return _safe_fetch(_fetch, "TIPS实际利率")


def analyze_dollar_credit(
    treasury: dict,
    dxy: dict,
    fed_bs: dict,
    tips: dict,
    breakeven: dict,
) -> str:
    """
    美元信用综合研判引擎。

    多维信号:
    - 美债收益率走势 (10Y 飙升 = 信用承压)
    - 2Y-10Y 利差 (倒挂 = 衰退信号, 信用受损)
    - 美元指数 DXY (走强 = 信用暂时坚挺)
    - 美联储缩表进度 (缩表 = 信用收缩)
    - 实际利率 TIPS (上升 = 美元走强信号)
    - 通胀预期 (飙升 = 美元购买力受损)

    输出: 一句话研判 + 信用评级(AAA/AA/BBB等)
    """
    signals = []
    score = 0  # 正=信用走强, 负=信用走弱

    # 1. 美债10Y收益率变化
    y10 = treasury.get("yield_10y") if treasury else None
    if y10:
        change = y10.get("change")
        val = y10.get("value")
        if change is not None:
            if change > 0.05:
                signals.append(f"10Y收益率飙升{change:+.3f}%至{val:.3f}%, 债价下跌、偿债成本上行")
                score -= 2
            elif change > 0.02:
                signals.append(f"10Y收益率小幅上行{change:+.3f}%至{val:.3f}%")
                score -= 1
            elif change < -0.05:
                signals.append(f"10Y收益率回落{change:+.3f}%至{val:.3f}%, 债价回暖")
                score += 1
            else:
                signals.append(f"10Y收益率{val:.3f}%, 基本持稳")

    # 2. 2Y-10Y 期限利差
    spread = treasury.get("spread_2y_10y") if treasury else None
    if spread is not None:
        if spread < 0:
            signals.append(f"2Y-10Y利差{spread:+.3f}%倒挂, 衰退预期升温、美元长期信用受损")
            score -= 3
        elif spread < 0.2:
            signals.append(f"2Y-10Y利差{spread:+.3f}%, 曲线平坦化, 增长隐忧")
            score -= 1
        elif spread > 0.5:
            signals.append(f"2Y-10Y利差{spread:+.3f}%, 曲线陡峭, 经济扩张预期")
            score += 2
        else:
            signals.append(f"2Y-10Y利差{spread:+.3f}%, 曲线形态正常")

    # 3. 美元指数 DXY
    dxy_pct = dxy.get("change_pct") if dxy else None
    dxy_val = dxy.get("value") if dxy else None
    if dxy_pct is not None:
        if dxy_pct > 0.5:
            signals.append(f"美元指数{dxy_val:.2f}(+{dxy_pct:.2f}%), 避险买盘推升")
            score += 2
        elif dxy_pct > 0:
            signals.append(f"美元指数{dxy_val:.2f}(+{dxy_pct:.2f}%), 温和走强")
            score += 1
        elif dxy_pct < -0.5:
            signals.append(f"美元指数{dxy_val:.2f}({dxy_pct:.2f}%), 美元承压贬值")
            score -= 2
        else:
            signals.append(f"美元指数{dxy_val:.2f}({dxy_pct:.2f}%), 区间震荡")

    # 4. 美联储资产负债表
    if fed_bs and fed_bs.get("weekly_change_bn") is not None:
        wc = fed_bs["weekly_change_bn"]
        total = fed_bs.get("total_bn")
        if wc < -5:
            signals.append(f"美联储缩表{wc:+.1f}B(总规模{total:.0f}B), 流动性持续收缩")
            score -= 1
        elif wc > 5:
            signals.append(f"美联储扩表{wc:+.1f}B(总规模{total:.0f}B), 释放流动性")
            score += 1
        else:
            signals.append(f"美联储资产负债表规模{total:.0f}B, 基本持平")

    # 5. 实际利率 TIPS
    if tips and tips.get("value") is not None:
        real_rate = tips["value"]
        if real_rate > 1.5:
            signals.append(f"10Y实际利率{real_rate:.2f}%, 高实际利率支撑美元")
            score += 2
        elif real_rate > 0.5:
            signals.append(f"10Y实际利率{real_rate:.2f}%, 美元购买力尚可")
            score += 1
        elif real_rate < 0:
            signals.append(f"10Y实际利率{real_rate:.2f}%, 实际利率为负, 美元购买力受损")
            score -= 2
        else:
            signals.append(f"10Y实际利率{real_rate:.2f}%, 偏低")

    # 6. 通胀预期
    be_val = breakeven.get("value") if breakeven else None
    if be_val is not None:
        if be_val > 3.0:
            signals.append(f"5Y通胀预期{be_val:.2f}%, 远超2%目标, 货币信用侵蚀加速")
            score -= 2
        elif be_val < 1.5:
            signals.append(f"5Y通胀预期{be_val:.2f}%, 低于目标, 美元信用暂时稳固")
            score += 1

    # 综合评级
    if score >= 5:
        rating = "AAA"
        verdict = "美元信用强势走稳"
    elif score >= 2:
        rating = "AA"
        verdict = "美元信用偏强运行"
    elif score >= 0:
        rating = "A"
        verdict = "美元信用中性持平"
    elif score >= -2:
        rating = "BBB"
        verdict = "美元信用边际承压"
    elif score >= -5:
        rating = "BB"
        verdict = "美元信用走弱"
    else:
        rating = "B"
        verdict = "美元信用显著恶化"

    detail = " | ".join(signals) if signals else "数据维度不足, 请检查数据源"

    return f"{verdict} | 信用评级: {rating} | {detail}"


# ============================================================
# 7. 金银比 (Gold/Silver Ratio)
# ============================================================

def fetch_gold_silver_ratio() -> dict:
    """
    计算金银比 (Gold/Silver Ratio)。

    金银比 = 黄金价格 / 白银价格
    历史参照:
    - 20年均值: ~60
    - 50年均值: ~55
    - 极端高位 (80-90): 白银相对低估, 通常预示白银补涨
    - 极端低位 (40-50): 白银相对高估, 通常预示白银回调
    """
    def _fetch():
        gold = fetch_gold_price()
        silver = fetch_silver_price()

        gold_futures = gold.get("GC=F", {}) if gold else {}
        gold_price = gold_futures.get("price")
        silver_price = silver.get("price") if silver else None

        if not gold_price or not silver_price or silver_price == 0:
            return None

        ratio = gold_price / silver_price

        # 历史背景解读
        context_parts = []
        if ratio > 80:
            context_parts.append("金银比处于极端高位(>80), 白银相对黄金被严重低估, 历史上往往预示白银补涨行情")
        elif ratio > 70:
            context_parts.append("金银比偏高(70-80), 白银相对低估, 关注白银补涨机会")
        elif ratio > 60:
            context_parts.append("金银比略高于20年均值(~60), 白银估值中性偏低估")
        elif ratio < 50:
            context_parts.append("金银比低于50, 白银相对黄金表现强势, 注意白银回调风险")
        elif ratio < 40:
            context_parts.append("金银比处于极端低位(<40), 白银相对黄金被严重高估, 历史上往往预示白银回调")
        else:
            context_parts.append(f"金银比在{ratio:.1f}附近, 处于20年均值(~60)区间, 两者估值相对均衡")

        context_parts.append(f"(20年均值约60, 50年均值约55)")

        return {
            "ratio": round(ratio, 2),
            "gold_price": gold_price,
            "silver_price": silver_price,
            "interpretation": " | ".join(context_parts),
            "historical_avg_20yr": 60,
            "historical_avg_50yr": 55,
        }

    return _safe_fetch(_fetch, "金银比")


# ============================================================
# 8. 美元指数独立分析 (DXY 独立展示)
# ============================================================

def fetch_dxy_analysis() -> dict:
    """
    美元指数独立分析模块。

    在基本 DXY 行情基础上, 增加 5 日趋势分析和综合解读。
    """
    def _fetch():
        t = yf.Ticker("DX-Y.NYB")
        hist = t.history(period="5d")
        info = t.info or {}
        if hist.empty:
            return None

        current = float(hist["Close"].iloc[-1])
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        if not prev_close and len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
        change_pct = None
        if prev_close:
            change_pct = (current - float(prev_close)) / float(prev_close) * 100

        # 5日趋势
        closes = [float(c) for c in hist["Close"].values]
        if len(closes) >= 2:
            trend_5d_pct = (closes[-1] - closes[0]) / closes[0] * 100
        else:
            trend_5d_pct = 0

        # 趋势方向
        if trend_5d_pct > 1:
            trend_direction = "强势上行"
        elif trend_5d_pct > 0.3:
            trend_direction = "温和走强"
        elif trend_5d_pct < -1:
            trend_direction = "显著下跌"
        elif trend_5d_pct < -0.3:
            trend_direction = "温和走弱"
        else:
            trend_direction = "区间震荡"

        # 综合解读
        if current > 105:
            interpretation = f"美元指数{current:.2f}, 处于强势区间(>105), 全球避险需求或美联储鹰派预期支撑"
        elif current > 100:
            interpretation = f"美元指数{current:.2f}, 处于中性偏强区间(100-105), 整体走势稳健"
        elif current > 95:
            interpretation = f"美元指数{current:.2f}, 处于中性偏弱区间(95-100), 美元承压但未破位"
        else:
            interpretation = f"美元指数{current:.2f}, 处于弱势区间(<95), 美元购买力显著下滑"

        return {
            "value": current,
            "prev_close": float(prev_close) if prev_close else None,
            "change_pct": change_pct,
            "trend_5d_pct": round(trend_5d_pct, 2),
            "trend_direction": trend_direction,
            "interpretation": interpretation,
        }

    return _safe_fetch(_fetch, "美元指数独立分析")


# ============================================================
# 9. COMEX 黄金/白银期货非商业持仓 (COT 报告)
# ============================================================

def fetch_cot_data() -> dict:
    """
    获取并解析 CFTC 持仓报告 (COT) 中 COMEX 黄金/白银的非商业持仓数据。

    数据源: CFTC Legacy Futures Only 报告 (TXT)
    URL: https://www.cftc.gov/dea/futures/deacmxsf.txt

    解析 COMEX 黄金 (Code-088691) 和 COMEX 白银 (Code-084691) 的非商业持仓。
    """
    def _fetch():
        url = "https://www.cftc.gov/dea/futures/deacmxsf.txt"
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        resp.encoding = "utf-8"
        text = resp.text

        result = {"gold": None, "silver": None, "report_date": None}

        # 提取报告日期 (第一行)
        lines = text.split("\n")
        for line in lines[:5]:
            line = line.strip()
            if line and len(line) > 10:
                # 日期格式如: "06/30/26" 或 "2026-06-30"
                import re
                date_match = re.search(r'(\d{2}/\d{2}/\d{2,4})', line)
                if date_match:
                    result["report_date"] = date_match.group(1)

        # 解析黄金 (Code-088691)
        gold_section = None
        silver_section = None
        for i, line in enumerate(lines):
            if "088691" in line and "GOLD" in line.upper():
                gold_section = i
            if "084691" in line and "SILVER" in line.upper():
                silver_section = i

        if gold_section is not None:
            result["gold"] = _parse_cot_commodity(lines, gold_section, "黄金")

        if silver_section is not None:
            result["silver"] = _parse_cot_commodity(lines, silver_section, "白银")

        return result

    return _safe_fetch(_fetch, "COT持仓报告", {"gold": None, "silver": None, "report_date": None})


def _parse_cot_commodity(lines: list, start_idx: int, name: str) -> dict:
    """
    从 CFTC 文本行中解析单个商品的 COT 持仓数据。

    CFTC Legacy 格式:
    - 找到商品代码行后, 扫描到 "COMMITMENTS" 行
    - 下一行即为数据行, 固定宽度格式
    - 列: NON-COMMERCIAL LONG | SHORT | SPREADING | COMMERCIAL LONG | SHORT
    """
    import re

    # 从 start_idx 开始扫描
    for i in range(start_idx, min(start_idx + 30, len(lines))):
        line = lines[i]
        if "COMMITMENTS" in line.upper():
            # 数据在下一行
            if i + 1 < len(lines):
                data_line = lines[i + 1]
                # 打印调试信息
                logger.debug(f"COT {name} data line: {data_line.strip()[:120]}")
                # 固定宽度解析: 每列通常 10-12 个字符
                # 尝试用正则提取数字
                numbers = re.findall(r'[\d,]+', data_line)
                if len(numbers) >= 5:
                    try:
                        noncomm_long = int(numbers[0].replace(",", ""))
                        noncomm_short = int(numbers[1].replace(",", ""))
                        spreading = int(numbers[2].replace(",", ""))
                        comm_long = int(numbers[3].replace(",", ""))
                        comm_short = int(numbers[4].replace(",", ""))

                        net_position = noncomm_long - noncomm_short

                        # 非商业持仓解读阈值
                        if name == "黄金":
                            if net_position > 250000:
                                sentiment = "极度看多"
                            elif net_position > 200000:
                                sentiment = "看多偏强"
                            elif net_position > 150000:
                                sentiment = "中性偏多"
                            elif net_position > 100000:
                                sentiment = "中性"
                            elif net_position > 50000:
                                sentiment = "中性偏空"
                            else:
                                sentiment = "显著看空"
                        else:  # 白银
                            if net_position > 40000:
                                sentiment = "极度看多"
                            elif net_position > 30000:
                                sentiment = "看多偏强"
                            elif net_position > 20000:
                                sentiment = "中性偏多"
                            elif net_position > 10000:
                                sentiment = "中性"
                            elif net_position > 5000:
                                sentiment = "中性偏空"
                            else:
                                sentiment = "显著看空"

                        return {
                            "noncomm_long": noncomm_long,
                            "noncomm_short": noncomm_short,
                            "net_position": net_position,
                            "spreading": spreading,
                            "comm_long": comm_long,
                            "comm_short": comm_short,
                            "sentiment": sentiment,
                            "open_interest": int(numbers[7]) if len(numbers) > 7 else None,
                        }
                    except (ValueError, IndexError) as e:
                        logger.warning(f"COT {name} 数字解析失败: {e}, raw: {numbers}")

    logger.warning(f"COT {name} 未找到数据行")
    return None


# ============================================================
# 10. SPDR 黄金 ETF 持仓变化
# ============================================================

def fetch_spdr_holdings() -> dict:
    """
    获取全球最大黄金 ETF SPDR (GLD) 的持仓变化数据。

    数据源:
    1. 优先: SPDR 官网 (https://www.spdrgoldshares.com)
    2. 降级: 新浪财经 / 东方财富等中文财经网站

    返回: 持仓量 (吨), 日变化 (吨), 总资产净值 (十亿美元)
    """
    def _fetch():
        result = {"holdings_tonnes": None, "change_tonnes": None, "nav": None, "source": "未知"}

        # 方案 0 (优先): SPDR 官方每日持仓 archive CSV (含历史, 可计算日变化)
        try:
            csv_urls = [
                "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archiveEN.csv",
                "https://www.spdrgoldshares.com/media/GLD/file/GLD_US_archiveEN.csv",
            ]
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            import io
            for csv_url in csv_urls:
                resp = requests.get(csv_url, headers=headers, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200 and resp.text.strip():
                    df = pd.read_csv(io.StringIO(resp.text))
                    # 列名宽松匹配: 日期 / 金衡盎司 / 吨 / NAV
                    cols = {c.lower().strip(): c for c in df.columns}
                    tonnes_col = next((c for k, c in cols.items() if "tonne" in k), None)
                    nav_col = next((c for k, c in cols.items() if "nav" in k), None)
                    if tonnes_col is None:
                        continue
                    df[tonnes_col] = pd.to_numeric(df[tonnes_col], errors="coerce")
                    df = df.dropna(subset=[tonnes_col])
                    if df.empty:
                        continue
                    latest_tonnes = float(df[tonnes_col].iloc[-1])
                    result["holdings_tonnes"] = round(latest_tonnes, 2)
                    if len(df) >= 2:
                        result["change_tonnes"] = round(latest_tonnes - float(df[tonnes_col].iloc[-2]), 2)
                    if nav_col is not None:
                        nav_val = pd.to_numeric(df[nav_col], errors="coerce").iloc[-1]
                        if pd.notna(nav_val) and nav_val > 0:
                            # CSV中NAV为美元, 转为十亿美元
                            result["nav"] = round(float(nav_val) / 1e9, 1) if float(nav_val) > 1e6 else round(float(nav_val), 1)
                    result["source"] = "SPDR 官方 Archive CSV"
                    break
        except Exception as e:
            logger.warning(f"SPDR archive CSV 抓取失败: {e}")

        # 方案 1: 尝试 SPDR 官网页面 (仅当 archive CSV 未成功时)
        if result["holdings_tonnes"] is None:
            try:
                url = "https://www.spdrgoldshares.com"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text = soup.get_text()

                    # 尝试提取持仓量 (吨)
                    import re
                    # 常见模式: "1,038.93 tonnes" 或 "1038.93 tonnes"
                    tonnes_match = re.search(r'([\d,]+\.?\d*)\s*tonnes', text, re.IGNORECASE)
                    # 或 "Total Ounces: 33,402,695"
                    ounces_match = re.search(r'([\d,]+)\s*ounces', text, re.IGNORECASE)

                    if tonnes_match:
                        result["holdings_tonnes"] = float(tonnes_match.group(1).replace(",", ""))
                        result["source"] = "SPDR 官网"
                    elif ounces_match:
                        ounces = float(ounces_match.group(1).replace(",", ""))
                        result["holdings_tonnes"] = round(ounces / 32150.7466, 2)  # 金衡盎司→吨
                        result["source"] = "SPDR 官网 (盎司换算)"

                    # 提取 NAV
                    nav_match = re.search(r'([\d,]+\.?\d*)\s*(?:billion|B)\s*(?:USD|\$)', text, re.IGNORECASE)
                    if nav_match:
                        result["nav"] = float(nav_match.group(1).replace(",", ""))
                    # 另一种 NAV 格式: $68.5 billion
                    nav_match2 = re.search(r'\$\s*([\d,]+\.?\d*)\s*(?:billion|B)', text, re.IGNORECASE)
                    if nav_match2 and not result["nav"]:
                        result["nav"] = float(nav_match2.group(1).replace(",", ""))
            except Exception as e:
                logger.warning(f"SPDR 官网抓取失败: {e}")

        # 方案 2: 如果官网失败, 尝试新浪财经或东方财富
        if result["holdings_tonnes"] is None:
            try:
                # 新浪财经搜索
                search_url = "https://search.sina.com.cn/?q=SPDR+黄金+持仓量&range=all&c=news&sort=time"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                resp = requests.get(search_url, headers=headers, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text = soup.get_text()
                    import re
                    tonnes_match = re.search(r'(\d+\.?\d*)\s*吨', text)
                    if tonnes_match:
                        result["holdings_tonnes"] = float(tonnes_match.group(1))
                        result["source"] = "新浪财经"
            except Exception as e:
                logger.warning(f"新浪财经抓取失败: {e}")

        if result["holdings_tonnes"] is None:
            try:
                # 东方财富
                url = "https://finance.eastmoney.com/a/czqyw.html"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text = soup.get_text()
                    import re
                    tonnes_match = re.search(r'(\d+\.?\d*)\s*吨', text)
                    if tonnes_match:
                        result["holdings_tonnes"] = float(tonnes_match.group(1))
                        result["source"] = "东方财富"
            except Exception as e:
                logger.warning(f"东方财富抓取失败: {e}")

        return result if result["holdings_tonnes"] is not None else None

    return _safe_fetch(_fetch, "SPDR黄金持仓")


# ============================================================
# 10. 贵金属/工业金属波动率指标 (GVZ / VXSLV / 铜波动率)
# ============================================================

def fetch_volatility_indices() -> dict:
    """
    获取贵金属/原油与工业金属波动率指标。

    - GVZ:   CBOE 黄金 ETF 期权隐含波动率指数 (yfinance: ^GVZ)
    - VXSLV: CBOE 白银 ETF 期权隐含波动率指数 (yfinance: ^VXSLV)
    - OVX:   CBOE 原油 ETF 期权隐含波动率指数 (yfinance: ^OVX)
    - LME铜波动率: 无公开实时 ticker, 用 COMEX 铜期货 (HG=F) 21日年化已实现
      波动率近似, 并在返回中标注计算方法。

    返回:
    {
        "gvz":         {"value", "prev_close", "change_pct"},
        "vxslv":       {"value", "prev_close", "change_pct"},
        "ovx":         {"value", "prev_close", "change_pct"},
        "copper_vol":  {"value", "method"},
        "interpretation": "..."
    }
    """
    def _fetch():
        result = {}

        # --- GVZ / VXSLV / OVX ---
        for key, ticker, name in (
            ("gvz", "^GVZ", "GVZ"),
            ("vxslv", "^VXSLV", "VXSLV"),
            ("ovx", "^OVX", "OVX"),
        ):
            try:
                hist = yf.Ticker(ticker).history(period="1mo")
                if hist.empty or len(hist) < 2:
                    continue
                current = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
                change_pct = (current - prev) / prev * 100
                result[key] = {
                    "value": round(current, 2),
                    "prev_close": round(prev, 2),
                    "change_pct": round(change_pct, 2),
                }
            except Exception as e:
                logger.warning(f"{name} 波动率指数获取失败: {e}")

        # --- LME 铜波动率 (HG=F 已实现波动率近似) ---
        try:
            hist = yf.Ticker("HG=F").history(period="3mo")
            if not hist.empty:
                closes = hist["Close"].dropna()
                if len(closes) >= 22:
                    rets = closes.pct_change().dropna().tail(21)
                    if len(rets) >= 10:
                        rv = float(np.std(rets, ddof=1) * np.sqrt(252) * 100)
                        result["copper_vol"] = {
                            "value": round(rv, 2),
                            "method": "COMEX铜期货(HG=F) 21日年化已实现波动率 (LME铜波动率近似)",
                        }
        except Exception as e:
            logger.warning(f"铜波动率计算失败: {e}")

        if not result:
            return None

        # --- 综合解读 ---
        interp = []
        gvz_val = result.get("gvz", {}).get("value")
        if gvz_val:
            if gvz_val > 25:
                interp.append(f"GVZ黄金波动率{gvz_val:.1f}, 处于高位(>25), 黄金价格短期波动风险显著放大")
            elif gvz_val > 20:
                interp.append(f"GVZ黄金波动率{gvz_val:.1f}, 偏高(20-25), 黄金短期波动加剧")
            elif gvz_val > 15:
                interp.append(f"GVZ黄金波动率{gvz_val:.1f}, 中性区间(15-20)")
            else:
                interp.append(f"GVZ黄金波动率{gvz_val:.1f}, 低位(<15), 黄金走势平稳")
        vxslv_val = result.get("vxslv", {}).get("value")
        if gvz_val and vxslv_val:
            if vxslv_val > gvz_val * 1.3:
                interp.append(f"VXSLV白银波动率({vxslv_val:.1f})显著高于GVZ({gvz_val:.1f}), 白银投机波动更剧烈, 注意仓位控制")
        ovx_val = result.get("ovx", {}).get("value")
        if ovx_val:
            if ovx_val > 40:
                interp.append(f"OVX原油波动率{ovx_val:.1f}处于高位(>40), 能源市场剧烈波动, 通胀预期与避险需求或推升金银")
            elif ovx_val > 30:
                interp.append(f"OVX原油波动率{ovx_val:.1f}偏高(30-40), 关注油价波动对通胀路径的影响")
            else:
                interp.append(f"OVX原油波动率{ovx_val:.1f}处于常态区间")
        cu_val = result.get("copper_vol", {}).get("value")
        if cu_val:
            if cu_val > 25:
                interp.append(f"铜波动率{cu_val:.1f}偏高, 工业金属市场定价宏观不确定性上升")
            else:
                interp.append(f"铜波动率{cu_val:.1f}处于常态区间")
        result["interpretation"] = " | ".join(interp) if interp else ""
        return result

    return _safe_fetch(_fetch, "贵金属波动率指标")


# ============================================================
# 11. 金银相关国际要闻 (Google News RSS)
# ============================================================

_NEWS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 关键词: 任何一条命中即认为与金银宏观相关
_NEWS_KEYWORDS = (
    "gold", "silver", "bullion", "precious metal",
    "central bank", "fed ", "fomc", "rate cut", "rate hike", "inflation",
    "tariff", "ecb", "bank of japan", "recession", "safe haven",
    "黄金", "白银", "央行", "美联储", "降息", "加息", "通胀", "关税", "避险",
)

# 要闻分类规则: (类别key, 中文标签, 图标, 匹配关键词) 按顺序优先匹配
_NEWS_CATEGORIES = (
    ("central_bank", "央行动态/购金", "🏛️",
     ("central bank", "cb gold", "gold buying", "gold reserves", "pboc",
      "央行", "购金", "增持黄金", "储备")),
    ("fed_policy", "美联储与利率政策", "🏦",
     ("fed", "fomc", "rate cut", "rate hike", "powell", "monetary policy",
      "美联储", "降息", "加息", "货币政策")),
    ("inflation", "通胀与经济数据", "📊",
     ("inflation", "cpi", "pce", "payroll", "jobs report", "gdp", "recession",
      "通胀", "非农", "就业")),
    ("geopolitics", "关税与地缘政治", "🌐",
     ("tariff", "war", "sanction", "conflict", "geopolit", "election",
      "关税", "地缘", "制裁", "冲突")),
    ("market", "金银行情与避险", "🪙",
     ("gold", "silver", "bullion", "safe haven", "rally", "surge", "plunge",
      "record high", "黄金", "白银", "避险", "新高")),
)


def _classify_news(title: str) -> tuple:
    """按标题关键词将要闻归类, 返回 (类别key, 中文标签, 图标)。默认归入行情避险。"""
    low = title.lower()
    for key, label, icon, kws in _NEWS_CATEGORIES:
        if any(k in low for k in kws):
            return key, label, icon
    return "market", "金银行情与避险", "🪙"


def _build_news_digest(items: list) -> str:
    """根据分类统计自动生成要闻综述段落。"""
    if not items:
        return ""
    cat_count = {}
    for it in items:
        cat_count[it.get("category_label", "其他")] = cat_count.get(it.get("category_label", "其他"), 0) + 1
    # 按数量降序
    ranked = sorted(cat_count.items(), key=lambda x: x[1], reverse=True)
    parts = [f"近7天共筛选出 {len(items)} 条金银相关国际要闻, 焦点集中在: "]
    parts.append("、".join(f"{label}({cnt}条)" for label, cnt in ranked[:3]))
    # 对焦点主题补充解读提示
    top_cat = ranked[0][0] if ranked else ""
    hints = {
        "美联储与利率政策": " — 利率预期变化是金银短期定价主线, 关注讲话与点阵图信号",
        "央行动态/购金": " — 央行购金是金价中长期支撑, 关注官方储备数据",
        "通胀与经济数据": " — 数据强弱直接影响降息路径, 金银波动或放大",
        "关税与地缘政治": " — 避险情绪升温利好金银, 关注事态升级",
        "金银行情与避险": " — 行情类消息居多, 注意技术位与资金流向",
    }
    for hint_key, hint in hints.items():
        if top_cat.startswith(hint_key[:4]):
            parts.append(hint)
            break
    return "".join(parts)


def fetch_gold_news(max_items: int = 8, days: int = 7) -> dict:
    """
    抓取近期影响黄金/白银价格的国际要闻。

    使用 Google News RSS 搜索 (无需 API Key):
    - "gold OR silver price" 行情面
    - "central bank gold buying" 央行购金/货币政策面

    过滤: 近 N 天 + 标题含相关关键词; 去重后按时间倒序取前 max_items 条。
    若全部早于时间窗口, 则保留最新 max_items 条兜底。
    """
    def _fetch():
        import urllib.parse
        import xml.etree.ElementTree as ET
        from email.utils import parsedate_to_datetime

        queries = [
            "gold price OR silver price OR bullion",
            "central bank gold buying OR fed rate gold",
        ]
        seen_titles = set()
        items = []
        cutoff = datetime.utcnow() - timedelta(days=days)

        for q in queries:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en"
            )
            try:
                resp = requests.get(url, headers={"User-Agent": _NEWS_UA},
                                    timeout=HTTP_TIMEOUT)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
            except Exception as e:
                logger.warning(f"要闻RSS抓取失败 ({q}): {e}")
                continue

            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                src_el = item.find("source")
                source = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
                # 先去除 Google News 的 " - 来源" 后缀, 再去重
                # (同一标题不同来源只保留一条)
                if " - " in title and source:
                    head, _, tail = title.rpartition(" - ")
                    if tail.strip().lower() == source.strip().lower():
                        title = head.strip()
                if not title or title.lower() in seen_titles:
                    continue
                # 标题小写关键词过滤
                low = title.lower()
                if not any(k in low for k in _NEWS_KEYWORDS):
                    continue
                seen_titles.add(title.lower())
                pub_str = (item.findtext("pubDate") or "").strip()
                pub_dt = None
                try:
                    if pub_str:
                        pub_dt = parsedate_to_datetime(pub_str)
                except Exception:
                    pass
                items.append({
                    "title": title,
                    "link": link,
                    "source": source,
                    "published": pub_str,
                    "published_dt": pub_dt,
                })

        if not items:
            return None

        # 时间过滤 (带时区的转 UTC 比较); 无时间的项保留
        def _to_utc(dt):
            if dt is None:
                return None
            try:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                return dt.replace(tzinfo=None)

        recent = [it for it in items
                  if it["published_dt"] is None
                  or (_to_utc(it["published_dt"]) or cutoff) >= cutoff]
        final = recent if recent else items
        # 排序: 有时间的按时间倒序在前, 无时间垫底
        final = sorted(
            final,
            key=lambda x: _to_utc(x["published_dt"]) or cutoff - timedelta(days=99),
            reverse=True,
        )[:max_items]

        # 分类并生成综述
        out_items = []
        for it in final:
            cat_key, cat_label, cat_icon = _classify_news(it["title"])
            out_items.append({
                "title": it["title"],
                "link": it["link"],
                "source": it["source"],
                "published": it["published"],
                "category": cat_key,
                "category_label": cat_label,
                "category_icon": cat_icon,
            })

        return {
            "items": out_items,
            "count": len(out_items),
            "digest": _build_news_digest(out_items),
        }

    return _safe_fetch(_fetch, "金银国际要闻")


# ============================================================
# 批量获取主入口
# ============================================================

def fetch_daily_bundle() -> dict:
    """批量获取每日看板所需全部数据 (带并发优化)。"""
    bundle = {}

    # 逐个获取 (yfinance 不支持并发 Ticker, 使用顺序请求)
    bundle["gold"] = fetch_gold_price()
    bundle["silver"] = fetch_silver_price()
    bundle["gold_silver_ratio"] = fetch_gold_silver_ratio()
    bundle["breakeven"] = fetch_breakeven_inflation()
    bundle["crb"] = fetch_crb_index()
    bundle["cpi_pce"] = fetch_cpi_pce_data()  # 每日看板也展示 CPI/PCE
    bundle["qqq"] = fetch_qqq_data()
    bundle["mag7"] = fetch_mag7_data()
    bundle["vxn"] = fetch_vxn_data()
    bundle["fear_greed"] = fetch_cnn_fear_greed()
    bundle["fedwatch"] = fetch_cme_fedwatch()

    # 美元信用评估维度
    bundle["treasury"] = fetch_treasury_yields()
    bundle["dxy"] = fetch_dxy_data()
    bundle["dxy_analysis"] = fetch_dxy_analysis()  # 独立分析
    bundle["fed_bs"] = fetch_fed_balance_sheet()
    bundle["tips"] = fetch_tips_spread()

    # 贵金属持仓
    bundle["cot"] = fetch_cot_data()
    bundle["spdr"] = fetch_spdr_holdings()

    # 波动率指标与国际要闻
    bundle["volatility"] = fetch_volatility_indices()
    bundle["news"] = fetch_gold_news()

    # 情绪研判
    bundle["tech_sentiment"] = analyze_tech_sentiment(
        bundle["mag7"], bundle["qqq"], bundle["vxn"], bundle["fear_greed"]
    )

    # 美元信用综合研判
    bundle["dollar_credit"] = analyze_dollar_credit(
        bundle["treasury"], bundle["dxy"], bundle["fed_bs"], bundle["tips"], bundle["breakeven"]
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
    bundle["silver"] = fetch_silver_price()
    bundle["gold_silver_ratio"] = fetch_gold_silver_ratio()
    bundle["fedwatch"] = fetch_cme_fedwatch()  # 当前利率概率

    # 美元信用评估维度 (月度报告也纳入)
    bundle["treasury"] = fetch_treasury_yields()
    bundle["dxy"] = fetch_dxy_data()
    bundle["dxy_analysis"] = fetch_dxy_analysis()
    bundle["fed_bs"] = fetch_fed_balance_sheet()
    bundle["tips"] = fetch_tips_spread()

    # 贵金属持仓
    bundle["cot"] = fetch_cot_data()
    bundle["spdr"] = fetch_spdr_holdings()

    bundle["dollar_credit"] = analyze_dollar_credit(
        bundle["treasury"], bundle["dxy"], bundle["fed_bs"], bundle["tips"], bundle.get("breakeven", {})
    )

    bundle["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC+8")
    return bundle
