#!/usr/bin/env python3
"""
测试脚本: 验证5个新模块的数据抓取功能
- 美元指数独立分析 (DXY)
- 金银比 (Gold/Silver Ratio)
- COMEX COT 报告解读
- SPDR 黄金 ETF 持仓变化
- CPI/PCE 通胀数据 (每日看板集成)
"""

import logging
import sys
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.data_fetchers import (
    fetch_silver_price,
    fetch_gold_silver_ratio,
    fetch_dxy_analysis,
    fetch_cot_data,
    fetch_spdr_holdings,
    fetch_cpi_pce_data,
    fetch_daily_bundle,
)

FAILED = 0
PASSED = 0

def test(name, result, required_keys=None):
    global PASSED, FAILED
    if result is None:
        print(f"  ❌ {name}: 返回 None (数据源不可用)")
        FAILED += 1
        return
    if required_keys:
        missing = [k for k in required_keys if k not in result]
        if missing:
            print(f"  ❌ {name}: 缺少字段 {missing}")
            FAILED += 1
            return
    print(f"  ✅ {name}: 数据获取成功")
    PASSED += 1
    # 打印关键字段
    for k in (required_keys or result.keys()):
        v = result.get(k)
        if v is not None:
            print(f"     {k}: {v}")
    return result


if __name__ == "__main__":
    print("=" * 60)
    print("测试: 5个新模块 + 每日完整 Bundle")
    print("=" * 60)

    # 1. 白银价格
    print("\n1️⃣  白银价格 (fetch_silver_price)")
    silver = test("白银期货", fetch_silver_price(), ["price"])

    # 2. 金银比
    print("\n2️⃣  金银比 (fetch_gold_silver_ratio)")
    gsr = test("金银比", fetch_gold_silver_ratio(), ["ratio", "gold_price", "silver_price"])

    # 3. 美元指数独立分析
    print("\n3️⃣  美元指数独立分析 (fetch_dxy_analysis)")
    dxy = test("DXY分析", fetch_dxy_analysis(), ["value", "interpretation"])

    # 4. COT 报告
    print("\n4️⃣  COMEX COT 报告 (fetch_cot_data)")
    cot = test("COT报告", fetch_cot_data(), ["gold", "silver"])
    if cot:
        gold_cot = cot.get("gold", {})
        if gold_cot:
            print(f"    黄金净多仓: {gold_cot.get('net_position')}, 情绪: {gold_cot.get('sentiment')}")
        silver_cot = cot.get("silver", {})
        if silver_cot:
            print(f"    白银净多仓: {silver_cot.get('net_position')}, 情绪: {silver_cot.get('sentiment')}")

    # 5. SPDR 持仓
    print("\n5️⃣  SPDR 黄金 ETF 持仓 (fetch_spdr_holdings)")
    spdr = test("SPDR持仓", fetch_spdr_holdings(), ["holdings_tonnes"])
    if spdr:
        print(f"    数据来源: {spdr.get('source')}")

    # 6. CPI/PCE
    print("\n6️⃣  CPI/PCE 通胀数据 (fetch_cpi_pce_data)")
    cpi_pce = test("CPI/PCE", fetch_cpi_pce_data(), ["cpi", "core_pce"])
    if cpi_pce:
        cpi = cpi_pce.get("cpi", {})
        pce = cpi_pce.get("core_pce", {})
        if cpi:
            print(f"    CPI: {cpi.get('value')} ({cpi.get('date')}), 同比: {cpi.get('yoy_pct')}%")
        if pce:
            print(f"    核心PCE: {pce.get('value')} ({pce.get('date')}), 同比: {pce.get('yoy_pct')}%")

    # 7. 完整每日 Bundle
    print("\n7️⃣  完整每日 Bundle (fetch_daily_bundle)")
    bundle = fetch_daily_bundle()
    if bundle:
        print(f"  ✅ 每日 Bundle 生成成功: {len(bundle)} 个键值")
        new_keys = ["silver", "gold_silver_ratio", "dxy_analysis", "cot", "spdr", "cpi_pce"]
        missing_new = [k for k in new_keys if k not in bundle]
        if missing_new:
            print(f"  ⚠️  Bundle 缺少新字段: {missing_new}")
        else:
            print(f"  ✅ 所有新字段均在 Bundle 中: {new_keys}")
        PASSED += 1
    else:
        print(f"  ❌ Bundle 生成失败")
        FAILED += 1

    # 汇总
    print("\n" + "=" * 60)
    print(f"测试结果: ✅ {PASSED} 通过, ❌ {FAILED} 失败")
    print("=" * 60)

    if FAILED > 0:
        sys.exit(1)
    print("所有测试通过!")