#!/usr/bin/env python3
"""
收集 root-keywords-tracker.md 中所有词根的 Rising 关键词（>500%）
时间范围: 2026-03-11 to 2026-03-13
跳过已在 data_20260313/ 中已有结果的词根
"""
import json
import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from keyword_loader import load_root_keywords
from querytrends import get_related_queries
from config import RETRY_WAIT_CONFIG

DATA_DIR = "data_20260313"
TIMEFRAME = "2026-03-11 2026-03-13"
RISING_THRESHOLD = 500  # 只保留 >500% 的 rising

os.makedirs(DATA_DIR, exist_ok=True)

# 加载所有词根
all_keywords = load_root_keywords("root-keywords-tracker.md")
print(f"共 {len(all_keywords)} 个词根")

# 找出已收集的词根（在 data_20260313/ 中已有 rising_<keyword>.json）
def already_collected(keyword):
    safe = keyword.replace(" ", "_").replace("/", "_")
    return os.path.exists(os.path.join(DATA_DIR, f"rising_{safe}.json"))

remaining = [kw for kw in all_keywords if not already_collected(kw)]
print(f"已跳过 {len(all_keywords) - len(remaining)} 个已收集的词根")
print(f"待收集: {len(remaining)} 个词根")
print()

def parse_rising_value(value_str):
    """解析 rising value，返回数值（Breakout = 9999）"""
    if value_str is None:
        return 0
    s = str(value_str).strip().replace(",", "").replace("+", "").replace("%", "")
    if s.lower() == "breakout":
        return 9999
    try:
        return float(s)
    except:
        return 0

def save_result(keyword, rising_above_500, total_count):
    safe = keyword.replace(" ", "_").replace("/", "_")
    fname = os.path.join(DATA_DIR, f"rising_{safe}.json")
    data = {
        "keyword": keyword,
        "date_range": "2026-03-11 to 2026-03-13",
        "geo": "Worldwide",
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rising_queries": total_count,
        "rising_queries_above_500pct": rising_above_500
    }
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  已保存: {fname}")

for i, keyword in enumerate(remaining, 1):
    print(f"[{i}/{len(remaining)}] 查询: {keyword}")
    try:
        result = get_related_queries(keyword, geo="", timeframe=TIMEFRAME)

        rising_above_500 = []
        total_count = 0

        if result and result.get("rising") is not None:
            import pandas as pd
            rising_df = result["rising"]
            if isinstance(rising_df, pd.DataFrame) and not rising_df.empty:
                total_count = len(rising_df)
                for _, row in rising_df.iterrows():
                    query = row.get("query", "")
                    value = row.get("value", 0)
                    numeric = parse_rising_value(value)
                    if numeric >= RISING_THRESHOLD:
                        rising_above_500.append({
                            "query": query,
                            "value": str(value) if not str(value).startswith("+") else str(value)
                        })

        print(f"  Rising >500%: {len(rising_above_500)} / {total_count} total")
        save_result(keyword, rising_above_500, total_count)

    except Exception as e:
        print(f"  错误: {e}")
        # 保存空结果以标记为已处理（防止重复）
        save_result(keyword, [], 0)

    # 关键词间延迟（避免连续触发限流）
    if i < len(remaining):
        delay = random.uniform(15, 25)
        print(f"  等待 {delay:.0f}s ...")
        time.sleep(delay)

print("\n=== 收集完成 ===")
print(f"数据已保存到 {DATA_DIR}/")
