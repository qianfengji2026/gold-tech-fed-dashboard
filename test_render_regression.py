#!/usr/bin/env python3
"""
渲染层回归测试: 用模拟的"生产环境完整数据"验证 render_daily_html 不崩溃。

背景: 2026-08-21 推送的新模块在 GitHub Actions 连续失败 6 天。
根因: 本地测试时 yfinance 限速导致数据为 None, 渲染代码被 if 跳过;
     生产环境数据正常返回, 触发 f-string 非法格式化 (Invalid format specifier)。
本测试用全字段填充的模拟数据 + 边界数据(None)双重验证渲染层。
"""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.html_templates import render_daily_html, render_monthly_html

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as e:
        print(f"  FAIL  {name}: {type(e).__name__}: {e}")
        failures.append(name)


def make_full_daily_bundle():
    """模拟生产环境: 所有数据源都成功返回的完整 bundle。"""
    return {
        # I: 黄金与通胀
        "gold": {
            "GC=F": {"price": 2650.4, "change_pct": 0.85, "prev_close": 2628.1},
            "GLD": {"price": 243.18, "change_pct": 0.82, "prev_close": 241.2},
        },
        "silver": {"price": 31.22, "change_pct": 1.35, "prev_close": 30.80},
        "gold_silver_ratio": {
            "ratio": 84.91,
            "gold_price": 2650.4,
            "silver_price": 31.22,
            "interpretation": "金银比处于极端高位(>80), 白银相对黄金被严重低估",
            "historical_avg_20yr": 60,
            "historical_avg_50yr": 55,
        },
        "breakeven": {"value": 2.35, "change": 0.02},
        "crb": {"price": 285.6, "change_pct": -0.44},
        "cpi_pce": {
            "cpi": {"value": 322.5, "date": "2026-07", "mom_pct": 0.15, "yoy_pct": 2.9},
            "core_pce": {"value": 128.9, "date": "2026-06", "mom_pct": 0.18, "yoy_pct": 2.7},
        },
        # II: 科技股
        "qqq": {"price": 512.3, "change_pct": 1.12, "volume": 38200000},
        "mag7": [
            {"ticker": "AAPL", "name": "苹果", "price": 232.5, "change_pct": 1.15, "volume": 55000000},
            {"ticker": "NVDA", "name": "英伟达", "price": 128.4, "change_pct": 2.31, "volume": 310000000},
        ],
        "vxn": {"value": 18.5, "change_pct": -3.2},
        "fear_greed": {"score": 71, "rating": "Greed"},
        "fedwatch": {
            "meeting_date": "2026-09-16",
            "current_rate": "4.25%-4.50%",
            "cut_prob": 62.5,
            "hold_prob": 36.8,
            "hike_prob": 0.7,
            "cut_details": [{"rate_range": "4.00%-4.25%", "probability": 62.5}],
            "max_prob_scenario": {"rate_range": "4.00%-4.25%", "probability": 62.5},
        },
        # V: 美元信用
        "treasury": {
            "yield_2y": {"value": 3.65, "prev": 3.67, "change": -0.02, "date": "2026-08-29"},
            "yield_10y": {"value": 3.89, "prev": 3.92, "change": -0.03, "date": "2026-08-29"},
            "yield_30y": {"value": 4.25, "prev": 4.28, "change": -0.03, "date": "2026-08-29"},
            "spread_2y_10y": 0.24,
            "spread_10y_30y": 0.36,
        },
        "dxy": {"value": 100.82, "prev_close": 101.10, "change_pct": -0.28},
        "dxy_analysis": {
            "value": 100.82,
            "prev_close": 101.10,
            "change_pct": -0.28,
            "trend_5d_pct": -1.42,
            "trend_direction": "显著下跌",
            "interpretation": "美元指数100.82, 处于中性偏弱区间(95-100), 美元承压但未破位",
        },
        "fed_bs": {"total_bn": 6615.2, "weekly_change_bn": -8.5, "date": "2026-08-27"},
        "tips": {"value": 1.78, "change": -0.02},
        "dollar_credit": "美元信用评级: AA (偏强运行)。10Y收益率3.89%回落, 债价回暖 | 2Y-10Y利差+0.24%, 曲线形态正常 | 美元指数100.82, 区间震荡 | 美联储资产负债表规模6615B, 基本持平 | 10Y实际利率1.78%, 美元购买力尚可",
        # VIII: COT
        "cot": {
            "report_date": "08/26/26",
            "gold": {
                "noncomm_long": 285123,
                "noncomm_short": 62489,
                "net_position": 222634,
                "spreading": 48210,
                "comm_long": 121340,
                "comm_short": 238950,
                "sentiment": "看多偏强",
                "open_interest": 418230,
            },
            "silver": {
                "noncomm_long": 68240,
                "noncomm_short": 18210,
                "net_position": 50030,
                "spreading": 32150,
                "comm_long": 28410,
                "comm_short": 51230,
                "sentiment": "极度看多",
                "open_interest": None,  # 边界: OI 缺失
            },
        },
        # IX: SPDR
        "spdr": {
            "holdings_tonnes": 1021.55,
            "change_tonnes": -1.28,
            "nav": 88.9,
            "source": "SPDR 官方 Archive CSV",
        },
        # X: 波动率指标
        "volatility": {
            "gvz": {"value": 16.42, "prev_close": 15.98, "change_pct": 2.75},
            "vxslv": {"value": 23.15, "prev_close": 24.10, "change_pct": -3.94},
            "ovx": {"value": 34.68, "prev_close": 33.20, "change_pct": 4.46},
            "copper_vol": {
                "value": 18.72,
                "method": "COMEX铜期货(HG=F) 21日年化已实现波动率 (LME铜波动率近似)",
            },
            "interpretation": "GVZ黄金波动率16.4, 中性区间(15-20) | OVX原油波动率34.7偏高(30-40), 关注油价波动对通胀路径的影响",
        },
        # XI: 国际要闻 (纯文字核心提炼)
        "news": {
            "items": [
                {
                    "title": "Fed officials signal caution on rate cuts as inflation cools",
                    "link": "https://example.com/news/1",
                    "source": "Reuters",
                    "published": "Fri, 25 Sep 2026 08:30:00 GMT",
                    "category": "fed_policy",
                    "category_label": "美联储与利率政策",
                    "category_icon": "🏦",
                    "core_title": "Fed officials signal caution on rate cuts as inflation cools",
                    "direction": "bearish",
                    "direction_label": "利空金银",
                    "key_figures": "",
                },
                {
                    "title": "中央银行持续增持黄金储备",
                    "link": "",
                    "source": "新华网",
                    "published": "",
                    "category": "central_bank",
                    "category_label": "央行动态/购金",
                    "category_icon": "🏛️",
                    "core_title": "中央银行持续增持黄金储备",
                    "direction": "bullish",
                    "direction_label": "利好金银",
                    "key_figures": "48吨",
                },
            ],
            "count": 2,
            "digest": "近7天共筛选出 2 条金银相关国际要闻, 焦点集中在: 美联储与利率政策(1条)、央行动态/购金(1条) | 消息面多空比: 利好1 vs 利空1, 多空消息均衡 — 利率预期变化是金银短期定价主线, 关注讲话与点阵图信号",
        },
        "tech_sentiment": "科技股情绪: 乐观偏多。Mag7 普涨, VXN 回落, 恐慌贪婪指数 71 (Greed)。",
        "fetch_time": "2026-08-30 05:02:33 UTC+8",
    }


def make_partial_daily_bundle():
    """模拟恶劣场景: 数据源大面积失败 (大量 None/缺失字段)。"""
    return {
        "gold": {},
        "breakeven": None,
        "crb": None,
        "cpi_pce": {"cpi": None, "core_pce": None},
        "qqq": None,
        "mag7": [],
        "vxn": None,
        "fear_greed": None,
        "fedwatch": None,
        "treasury": {},
        "dxy": None,
        "dxy_analysis": None,
        "fed_bs": None,
        "tips": None,
        "dollar_credit": "",
        "cot": None,
        "spdr": None,
        "gold_silver_ratio": None,
        "volatility": None,
        "news": None,
        "tech_sentiment": "",
        "fetch_time": "2026-08-30 05:02:33 UTC+8",
    }


def make_volatility_partial():
    """波动率指标部分缺失的边界场景 (只有 GVZ, 无 VXSLV/OVX/铜)。"""
    b = make_full_daily_bundle()
    b["volatility"] = {
        "gvz": {"value": 21.30, "prev_close": 20.10, "change_pct": 5.97},
        "interpretation": "GVZ黄金波动率21.3, 偏高(20-25), 黄金短期波动加剧",
    }
    b["news"] = {"items": [], "count": 0, "digest": ""}
    return b


def make_news_legacy_fields():
    """要闻字段为旧版结构 (无 category/digest) 的兼容场景。"""
    b = make_full_daily_bundle()
    b["news"] = {
        "items": [
            {"title": "Gold hits record high on safe haven demand",
             "link": "https://example.com/news/3", "source": "Bloomberg",
             "published": "Thu, 24 Sep 2026 10:00:00 GMT"},
        ],
        "count": 1,
    }
    return b


def make_spdr_partial():
    """SPDR 有持仓但 NAV 缺失的边界场景。"""
    b = make_full_daily_bundle()
    b["spdr"] = {"holdings_tonnes": 1021.55, "change_tonnes": None, "nav": None, "source": "SPDR 官网"}
    return b


def make_cot_sparse():
    """COT 解析出净持仓但 long/short/OI 全缺失的边界场景。"""
    b = make_full_daily_bundle()
    b["cot"] = {
        "gold": {"net_position": 222634, "sentiment": "中性"},
        "silver": None,
    }
    return b


def make_monthly_bundle():
    return {
        "aisc": {
            "global_avg_aisc": {"value": 1438, "quarter": "2026Q2", "yoy_change_pct": 8.2},
            "top_producers_margin": [
                {"producer": "Newmont", "ticker": "NEM", "aisc": 1220},
                {"producer": "Barrick", "ticker": "GOLD", "aisc": 1350},
            ],
        },
        "wgc_cb": {
            "global_central_bank_net_purchases": {
                "quarter": "2026Q2",
                "value": 183,
                "yoy_change_pct": 12.3,
            },
            "top_buyers": [
                {"rank": 1, "country": "波兰", "purchases_tonnes": 48, "total_reserves_tonnes": 420},
            ],
            "context": "全球央行持续增持黄金。",
            "historical_trend": [{"year": 2025, "total_tonnes": 1045}],
        },
        "cpi_pce": {
            "cpi": {"value": 322.5, "date": "2026-07", "mom_pct": 0.15, "yoy_pct": 2.9},
            "core_pce": None,
        },
        "fomc": {
            "rate_range": "4.25%-4.50%",
            "effective_rate": 4.33,
            "last_decision_date": "2026-07-29",
            "decision_summary": "维持利率不变, 关注通胀进展。",
            "dot_plot_median_2026": "3.9%",
            "dot_plot_median_2027": "3.4%",
        },
        "gold": {"GC=F": {"price": 2650.4, "change_pct": 0.85}},
        "fedwatch": {
            "meeting_date": "2026-09-16",
            "current_rate": "4.25%-4.50%",
            "cut_prob": 62.5,
            "hold_prob": 36.8,
            "hike_prob": 0.7,
        },
        "fetch_time": "2026-09-01 06:00:00 UTC+8",
    }


if __name__ == "__main__":
    print("=" * 60)
    print("渲染层回归测试 (模拟生产数据 + 边界数据)")
    print("=" * 60)

    cases = [
        ("每日-完整数据(生产场景)", lambda: render_daily_html(make_full_daily_bundle())),
        ("每日-全None(降级场景)", lambda: render_daily_html(make_partial_daily_bundle())),
        ("每日-SPDR缺NAV", lambda: render_daily_html(make_spdr_partial())),
        ("每日-COT字段稀疏", lambda: render_daily_html(make_cot_sparse())),
        ("每日-波动率部分缺失+要闻空", lambda: render_daily_html(make_volatility_partial())),
        ("每日-要闻旧版字段兼容", lambda: render_daily_html(make_news_legacy_fields())),
        ("月度-完整数据", lambda: render_monthly_html(make_monthly_bundle())),
    ]

    for name, fn in cases:
        check(name, fn)

    print("-" * 60)
    if failures:
        print(f"测试结果: ❌ {len(failures)} 项失败: {failures}")
        sys.exit(1)
    print("测试结果: ✅ 全部通过")
