#!/usr/bin/env python3
"""
通过 browsermcp 从 Google Trends 浏览器收集的数据
时间范围: Past 7 days (now 7-d), 地区: Worldwide
收集日期: 2026-03-13
"""
import json
import csv
import os
from datetime import datetime

# 收集到的数据 (从浏览器快照读取并填充)
collected_data = {}

def add_keyword_data(keyword, rising_queries, top_queries):
    """添加一个关键词的数据"""
    collected_data[keyword] = {
        "rising": rising_queries,  # [{"query": "...", "value": "+X%"}, ...]
        "top": top_queries,        # [{"query": "...", "value": N}, ...]
    }

def save_to_files(output_dir="data_20260313"):
    """保存为 CSV 和 JSON 文件"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 保存每个关键词的 JSON 文件
    for keyword, data in collected_data.items():
        json_data = {
            "keyword": keyword,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "timeframe": "now 7-d",
            "geo": "Worldwide",
            "related_queries": {
                "top": data["top"],
                "rising": data["rising"]
            }
        }
        fname = os.path.join(output_dir, f"related_queries_{keyword.replace(' ', '_')}_{timestamp}.json")
        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"Saved JSON: {fname}")

    # 保存汇总 CSV
    csv_fname = os.path.join(output_dir, f"daily_report_20260313.csv")
    with open(csv_fname, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["keyword", "related_keywords", "value", "type"])
        for keyword, data in collected_data.items():
            for item in data["top"]:
                writer.writerow([keyword, item["query"], item["value"], "top"])
            for item in data["rising"]:
                writer.writerow([keyword, item["query"], item["value"], "rising"])
    print(f"Saved CSV: {csv_fname}")
    return csv_fname


# ===== 数据填充区域 (由 browsermcp 采集) =====

add_keyword_data("generator",
    rising=[
        {"query": "spiral art generator", "value": "+250%"},
        {"query": "pika", "value": "+130%"},
        {"query": "runway ml", "value": "+110%"},
        {"query": "runway", "value": "+110%"},
    ],
    top=[
        {"query": "ai generator", "value": 100},
        {"query": "image generator", "value": 33},
        {"query": "video generator", "value": 32},
        {"query": "random generator", "value": 30},
        {"query": "video ai generator", "value": 29},
    ]
)

# TODO: 继续添加其他关键词数据...


if __name__ == "__main__":
    print(f"已收集 {len(collected_data)} 个关键词数据")
    for kw in collected_data:
        d = collected_data[kw]
        print(f"  {kw}: {len(d['rising'])} rising, {len(d['top'])} top")

    result = save_to_files()
    print(f"\n完成! 报告: {result}")
