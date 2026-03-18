#!/usr/bin/env python3
"""
收集今日 (2026-03-18) Google Trends Rising 关键词
时间范围: now 1-d（过去24小时）
过滤条件: Rising > 500% 或 Breakout
"""
import json
import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keyword_loader import load_root_keywords
from querytrends import get_related_queries

DATA_DIR = "data_20260318"
TIMEFRAME = "now 1-d"
RISING_THRESHOLD = 500

os.makedirs(DATA_DIR, exist_ok=True)


def sanitize(keyword):
    return keyword.replace(" ", "_").replace("/", "_")


def already_collected(keyword):
    fname = os.path.join(DATA_DIR, f"related_queries_{sanitize(keyword)}.json")
    return os.path.exists(fname)


def parse_rising_value(value_str):
    if value_str is None:
        return 0
    s = str(value_str).strip().replace(",", "").replace("+", "").replace("%", "")
    if s.lower() == "breakout":
        return 9999
    try:
        return float(s)
    except:
        return 0


def save_result(keyword, rising_filtered, all_rising_count, all_top):
    fname = os.path.join(DATA_DIR, f"related_queries_{sanitize(keyword)}.json")
    data = {
        "keyword": keyword,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timeframe": TIMEFRAME,
        "geo": "Worldwide",
        "related_queries": {
            "top": all_top,
            "rising": rising_filtered
        },
        "meta": {
            "total_rising_queries": all_rising_count,
            "rising_above_500pct": len(rising_filtered)
        }
    }
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return fname


all_keywords = load_root_keywords("root-keywords-tracker.md")
print(f"共 {len(all_keywords)} 个词根")

remaining = [kw for kw in all_keywords if not already_collected(kw)]
print(f"已收集: {len(all_keywords) - len(remaining)}, 待收集: {len(remaining)}")
print(f"时间范围: {TIMEFRAME}")
print(f"Rising 阈值: >{RISING_THRESHOLD}%\n")

high_rising_count = 0

for i, keyword in enumerate(remaining, 1):
    print(f"[{i}/{len(remaining)}] {keyword}")
    try:
        result = get_related_queries(keyword, geo="", timeframe=TIMEFRAME)

        rising_filtered = []
        all_rising_count = 0
        all_top = []

        import pandas as pd
        if result:
            # 处理 rising
            rising_df = result.get("rising")
            if isinstance(rising_df, pd.DataFrame) and not rising_df.empty:
                all_rising_count = len(rising_df)
                for _, row in rising_df.iterrows():
                    query = row.get("query", "")
                    value = row.get("value", 0)
                    numeric = parse_rising_value(value)
                    if numeric >= RISING_THRESHOLD:
                        rising_filtered.append({
                            "query": query,
                            "value": f"+{int(value)}%" if str(value).isdigit() else str(value)
                        })

            # 处理 top
            top_df = result.get("top")
            if isinstance(top_df, pd.DataFrame) and not top_df.empty:
                for _, row in top_df.iterrows():
                    all_top.append({
                        "query": row.get("query", ""),
                        "value": int(row.get("value", 0))
                    })

        if rising_filtered:
            high_rising_count += 1
            print(f"  ★ Rising >500%: {len(rising_filtered)} / {all_rising_count}")
            for r in rising_filtered:
                print(f"    {r['query']} {r['value']}")
        else:
            print(f"  Rising >500%: 0 / {all_rising_count}")

        save_result(keyword, rising_filtered, all_rising_count, all_top)

    except Exception as e:
        print(f"  错误: {e}")
        save_result(keyword, [], 0, [])

    if i < len(remaining):
        delay = random.uniform(35, 55)
        print(f"  等待 {delay:.0f}s...")
        time.sleep(delay)

print(f"\n=== 收集完成 ===")
print(f"共 {len(all_keywords)} 个词根，有 {high_rising_count} 个词根存在 Rising >500% 关键词")
print(f"数据保存到: {DATA_DIR}/")
