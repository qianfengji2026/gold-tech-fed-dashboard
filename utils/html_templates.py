"""
HTML 邮件模板模块 - 为每日看板和月度报告生成专业的 HTML 邮件正文

设计风格: 深色金融仪表盘风格, 适合邮件客户端渲染 (内联CSS, 无外部依赖)。
"""

from datetime import datetime
from typing import Any, Optional


# ============================================================
# 通用 CSS 样式
# ============================================================

BASE_STYLE = """
<style>
    body { margin: 0; padding: 0; background: #f4f6f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; }
    .container { max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
    .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: #fff; padding: 28px 32px; text-align: center; }
    .header h1 { margin: 0 0 6px 0; font-size: 22px; font-weight: 700; letter-spacing: 1px; }
    .header .subtitle { font-size: 13px; opacity: 0.8; }
    .header .date-badge { display: inline-block; background: rgba(255,255,255,0.15); border-radius: 20px; padding: 4px 16px; font-size: 12px; margin-top: 8px; }
    .section { padding: 20px 28px; border-bottom: 1px solid #eef0f4; }
    .section:last-child { border-bottom: none; }
    .section-title { font-size: 16px; font-weight: 700; color: #1a1a2e; margin: 0 0 16px 0; padding-left: 12px; border-left: 4px solid #e6b422; }
    .metric-row { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
    .metric-card { flex: 1; min-width: 140px; background: #f8f9fc; border-radius: 8px; padding: 14px 16px; text-align: center; }
    .metric-label { font-size: 12px; color: #888; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-value { font-size: 20px; font-weight: 700; color: #1a1a2e; }
    .metric-change { font-size: 13px; font-weight: 600; margin-top: 4px; }
    .up { color: #E53935; }       /* 涨=红(中国惯例) */
    .down { color: #43A047; }     /* 跌=绿(中国惯例) */
    .neutral { color: #888; }
    .vix-up { color: #43A047; }   /* VIX 涨 = 恐慌缓解 = 绿 */
    .vix-down { color: #E53935; }  /* VIX 跌 = 恐慌上升 = 红 */
    table.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    table.data-table th { background: #f0f2f5; color: #666; font-weight: 600; padding: 10px 12px; text-align: left; border-bottom: 2px solid #ddd; }
    table.data-table td { padding: 10px 12px; border-bottom: 1px solid #eef0f4; }
    table.data-table tr:hover { background: #fafbfc; }
    .sentiment-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 13px; letter-spacing: 0.5px; }
    .sentiment-extreme-greed { background: #ffebee; color: #c62828; border: 1px solid #ef9a9a; }
    .sentiment-greed { background: #fff3e0; color: #e65100; border: 1px solid #ffcc80; }
    .sentiment-neutral { background: #f5f5f5; color: #616161; border: 1px solid #e0e0e0; }
    .sentiment-fear { background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; }
    .sentiment-panic { background: #fce4ec; color: #880e4f; border: 1px solid #f48fb1; }
    .prob-bar-container { background: #eef0f4; border-radius: 4px; height: 20px; overflow: hidden; margin: 6px 0; }
    .prob-bar { height: 100%; border-radius: 4px; display: inline-block; transition: width 0.3s; }
    .prob-cut { background: linear-gradient(90deg, #43A047, #66BB6A); }
    .prob-hold { background: linear-gradient(90deg, #78909C, #90A4AE); }
    .prob-hike { background: linear-gradient(90deg, #E53935, #EF5350); }
    .footer { background: #f8f9fc; padding: 16px 28px; text-align: center; font-size: 11px; color: #999; }
    .warn-badge { background: #fff3e0; color: #e65100; padding: 3px 10px; border-radius: 4px; font-size: 11px; }
    .divider { height: 1px; background: #eef0f4; margin: 16px 0; }
    .kpi-big { font-size: 28px; font-weight: 800; }
    @media (max-width: 600px) {
        .metric-row { flex-direction: column; }
        .metric-card { min-width: auto; }
    }
</style>
"""


# ============================================================
# 辅助函数
# ============================================================

def _fmt_pct(value, decimals=2):
    """格式化百分比。"""
    if value is None:
        return '<span class="neutral">N/A</span>'
    sign = "+" if value > 0 else ""
    cls = "up" if value > 0 else ("down" if value < 0 else "neutral")
    return f'<span class="{cls}">{sign}{value:.{decimals}f}%</span>'


def _fmt_price(value, decimals=2):
    """格式化价格。"""
    if value is None:
        return "N/A"
    return f"${value:,.{decimals}f}"


def _fmt_num(value, spec=",.0f", prefix="", suffix=""):
    """安全格式化数字: None/非数值时返回 N/A, 避免渲染崩溃。"""
    if value is None or isinstance(value, str):
        return "N/A"
    try:
        return f"{prefix}{value:{spec}}{suffix}"
    except (ValueError, TypeError):
        return "N/A"


def _change_class(pct, reverse=False):
    """返回 CSS 类名: up(涨红) / down(跌绿) / neutral."""
    if pct is None:
        return "neutral"
    if pct == 0:
        return "neutral"
    is_pos = pct > 0
    if reverse:
        is_pos = not is_pos
    return "up" if is_pos else "down"


def _sentiment_class(sentiment_text: str) -> str:
    """根据情绪文字返回对应 CSS 类。"""
    s = sentiment_text
    if "多头狂热" in s:
        return "sentiment-extreme-greed"
    if "极度贪婪" in s:
        return "sentiment-extreme-greed"
    if "乐观" in s:
        return "sentiment-greed"
    if "中性" in s or "震荡" in s:
        return "sentiment-neutral"
    if "谨慎" in s:
        return "sentiment-fear"
    if "恐慌" in s:
        return "sentiment-panic"
    return "sentiment-neutral"


def _sentiment_label(sentiment_text: str) -> str:
    """从情绪文本提取短标签。"""
    s = sentiment_text
    if "多头狂热" in s:
        return "多头狂热"
    if "极度贪婪" in s:
        return "极度贪婪"
    if "乐观偏多" in s:
        return "乐观偏多"
    if "中性观望" in s:
        return "中性观望"
    if "谨慎偏空" in s:
        return "谨慎偏空"
    if "恐慌抛售" in s:
        return "恐慌抛售"
    if "恐慌回调" in s:
        return "恐慌回调"
    if "震荡" in s:
        return "震荡整理"
    return "待评估"


# ============================================================
# 每日看板 HTML
# ============================================================

def render_daily_html(data: dict) -> str:
    """渲染每日高频看板 HTML 邮件。"""
    today = datetime.now().strftime("%Y-%m-%d")
    gold = data.get("gold", {})
    breakeven = data.get("breakeven")
    crb = data.get("crb")
    qqq = data.get("qqq")
    mag7 = data.get("mag7", [])
    vxn = data.get("vxn")
    fg = data.get("fear_greed")
    fedwatch = data.get("fedwatch")
    sentiment = data.get("tech_sentiment", "")
    fetch_time = data.get("fetch_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    gold_futures = gold.get("GC=F", {}) if gold else {}
    gold_etf = gold.get("GLD", {}) if gold else {}

    # 情绪标签
    s_label = _sentiment_label(sentiment)
    s_cls = _sentiment_class(sentiment)

    parts = []

    # --- 头部 ---
    parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body>
{BASE_STYLE}
<div class="container">

<div class="header">
    <h1>每日黄金通胀预期、美股科技股情绪、美联储降息概率、美元信用评估、贵金属持仓、波动率与国际要闻看板</h1>
    <div class="subtitle">Daily Gold · Inflation · Tech Sentiment · Fed Policy · Dollar Credit · Precious Metals</div>
    <div class="date-badge">{today}</div>
</div>
""")

    # --- 第一部分: 黄金与通胀 ---
    cpi_pce = data.get("cpi_pce", {})
    cpi = cpi_pce.get("cpi") if cpi_pce else None
    core_pce = cpi_pce.get("core_pce") if cpi_pce else None

    parts.append("""
<div class="section">
    <div class="section-title">I. 黄金与通胀预期</div>
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">黄金期货 (GC=F)</div>
            <div class="metric-value kpi-big">{gold_futures_price}</div>
            <div class="metric-change {gold_futures_cls}">{gold_futures_change}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">黄金ETF (GLD)</div>
            <div class="metric-value kpi-big">{gold_etf_price}</div>
            <div class="metric-change {gold_etf_cls}">{gold_etf_change}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">5Y 平衡通胀率</div>
            <div class="metric-value kpi-big">{be_value}</div>
            <div class="metric-change {be_cls}">{be_change}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">CRB 大宗商品 (DBC)</div>
            <div class="metric-value kpi-big">{crb_value}</div>
            <div class="metric-change {crb_cls}">{crb_change}</div>
        </div>
    </div>
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">CPI ({cpi_date})</div>
            <div class="metric-value kpi-big">{cpi_value}</div>
            <div class="metric-change">环比 {cpi_mom} | 同比 {cpi_yoy}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">核心 PCE ({pce_date})</div>
            <div class="metric-value kpi-big">{pce_value}</div>
            <div class="metric-change">环比 {pce_mom} | 同比 {pce_yoy}</div>
        </div>
    </div>
</div>
""".format(
        gold_futures_price=_fmt_price(gold_futures.get("price")),
        gold_futures_cls=_change_class(gold_futures.get("change_pct")),
        gold_futures_change=_fmt_pct(gold_futures.get("change_pct")),
        gold_etf_price=_fmt_price(gold_etf.get("price")),
        gold_etf_cls=_change_class(gold_etf.get("change_pct")),
        gold_etf_change=_fmt_pct(gold_etf.get("change_pct")),
        be_value=f"{breakeven['value']:.2f}%" if breakeven and breakeven.get("value") else "N/A",
        be_cls=_change_class(breakeven.get("change") if breakeven else None),
        be_change=_fmt_pct(breakeven.get("change"), 3) if breakeven else "N/A",
        crb_value=_fmt_price(crb.get("price")) if crb else "N/A",
        crb_cls=_change_class(crb.get("change_pct") if crb else None),
        crb_change=_fmt_pct(crb.get("change_pct")) if crb else "N/A",
        cpi_date=cpi.get("date", "") if cpi else "N/A",
        cpi_value=_fmt_num(cpi.get("value") if cpi else None, ",.1f"),
        cpi_mom=_fmt_pct(cpi.get("mom_pct"), 3) if cpi else "N/A",
        cpi_yoy=_fmt_pct(cpi.get("yoy_pct"), 1) if cpi else "N/A",
        pce_date=core_pce.get("date", "") if core_pce else "N/A",
        pce_value=_fmt_num(core_pce.get("value") if core_pce else None, ",.1f"),
        pce_mom=_fmt_pct(core_pce.get("mom_pct"), 3) if core_pce else "N/A",
        pce_yoy=_fmt_pct(core_pce.get("yoy_pct"), 1) if core_pce else "N/A",
    ))

    # --- 第二部分: 科技股行情 ---
    parts.append("""
<div class="section">
    <div class="section-title">II. 纳斯达克100 & 科技七巨头 (Mag 7)</div>

    <!-- QQQ -->
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">QQQ (纳指100 ETF)</div>
            <div class="metric-value kpi-big">{qqq_price}</div>
            <div class="metric-change {qqq_cls}">{qqq_change}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">VXN 科技波动率</div>
            <div class="metric-value kpi-big">{vxn_value}</div>
            <div class="metric-change {vxn_cls}">{vxn_change} <small>(涨=恐慌↑ 跌=恐慌↓)</small></div>
        </div>
        <div class="metric-card">
            <div class="metric-label">恐慌贪婪指数</div>
            <div class="metric-value kpi-big">{fg_score}</div>
            <div class="metric-change">{fg_rating}</div>
        </div>
    </div>
""".format(
        qqq_price=_fmt_price(qqq.get("price")) if qqq else "N/A",
        qqq_cls=_change_class(qqq.get("change_pct") if qqq else None),
        qqq_change=_fmt_pct(qqq.get("change_pct")) if qqq else "N/A",
        vxn_value=f"{vxn['value']:.1f}" if vxn and vxn.get("value") else "N/A",
        vxn_cls=_change_class(vxn.get("change_pct") if vxn else None, reverse=True),
        vxn_change=_fmt_pct(vxn.get("change_pct")) if vxn else "N/A",
        fg_score=f"{fg['score']}" if fg and fg.get("score") is not None else "N/A",
        fg_rating=fg.get("rating", "N/A") if fg else "N/A",
    ))

    # Mag7 表格
    parts.append("""
    <table class="data-table" style="margin-top:16px;">
        <thead>
            <tr><th>股票</th><th>代码</th><th>最新价</th><th>涨跌幅</th><th>成交量</th></tr>
        </thead>
        <tbody>
""")
    for m in mag7:
        vol_str = f"{m.get('volume', 0):,.0f}" if m.get("volume") else "N/A"
        parts.append(f"""
            <tr>
                <td><strong>{m.get('name', '')}</strong></td>
                <td>{m.get('ticker', '')}</td>
                <td>{_fmt_price(m.get('price'))}</td>
                <td>{_fmt_pct(m.get('change_pct'))}</td>
                <td>{vol_str}</td>
            </tr>
""")
    parts.append("</tbody></table></div>")

    # --- 第三部分: 情绪研判 ---
    parts.append(f"""
<div class="section">
    <div class="section-title">III. 科技股情绪研判</div>
    <div style="text-align:center; padding: 16px 0;">
        <span class="sentiment-badge {s_cls}" style="font-size:16px; padding:10px 24px;">{s_label}</span>
    </div>
    <p style="text-align:center; color:#666; font-size:13px; margin-top:8px;">{sentiment}</p>
</div>
""")

    # --- 第四部分: 美联储 ---
    parts.append("""
<div class="section">
    <div class="section-title">IV. CME FedWatch 下次会议利率概率</div>
""")

    if fedwatch:
        fw = fedwatch
        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">会议日期</div>
            <div class="metric-value" style="font-size:16px;">{fw.get('meeting_date', 'N/A')}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">当前基准利率</div>
            <div class="metric-value" style="font-size:16px;">{fw.get('current_rate', 'N/A')}</div>
        </div>
    </div>
""")

        # 概率条
        cut_p = fw.get("cut_prob", 0)
        hold_p = fw.get("hold_prob", 0)
        hike_p = fw.get("hike_prob", 0)

        parts.append(f"""
    <p style="font-weight:700; margin-bottom:8px;">下次会议利率变动概率分布:</p>
    <div class="prob-bar-container">
        <span class="prob-bar prob-cut" style="width:{cut_p:.1f}%;"></span>
        <span class="prob-bar prob-hold" style="width:{hold_p:.1f}%;"></span>
        <span class="prob-bar prob-hike" style="width:{hike_p:.1f}%;"></span>
    </div>
    <div style="display:flex; justify-content:space-between; font-size:12px; color:#666; margin-top:4px;">
        <span style="color:#43A047;">降息 {cut_p:.1f}%</span>
        <span style="color:#78909C;">不变 {hold_p:.1f}%</span>
        <span style="color:#E53935;">加息 {hike_p:.1f}%</span>
    </div>
""")

        # 降息明细
        cut_details = fw.get("cut_details", [])
        if cut_details:
            parts.append('<p style="font-weight:700; margin-top:12px;">降息情景明细:</p><ul style="font-size:13px; color:#444;">')
            for d in cut_details:
                parts.append(f'<li>{d.get("rate_range", "")}: <strong>{d.get("probability", 0):.1f}%</strong></li>')
            parts.append("</ul>")

        # 最大概率
        mx = fw.get("max_prob_scenario")
        if mx:
            parts.append(f"""
    <p style="font-size:13px; color:#666; margin-top:8px;">
        最大概率情景: <strong>{mx.get('rate_range', '')}</strong> ({mx.get('probability', 0):.1f}%)
    </p>
""")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')

    parts.append("</div>")

    # --- 第五部分: 美元信用涨跌评估 ---
    treasury = data.get("treasury")
    dxy = data.get("dxy")
    fed_bs = data.get("fed_bs")
    tips = data.get("tips")
    dollar_credit = data.get("dollar_credit", "")

    parts.append("""
<div class="section">
    <div class="section-title">V. 美元信用涨跌评估</div>
""")

    # 信用研判结论
    dc_label = "待评估"
    dc_cls = "sentiment-neutral"
    if dollar_credit:
        if "强势走稳" in dollar_credit or "AAA" in dollar_credit:
            dc_label = "AAA · 信用强势走稳"
            dc_cls = "sentiment-greed"
        elif "偏强运行" in dollar_credit or "信用评级: AA" in dollar_credit:
            dc_label = "AA · 信用偏强运行"
            dc_cls = "sentiment-greed"
        elif "中性持平" in dollar_credit or "信用评级: A" in dollar_credit:
            dc_label = "A · 信用中性持平"
            dc_cls = "sentiment-neutral"
        elif "边际承压" in dollar_credit or "BBB" in dollar_credit:
            dc_label = "BBB · 信用边际承压"
            dc_cls = "sentiment-fear"
        elif "信用走弱" in dollar_credit or "信用评级: BB" in dollar_credit:
            dc_label = "BB · 信用走弱"
            dc_cls = "sentiment-fear"
        elif "显著恶化" in dollar_credit or "信用评级: B" in dollar_credit:
            dc_label = "B · 信用显著恶化"
            dc_cls = "sentiment-panic"

    parts.append(f"""
    <div style="text-align:center; padding: 12px 0;">
        <span class="sentiment-badge {dc_cls}" style="font-size:15px; padding:8px 20px;">{dc_label}</span>
    </div>
    <p style="text-align:center; color:#666; font-size:12px; margin-top:6px;">{dollar_credit}</p>
""")

    # 美债收益率卡片
    y2 = treasury.get("yield_2y") if treasury else None
    y10 = treasury.get("yield_10y") if treasury else None
    y30 = treasury.get("yield_30y") if treasury else None
    spread_2_10 = treasury.get("spread_2y_10y") if treasury else None

    parts.append('<div class="metric-row" style="margin-top:16px;">')

    if y2:
        parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">2Y 国债收益率</div>
            <div class="metric-value" style="font-size:18px;">{_fmt_num(y2.get('value'), ".3f", suffix="%")}</div>
            <div class="metric-change {_change_class(y2.get('change'))}">{_fmt_pct(y2.get('change'), 3)}</div>
        </div>
""")

    if y10:
        parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">10Y 国债收益率</div>
            <div class="metric-value" style="font-size:18px;">{_fmt_num(y10.get('value'), ".3f", suffix="%")}</div>
            <div class="metric-change {_change_class(y10.get('change'))}">{_fmt_pct(y10.get('change'), 3)}</div>
        </div>
""")

    if y30:
        parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">30Y 国债收益率</div>
            <div class="metric-value" style="font-size:18px;">{_fmt_num(y30.get('value'), ".3f", suffix="%")}</div>
            <div class="metric-change {_change_class(y30.get('change'))}">{_fmt_pct(y30.get('change'), 3)}</div>
        </div>
""")

    parts.append("</div>")

    # 利差 + DXY + 实际利率
    parts.append('<div class="metric-row">')

    if spread_2_10 is not None:
        parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">2Y-10Y 期限利差</div>
            <div class="metric-value" style="font-size:18px; color:{'#E53935' if spread_2_10 >= 0 else '#43A047'};">{spread_2_10:+.3f}%</div>
            <div class="metric-change">{'倒挂' if spread_2_10 < 0 else '正常'}</div>
        </div>
""")

    if dxy:
        dxy_val = dxy.get("value")
        dxy_pct = dxy.get("change_pct")
        dxy_val_str = f"{dxy_val:.2f}" if dxy_val is not None else "N/A"
        parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">美元指数 (DXY)</div>
            <div class="metric-value" style="font-size:18px;">{dxy_val_str}</div>
            <div class="metric-change {_change_class(dxy_pct)}">{_fmt_pct(dxy_pct)}</div>
        </div>
""")

    if tips and tips.get("value") is not None:
        real_rate = tips["value"]
        parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">10Y 实际利率 (TIPS)</div>
            <div class="metric-value" style="font-size:18px; color:{'#E53935' if real_rate > 0 else '#43A047'};">{real_rate:.3f}%</div>
            <div class="metric-change">{_fmt_pct(tips.get('change'), 3)}</div>
        </div>
""")

    parts.append("</div>")

    # 美联储资产负债表
    if fed_bs and fed_bs.get("total_bn") is not None:
        total_bn = fed_bs["total_bn"]
        wc_bn = fed_bs.get("weekly_change_bn", 0)
        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card" style="min-width:100%;">
            <div class="metric-label">美联储资产负债表规模 ({fed_bs.get('date', 'N/A')})</div>
            <div class="metric-value" style="font-size:18px;">${total_bn:,.0f}B</div>
            <div class="metric-change {_change_class(wc_bn)}">周变化: {wc_bn:+.1f}B</div>
        </div>
    </div>
""")

    parts.append("</div>")

    # --- 第六部分: 美元指数独立分析 ---
    dxy_analysis = data.get("dxy_analysis")

    parts.append("""
<div class="section">
    <div class="section-title">VI. 美元指数独立分析</div>
""")
    if dxy_analysis:
        dxy_val = dxy_analysis.get("value")
        dxy_pct = dxy_analysis.get("change_pct")
        dxy_trend = dxy_analysis.get("trend_direction", "")
        dxy_trend_pct = dxy_analysis.get("trend_5d_pct")
        dxy_interp = dxy_analysis.get("interpretation", "")
        dxy_val_str = f"{dxy_val:.2f}" if dxy_val is not None else "N/A"
        # 趋势箭头
        trend_arrow = "→"
        if dxy_trend_pct is not None:
            if dxy_trend_pct > 0.5:
                trend_arrow = "↑"
            elif dxy_trend_pct < -0.5:
                trend_arrow = "↓"
        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">最新 DXY 指数</div>
            <div class="metric-value kpi-big">{dxy_val_str}</div>
            <div class="metric-change {_change_class(dxy_pct)}">{_fmt_pct(dxy_pct)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">5 日趋势</div>
            <div class="metric-value kpi-big">{trend_arrow}</div>
            <div class="metric-change">{dxy_trend} ({_fmt_pct(dxy_trend_pct)})</div>
        </div>
    </div>
    <p style="text-align:center; color:#666; font-size:13px; margin-top:8px;">{dxy_interp}</p>
""")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')
    parts.append("</div>")

    # --- 第七部分: 金银比 (Gold/Silver Ratio) ---
    gsr = data.get("gold_silver_ratio")

    parts.append("""
<div class="section">
    <div class="section-title">VII. 金银比 (Gold/Silver Ratio)</div>
""")
    if gsr and gsr.get("ratio"):
        ratio = gsr["ratio"]
        gold_p = gsr.get("gold_price")
        silver_p = gsr.get("silver_price")
        avg20 = gsr.get("historical_avg_20yr", 60)
        avg50 = gsr.get("historical_avg_50yr", 55)
        interp = gsr.get("interpretation", "")

        # 基于比值的颜色: 显著偏离均值时高亮
        deviation = (ratio - avg20) / avg20 * 100
        ratio_cls = "up" if deviation > 5 else ("down" if deviation < -5 else "neutral")

        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card" style="min-width:100%;">
            <div class="metric-label">金银比</div>
            <div class="metric-value kpi-big" style="color:{'#E53935' if ratio > avg20 else '#43A047'};">{ratio:.1f}</div>
            <div class="metric-change {ratio_cls}">金价 {_fmt_num(gold_p, ",.0f", prefix="$")} | 银价 {_fmt_num(silver_p, ",.2f", prefix="$")}</div>
        </div>
    </div>
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">20 年均值</div>
            <div class="metric-value" style="font-size:18px;">{avg20}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">50 年均值</div>
            <div class="metric-value" style="font-size:18px;">{avg50}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">偏离 20 年均值</div>
            <div class="metric-value {ratio_cls}" style="font-size:18px;">{deviation:+.1f}%</div>
        </div>
    </div>
    <p style="text-align:center; color:#666; font-size:13px; margin-top:8px;">{interp}</p>
""")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')
    parts.append("</div>")

    # --- 第八部分: COMEX COT 报告解读 ---
    cot = data.get("cot")

    parts.append("""
<div class="section">
    <div class="section-title">VIII. COMEX 黄金/白银期货非商业持仓 (COT 报告)</div>
""")
    if cot:
        gold_cot = cot.get("gold", {})
        silver_cot = cot.get("silver", {})

        def _cot_sent_cls(s: str) -> str:
            if "极度看多" in s:
                return "sentiment-extreme-greed"
            if "看多" in s:
                return "sentiment-greed"
            if "偏空" in s:
                return "sentiment-fear"
            if "看空" in s:
                return "sentiment-panic"
            return "sentiment-neutral"

        # 黄金 COT
        if gold_cot:
            gold_net = gold_cot.get("net_position")
            gold_sentiment = gold_cot.get("sentiment", "中性")
            gold_oi = gold_cot.get("open_interest")
            gold_long = gold_cot.get("noncomm_long")
            gold_short = gold_cot.get("noncomm_short")
            gold_sent_cls = _cot_sent_cls(gold_sentiment)
            gold_sent_label = gold_sentiment

            parts.append(f"""
    <p style="font-weight:700; margin-bottom:8px;">黄金 (COMEX, Code-088691)</p>
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">非商业净多仓</div>
            <div class="metric-value kpi-big">{_fmt_num(gold_net, ",")}</div>
            <div class="metric-change">多头: {_fmt_num(gold_long, ",")} | 空头: {_fmt_num(gold_short, ",")}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">未平仓合约 (OI)</div>
            <div class="metric-value kpi-big">{_fmt_num(gold_oi, ",")}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">持仓情绪</div>
            <div style="margin-top:8px;"><span class="sentiment-badge {gold_sent_cls}">{gold_sent_label}</span></div>
        </div>
    </div>
""")
        else:
            parts.append('<p style="color:#888;">黄金 COT 数据暂不可用</p>')

        # 白银 COT
        if silver_cot:
            silver_net = silver_cot.get("net_position")
            silver_sentiment = silver_cot.get("sentiment", "中性")
            silver_oi = silver_cot.get("open_interest")
            silver_long = silver_cot.get("noncomm_long")
            silver_short = silver_cot.get("noncomm_short")
            silver_sent_cls = _cot_sent_cls(silver_sentiment)
            silver_sent_label = silver_sentiment

            parts.append(f"""
    <p style="font-weight:700; margin-top:16px; margin-bottom:8px;">白银 (COMEX, Code-084691)</p>
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">非商业净多仓</div>
            <div class="metric-value kpi-big">{_fmt_num(silver_net, ",")}</div>
            <div class="metric-change">多头: {_fmt_num(silver_long, ",")} | 空头: {_fmt_num(silver_short, ",")}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">未平仓合约 (OI)</div>
            <div class="metric-value kpi-big">{_fmt_num(silver_oi, ",")}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">持仓情绪</div>
            <div style="margin-top:8px;"><span class="sentiment-badge {silver_sent_cls}">{silver_sent_label}</span></div>
        </div>
    </div>
""")
        else:
            parts.append('<p style="color:#888;">白银 COT 数据暂不可用</p>')
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')
    parts.append("</div>")

    # --- 第九部分: SPDR 黄金 ETF 持仓 ---
    spdr = data.get("spdr")

    parts.append("""
<div class="section">
    <div class="section-title">IX. 全球最大黄金 ETF (SPDR) 持仓变化</div>
""")
    if spdr:
        holdings = spdr.get("holdings_tonnes")
        change = spdr.get("change_tonnes")
        nav = spdr.get("nav")
        source = spdr.get("source", "未知")

        change_str = f"{change:+.2f} 吨" if change is not None else "N/A"
        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">SPDR 黄金持仓量</div>
            <div class="metric-value kpi-big">{_fmt_num(holdings, ",.2f")}<span style="font-size:14px;"> 吨</span></div>
            <div class="metric-change {_change_class(change) if change is not None else 'neutral'}">{change_str}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">总资产净值 (NAV)</div>
            <div class="metric-value kpi-big">{_fmt_num(nav, ",.1f", prefix="$", suffix="B")}</div>
            <div class="metric-change">数据来源: {source}</div>
        </div>
    </div>
    <p style="text-align:center; color:#666; font-size:12px; margin-top:8px;">
        SPDR 持仓变化反映全球最大黄金 ETF 的资金流向, 是衡量黄金投资需求的重要指标。
    </p>
""")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')
    parts.append("</div>")

    # --- 第十部分: 贵金属/原油波动率指标 ---
    volatility = data.get("volatility")

    parts.append("""
<div class="section">
    <div class="section-title">X. 贵金属 & 原油波动率指标 (GVZ / VXSLV / OVX / 铜波动率)</div>
""")
    if volatility:
        gvz = volatility.get("gvz")
        vxslv = volatility.get("vxslv")
        ovx = volatility.get("ovx")
        copper_vol = volatility.get("copper_vol")
        vol_interp = volatility.get("interpretation", "")

        parts.append("""
    <div class="metric-row">
""")
        for item in (
            ("GVZ 黄金波动率", gvz, "涨=风险放大 跌=趋于平稳"),
            ("VXSLV 白银波动率", vxslv, "涨=风险放大 跌=趋于平稳"),
            ("OVX 原油波动率", ovx, "涨=能源动荡 跌=平稳"),
        ):
            label, obj, hint = item
            if not obj:
                continue
            v = obj.get("value")
            chg = obj.get("change_pct")
            parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value kpi-big">{_fmt_num(v, ".2f")}</div>
            <div class="metric-change {_change_class(chg, reverse=True)}">{_fmt_pct(chg)} <small>({hint})</small></div>
        </div>
""")
        if copper_vol and copper_vol.get("value") is not None:
            parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">LME 铜波动率 (近似)</div>
            <div class="metric-value kpi-big">{_fmt_num(copper_vol.get("value"), ".2f")}%</div>
            <div class="metric-change">21日年化已实现波动率 (COMEX HG=F)</div>
        </div>
""")
        parts.append("""
    </div>
""")
        if vol_interp:
            parts.append(f"""
    <p style="text-align:center; color:#666; font-size:12px; margin-top:8px;">{vol_interp}</p>
""")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')
    parts.append("</div>")

    # --- 第十一部分: 金银相关国际要闻 ---
    news = data.get("news")

    parts.append("""
<div class="section">
    <div class="section-title">XI. 近期影响金银价格的国际大事要闻</div>
""")
    if news and news.get("items"):
        parts.append("""
    <table class="data-table">
        <thead>
            <tr><th style="width:70%;">标题</th><th>来源</th><th>时间</th></tr>
        </thead>
        <tbody>
""")
        for it in news["items"]:
            title = it.get("title", "")
            link = it.get("link", "")
            source = it.get("source", "")
            published = it.get("published", "")
            title_html = f'<a href="{link}" style="color:#1a5276; text-decoration:none;">{title}</a>' if link else title
            parts.append(f"""
            <tr>
                <td>{title_html}</td>
                <td>{source}</td>
                <td style="font-size:12px; color:#666;">{published}</td>
            </tr>
""")
        parts.append("""
        </tbody>
    </table>
    <p style="text-align:center; color:#666; font-size:12px; margin-top:8px;">
        数据来源: Google News RSS (近7天, 央行购金/美联储政策/关税/避险等金银相关事件)
    </p>
""")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')
    parts.append("</div>")

    # --- 页脚 ---
    parts.append(f"""
<div class="footer">
    <p>本报告由 Gold-Tech-Fed-Dashboard 自动生成 | 数据抓取时间: {fetch_time}</p>
    <p>免责声明: 本报告仅供信息参考, 不构成投资建议。数据来源于 Yahoo Finance、FRED、CME、CNN 等公开渠道。</p>
    <p style="margin-top:8px; color:#bbb;">Powered by WorkBuddy AI · Python yfinance + fredapi</p>
</div>

</div>
</body>
</html>
""")

    return "\n".join(parts)


# ============================================================
# 月度宏观报告 HTML
# ============================================================

def render_monthly_html(data: dict) -> str:
    """渲染月度/季度宏观底牌报告 HTML 邮件。"""
    today = datetime.now().strftime("%Y-%m-%d")
    aisc = data.get("aisc")
    wgc = data.get("wgc_cb")
    cpi_pce = data.get("cpi_pce", {})
    fomc = data.get("fomc")
    gold = data.get("gold", {})
    fedwatch = data.get("fedwatch")
    fetch_time = data.get("fetch_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    gold_futures = (gold.get("GC=F", {}) if gold else {}) or {}

    parts = []

    # --- 头部 ---
    parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body>
{BASE_STYLE}
<div class="container">

<div class="header" style="background: linear-gradient(135deg, #1a1a2e 0%, #2d1b4e 50%, #4a0e4e 100%);">
    <h1>全球央行购金、黄金硬核开采成本与美联储最新货币政策月度报告</h1>
    <div class="subtitle">Central Bank Gold · Mining AISC · Inflation · FOMC Policy | Monthly Macro Report</div>
    <div class="date-badge">{today}</div>
</div>
""")

    # --- 第一部分: 央行购金 ---
    parts.append("""
<div class="section">
    <div class="section-title">I. 全球央行购金动态</div>
""")
    if wgc and wgc.get("global_central_bank_net_purchases"):
        g = wgc["global_central_bank_net_purchases"]
        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">最新季度 {g.get('quarter', '')}</div>
            <div class="metric-value kpi-big">{g.get('value', 'N/A')}<span style="font-size:14px;"> 吨</span></div>
            <div class="metric-change {_change_class(0)}">全球央行净买入量</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">同比增长</div>
            <div class="metric-value kpi-big">{_fmt_pct(g.get('yoy_change_pct', 0))}</div>
            <div class="metric-change">较去年同期</div>
        </div>
    </div>
""")

        # Top 买家表
        top_buyers = wgc.get("top_buyers", [])
        if top_buyers:
            parts.append("""
    <p style="font-weight:700; margin-top:12px;">前三大买方:</p>
    <table class="data-table">
        <thead><tr><th>排名</th><th>国家</th><th>净买入量 (吨)</th><th>黄金储备总量 (吨)</th></tr></thead>
        <tbody>
""")
            for b in top_buyers:
                parts.append(f"""
            <tr>
                <td>{b.get('rank', '')}</td>
                <td><strong>{b.get('country', '')}</strong></td>
                <td>{b.get('purchases_tonnes', 'N/A')}</td>
                <td>{b.get('total_reserves_tonnes', 'N/A'):,}</td>
            </tr>
""")
            parts.append("</tbody></table>")

        # 趋势背景
        context = wgc.get("context", "")
        if context:
            parts.append(f'<p style="font-size:13px; color:#666; margin-top:12px; line-height:1.6;">{context}</p>')

        # 历史趋势
        hist = wgc.get("historical_trend", [])
        if hist:
            parts.append("""
    <p style="font-weight:700; margin-top:12px;">年度央行购金趋势:</p>
    <table class="data-table">
        <thead><tr><th>年份</th><th>全球净买入 (吨)</th></tr></thead>
        <tbody>
""")
            for h in hist:
                parts.append(f"<tr><td>{h.get('year', '')}</td><td>{h.get('total_tonnes', 'N/A'):,}</td></tr>")
            parts.append("</tbody></table>")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')

    parts.append("</div>")

    # --- 第二部分: AISC ---
    parts.append("""
<div class="section">
    <div class="section-title">II. 全球黄金硬核开采成本 (AISC)</div>
""")
    if aisc and aisc.get("global_avg_aisc"):
        agg = aisc["global_avg_aisc"]
        aisc_val = agg.get("value")
        gold_price = gold_futures.get("price")

        # 矿企利润垫
        margin = None
        margin_pct = None
        if aisc_val and gold_price:
            margin = gold_price - aisc_val
            margin_pct = margin / gold_price * 100

        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">全球平均 AISC ({agg.get('quarter', '')})</div>
            <div class="metric-value kpi-big">${aisc_val:,}/oz</div>
            <div class="metric-change">同比: {_fmt_pct(agg.get('yoy_change_pct', 0))}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">当前金价</div>
            <div class="metric-value kpi-big">{_fmt_price(gold_price)}</div>
            <div class="metric-change">GC=F 期货</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">矿企利润垫空间</div>
            <div class="metric-value kpi-big" style="color:{'#E53935' if margin and margin > 0 else '#43A047'};">${margin:,.0f}/oz</div>
            <div class="metric-change">利润率 {margin_pct:.1f}%</div>
        </div>
    </div>
    <p style="font-size:13px; color:#666; margin-top:12px;">
        当前金价约为全球平均 AISC 的 <strong>{gold_price/aisc_val:.1f}x</strong>。
        矿企享有约 <strong>${margin:,.0f}/oz</strong> 的利润垫空间,
        为近三年最高水平, 金矿企业盈利能力强劲。即使金价回调 {margin_pct:.0f}% 至 ${aisc_val:,}/oz,
        全行业仍可维持盈亏平衡。
    </p>
""")

        top_producers = aisc.get("top_producers_margin", [])
        if top_producers:
            parts.append("""
    <p style="font-weight:700; margin-top:12px;">头部矿企 AISC 对比:</p>
    <table class="data-table">
        <thead><tr><th>矿企</th><th>代码</th><th>AISC ($/oz)</th><th>利润垫 ($/oz)</th></tr></thead>
        <tbody>
""")
            for p in top_producers:
                p_margin = (gold_price - p.get("aisc", 0)) if gold_price else None
                parts.append(f"""
            <tr>
                <td><strong>{p.get('producer', '')}</strong></td>
                <td>{p.get('ticker', '')}</td>
                <td>${p.get('aisc', 'N/A'):,}</td>
                <td style="color:#E53935;">${p_margin:,.0f}</td>
            </tr>
""")
            parts.append("</tbody></table>")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')

    parts.append("</div>")

    # --- 第三部分: CPI/PCE ---
    parts.append("""
<div class="section">
    <div class="section-title">III. 美国最新通胀数据</div>
""")
    cpi = cpi_pce.get("cpi")
    pce = cpi_pce.get("core_pce")

    if cpi or pce:
        parts.append('<div class="metric-row">')
        if cpi:
            parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">CPI ({cpi.get('date', '')})</div>
            <div class="metric-value kpi-big">{cpi.get('value', 'N/A'):,.1f}</div>
            <div class="metric-change">环比 {_fmt_pct(cpi.get('mom_pct'), 3)} | 同比 {_fmt_pct(cpi.get('yoy_pct'), 1)}</div>
        </div>
""")
        if pce:
            parts.append(f"""
        <div class="metric-card">
            <div class="metric-label">核心 PCE ({pce.get('date', '')})</div>
            <div class="metric-value kpi-big">{pce.get('value', 'N/A'):,.1f}</div>
            <div class="metric-change">环比 {_fmt_pct(pce.get('mom_pct'), 3)} | 同比 {_fmt_pct(pce.get('yoy_pct'), 1)}</div>
        </div>
""")
        parts.append("</div>")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中 (需配置 FRED_API_KEY)</p>')

    parts.append("</div>")

    # --- 第四部分: FOMC ---
    parts.append("""
<div class="section">
    <div class="section-title">IV. 美联储最新货币政策 & FOMC</div>
""")
    if fomc:
        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">当前基准利率区间</div>
            <div class="metric-value" style="font-size:18px;">{fomc.get('rate_range', 'N/A')}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">有效联邦基金利率</div>
            <div class="metric-value" style="font-size:18px;">{fomc.get('effective_rate') or 'N/A'}{'%' if fomc.get('effective_rate') else ''}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">最近决议日期</div>
            <div class="metric-value" style="font-size:16px;">{fomc.get('last_decision_date', 'N/A')}</div>
        </div>
    </div>
    <div style="background:#f8f9fc; border-radius:8px; padding:16px; margin-top:12px;">
        <p style="font-weight:700; margin:0 0 8px 0;">最新政策声明要点:</p>
        <p style="font-size:13px; color:#444; line-height:1.6; margin:0;">{fomc.get('decision_summary', 'N/A')}</p>
    </div>
    <div class="metric-row" style="margin-top:12px;">
        <div class="metric-card">
            <div class="metric-label">点阵图中值 (2026)</div>
            <div class="metric-value">{fomc.get('dot_plot_median_2026', 'N/A')}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">点阵图中值 (2027)</div>
            <div class="metric-value">{fomc.get('dot_plot_median_2027', 'N/A')}</div>
        </div>
    </div>
""")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')

    parts.append("</div>")

    # --- 第五部分: FedWatch 概率 ---
    parts.append("""
<div class="section">
    <div class="section-title">V. CME FedWatch 最新利率概率</div>
""")
    if fedwatch:
        fw = fedwatch
        cut_p = fw.get("cut_prob", 0)
        hold_p = fw.get("hold_prob", 0)
        hike_p = fw.get("hike_prob", 0)
        parts.append(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="metric-label">下次会议</div>
            <div class="metric-value" style="font-size:16px;">{fw.get('meeting_date', 'N/A')}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">当前利率</div>
            <div class="metric-value" style="font-size:16px;">{fw.get('current_rate', 'N/A')}</div>
        </div>
    </div>
    <div class="prob-bar-container" style="margin-top:8px;">
        <span class="prob-bar prob-cut" style="width:{cut_p:.1f}%;"></span>
        <span class="prob-bar prob-hold" style="width:{hold_p:.1f}%;"></span>
        <span class="prob-bar prob-hike" style="width:{hike_p:.1f}%;"></span>
    </div>
    <div style="display:flex; justify-content:space-between; font-size:12px; color:#666; margin-top:4px;">
        <span style="color:#43A047;">降息 {cut_p:.1f}%</span>
        <span style="color:#78909C;">不变 {hold_p:.1f}%</span>
        <span style="color:#E53935;">加息 {hike_p:.1f}%</span>
    </div>
""")
    else:
        parts.append('<p style="color:#888;">该项数据源正在维护中</p>')

    parts.append("</div>")

    # --- 页脚 ---
    parts.append(f"""
<div class="footer">
    <p>本报告由 Gold-Tech-Fed-Dashboard 自动生成 | 数据抓取时间: {fetch_time}</p>
    <p>免责声明: 本报告仅供信息参考, 不构成投资建议。央行购金及 AISC 数据来源 WGC/S&P Global, 通胀数据来源 FRED, 利率概率来源 CME。</p>
    <p style="margin-top:8px; color:#bbb;">Powered by WorkBuddy AI · Python yfinance + fredapi + CME FedWatch</p>
</div>

</div>
</body>
</html>
""")

    return "\n".join(parts)
