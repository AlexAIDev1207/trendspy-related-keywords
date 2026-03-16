#!/usr/bin/env python3
"""
Google Trends Related Queries 收集器
直接调用 Google Trends API，模仿浏览器请求，不依赖 trendspy
时间范围: Past 7 days (now 7-d), 地区: Worldwide
"""
import requests
import json
import csv
import os
import time
import random
import re
from datetime import datetime, timedelta

OUTPUT_DIR = "data_20260313"
TIMEFRAME = "now 7-d"
GEO = ""  # Worldwide

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://trends.google.com/",
    "Origin": "https://trends.google.com",
}

session = requests.Session()
session.headers.update(HEADERS)

# ──────────────────────────────────────────────
# Step 1: 获取 explore widget token
# ──────────────────────────────────────────────
def get_widget_token(keyword: str, timeframe: str = TIMEFRAME, geo: str = GEO):
    url = "https://trends.google.com/trends/api/explore"
    req_payload = {
        "comparisonItem": [{"keyword": keyword, "geo": geo, "time": timeframe}],
        "category": 0,
        "property": "",
    }
    params = {
        "hl": "en-US",
        "tz": "-480",
        "req": json.dumps(req_payload, separators=(",", ":")),
    }
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    # Google prepends ")]}',\n" to prevent JSON hijacking
    text = r.text.lstrip(")]}'")
    data = json.loads(text)
    widgets = data.get("widgets", [])
    for w in widgets:
        if w.get("id") == "RELATED_QUERIES":
            return w.get("token"), w.get("request", {})
    return None, None


# ──────────────────────────────────────────────
# Step 2: 用 token 获取相关查询
# ──────────────────────────────────────────────
def get_related_queries(token: str, widget_request: dict):
    url = "https://trends.google.com/trends/api/widgetdata/relatedsearches"
    params = {
        "hl": "en-US",
        "tz": "-480",
        "req": json.dumps(widget_request, separators=(",", ":")),
        "token": token,
    }
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    text = r.text.lstrip(")]}'")
    return json.loads(text)


# ──────────────────────────────────────────────
# 解析 related queries 响应
# ──────────────────────────────────────────────
def parse_queries(raw: dict):
    top = []
    rising = []
    try:
        ranked = raw["default"]["rankedList"]
        for item in ranked:
            ranked_kw = item.get("rankedKeyword", [])
            query_type = item.get("rankingType", "")
            for kw in ranked_kw:
                query = kw.get("query", "")
                value = kw.get("value", 0)
                if query_type == "TOP":
                    top.append({"query": query, "value": value})
                elif query_type == "RISING":
                    # rising value 是数字，但我们显示为 +X%
                    pct = kw.get("formattedValue", f"+{value}%")
                    rising.append({"query": query, "value": pct})
    except (KeyError, TypeError) as e:
        print(f"  解析错误: {e}")
    return top, rising


# ──────────────────────────────────────────────
# 主采集函数
# ──────────────────────────────────────────────
def collect_keyword(keyword: str):
    print(f"\n正在采集: {keyword}")
    for attempt in range(5):
        try:
            delay = random.uniform(8, 15)
            time.sleep(delay)

            token, widget_req = get_widget_token(keyword)
            if not token:
                print(f"  未获取到 token，跳过")
                return None

            delay2 = random.uniform(2, 5)
            time.sleep(delay2)

            raw = get_related_queries(token, widget_req)
            top, rising = parse_queries(raw)
            print(f"  ✓ top={len(top)}, rising={len(rising)}")
            return {"top": top, "rising": rising}

        except requests.exceptions.HTTPError as e:
            if "429" in str(e) or "quota" in str(e).lower():
                wait = random.uniform(300, 360)
                print(f"  遭遇限流，等待 {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP错误 (尝试{attempt+1}): {e}")
                time.sleep(30)
        except Exception as e:
            print(f"  错误 (尝试{attempt+1}): {e}")
            time.sleep(20)
    return None


# ──────────────────────────────────────────────
# 保存数据
# ──────────────────────────────────────────────
def save_results(all_data: dict):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 每个关键词保存 JSON
    for kw, data in all_data.items():
        if not data:
            continue
        json_data = {
            "keyword": kw,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "timeframe": TIMEFRAME,
            "geo": "Worldwide",
            "related_queries": {
                "top": data["top"],
                "rising": data["rising"]
            }
        }
        fname = os.path.join(OUTPUT_DIR, f"related_queries_{kw.replace(' ', '_')}_{timestamp}.json")
        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

    # 汇总 CSV
    csv_fname = os.path.join(OUTPUT_DIR, "daily_report_20260313.csv")
    with open(csv_fname, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["keyword", "related_keywords", "value", "type"])
        for kw, data in all_data.items():
            if not data:
                continue
            for item in data["top"]:
                writer.writerow([kw, item["query"], item["value"], "top"])
            for item in data["rising"]:
                writer.writerow([kw, item["query"], item["value"], "rising"])

    print(f"\n✓ 数据已保存到 {OUTPUT_DIR}/")
    print(f"  CSV: {csv_fname}")
    return csv_fname


# ──────────────────────────────────────────────
# 关键词列表（🔥 优先级）
# ──────────────────────────────────────────────
FIRE_KEYWORDS = [
    # AI 生成类
    "generator", "creator", "maker", "writer",
    # 导航/对比
    "alternative",
    # 数据流动
    "downloader", "extractor",
    # 转换
    "converter", "compressor",
    # 编辑/优化
    "editor", "remover",
    # 检测/评估
    "checker", "detector", "humanizer", "calculator",
    # 文字处理
    "summarizer", "rewriter", "proofreader",
    # 图片工具
    "image", "photo", "logo", "avatar", "style",
    "interior design", "upscaler", "anime", "product photo",
    # 音乐
    "music",
    # 通用
    "video",
    # AI 品牌词
    "ai", "gpt", "prompter",
    # 游戏
    "cheat",
]

# ⭐ 次优先级（可选运行）
STAR_KEYWORDS = [
    "assistant", "researcher", "builder", "composer",
    "best", "directory", "finder", "template", "guide",
    "designer", "saver", "scraper", "translator",
    "optimizer", "enhancer", "scanner", "analyzer",
    "planner", "scheduler", "manager", "sender", "recorder",
    "viewer", "simulator", "transcriber", "paraphraser",
    "font", "chart", "diagram", "cartoon", "audio",
    "bot", "code", "text",
]


if __name__ == "__main__":
    import sys

    # 先采集之前浏览器已收集的数据作为种子
    browser_data = {
        "generator": {
            "rising": [
                {"query": "spiral art generator", "value": "+250%"},
                {"query": "pika", "value": "+130%"},
                {"query": "runway ml", "value": "+110%"},
                {"query": "runway", "value": "+110%"},
            ],
            "top": [
                {"query": "ai generator", "value": 100},
                {"query": "image generator", "value": 33},
                {"query": "video generator", "value": 32},
                {"query": "random generator", "value": 30},
                {"query": "video ai generator", "value": 29},
            ]
        },
        "creator": {
            "rising": [
                {"query": "young sheldon creator", "value": "+400%"},
                {"query": "global creator academy", "value": "+300%"},
                {"query": "tyler the creator birthday", "value": "+190%"},
                {"query": "new york times", "value": "+160%"},
                {"query": "anthropic skill creator", "value": "+120%"},
            ],
            "top": [
                {"query": "the creator", "value": 100},
                {"query": "tyler the creator", "value": 37},
                {"query": "content creator", "value": 35},
                {"query": "ai creator", "value": 32},
                {"query": "youtube creator", "value": 17},
            ]
        },
    }

    all_data = dict(browser_data)

    # 确定要采集的关键词（排除已有的）
    remaining = [kw for kw in FIRE_KEYWORDS if kw not in all_data]

    print(f"开始采集 {len(remaining)} 个关键词（已有 {len(browser_data)} 个来自浏览器）")
    print(f"预计时间：{len(remaining) * 12 / 60:.1f} 分钟（按12秒/词估算）\n")

    for i, kw in enumerate(remaining, 1):
        print(f"[{i}/{len(remaining)}]", end=" ")
        result = collect_keyword(kw)
        if result:
            all_data[kw] = result

        # 每10个关键词保存一次中间结果
        if i % 10 == 0:
            print(f"\n--- 中间保存 ({i}/{len(remaining)}) ---")
            save_results(all_data)

    # 最终保存
    csv_file = save_results(all_data)

    print(f"\n=== 完成 ===")
    print(f"采集了 {len(all_data)} 个关键词")
    print(f"报告: {csv_file}")
