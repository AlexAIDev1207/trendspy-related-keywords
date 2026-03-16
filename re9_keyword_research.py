#!/usr/bin/env python3
"""
RE9 关键词深度挖掘脚本
两轮 related_queries 发现 RE9 主题全部长尾搜索词
输出：关键词 + gpts 比值 + 主题分群 + 难度模式标注
"""

import time
import random
import logging
import os
import json
import pandas as pd
import google.generativeai as genai
from datetime import datetime

from querytrends import get_related_queries, get_gpts_ratio_batch
from config import TRENDS_CONFIG, GEMINI_CONFIG

# ─── 配置 ─────────────────────────────────────────────────────────────────────

# 第一轮种子词（RE9 已知高搜索量词）
SEED_KEYWORDS = [
    "re9 safe code",
    "re9 puzzle box",
    "resident evil requiem safe code",
    "resident evil requiem walkthrough",
]

TIMEFRAME    = "now 7-d"   # RE9 发售首周，用7天捕捉完整数据
GEO          = ""           # 全球
OUTPUT_DIR   = "re9_research"
MIN_GPTS_RATIO  = 0.05     # 发现模式，阈值放低
ROUND2_TOP_N    = 15       # Round1 中取多少词做 Round2 种子
BATCH_SIZE      = 5        # 每批查询关键词数量
BATCH_INTERVAL  = 300      # 批次间隔（秒）

# 难度模式相关词汇特征（用于自动标注）
DIFFICULTY_SIGNALS = [
    "insanity", "insanity mode", "hardcore", "hard mode", "madhouse",
    "casual", "standard mode", "normal mode", "easy mode",
    "new game plus", "ng+", "second playthrough", "2nd run",
    "difficulty", "challenge run", "no damage", "minimalist",
    "speed run", "speedrun", "speed demon",
]

# 关键词分群 Prompt 用到的分类
CLUSTER_CATEGORIES = [
    "保险箱密码",    # safe codes, lock combinations
    "谜题/解谜",    # puzzle boxes, quartz, organ puzzles
    "Boss攻略",     # how to beat specific bosses
    "收集品",       # files, mr raccoon, coins, BSAA containers
    "成就/奖杯",    # trophy guide, case closed, speed demon
    "剧情/角色",    # story, endings, grace, leon, lore
    "游戏机制",     # crafting, blood collector, upgrades, weapons
    "攻略/通关",    # walkthrough, chapter guide, complete guide
    "难度模式",     # insanity, casual, challenge runs
    "其他",
]

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("re9_research.log"),
        logging.StreamHandler(),
    ],
)

# ─── 核心函数 ─────────────────────────────────────────────────────────────────

def extract_keywords_from_data(related_data, max_top=20, max_rising=20):
    """从 related_queries 结果中提取关键词列表"""
    results = []
    if not related_data:
        return results

    if "top" in related_data and related_data["top"] is not None:
        df = related_data["top"]
        if isinstance(df, pd.DataFrame):
            for _, row in df.head(max_top).iterrows():
                results.append({
                    "keyword": str(row["query"]).strip(),
                    "value": int(row["value"]),
                    "type": "top",
                })

    if "rising" in related_data and related_data["rising"] is not None:
        df = related_data["rising"]
        if isinstance(df, pd.DataFrame):
            for _, row in df.head(max_rising).iterrows():
                results.append({
                    "keyword": str(row["query"]).strip(),
                    "value": int(row["value"]),
                    "type": "rising",
                })

    return results


def score_for_round2(item):
    """
    计算 Round2 种子词的优先级分数。
    rising 词增长值缩放（避免和 top 值直接比较），top 词直接用相关度值。
    """
    if item["type"] == "rising":
        return item["value"] * 0.1  # 增长1000% ≈ top值100
    return item["value"]


def tag_difficulty_mode(keyword: str) -> bool:
    """判断关键词是否涉及难度模式"""
    kw_lower = keyword.lower()
    return any(signal in kw_lower for signal in DIFFICULTY_SIGNALS)


def cluster_keywords_with_gemini(keywords: list) -> dict:
    """
    用 Gemini 将关键词批量分群，返回 {keyword: cluster_name}
    每批最多 30 个词。
    """
    if not GEMINI_CONFIG["api_key"]:
        logging.warning("GEMINI_API_KEY 未配置，跳过分群")
        return {kw: "未分群" for kw in keywords}

    genai.configure(api_key=GEMINI_CONFIG["api_key"])
    model = genai.GenerativeModel(GEMINI_CONFIG["model"])
    category_str = "、".join(CLUSTER_CATEGORIES)
    batch_size = 30
    result_map = {}

    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i + batch_size]
        prompt = f"""You are an SEO analyst specializing in game guide content.
Classify each keyword into EXACTLY ONE of these Chinese categories:
{category_str}

Rules:
- 保险箱密码: safe codes, lock codes, combination codes, safe locations
- 谜题/解谜: puzzle box, quartz puzzles, organ puzzles, briefcase code, blood analyzer
- Boss攻略: how to beat [boss name], boss strategy, boss weakness
- 收集品: files, mr raccoon, antique coins, BSAA containers, plant seedlings, collectibles
- 成就/奖杯: trophy guide, achievement, platinum, case closed, speed demon, minimalist
- 剧情/角色: story, ending, grace, leon, lore, characters, who is, explained
- 游戏机制: weapons, crafting, blood collector, upgrades, ammo, inventory, tips
- 攻略/通关: walkthrough, chapter guide, complete guide, how to progress, where to go
- 难度模式: insanity mode, casual, hardcore, speedrun, challenge run, ng+
- 其他: anything that doesn't fit above

Keywords: {json.dumps(batch, ensure_ascii=False)}

Return ONLY a valid JSON object: {{"keyword": "category", ...}}
"""
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:-1])
            data = json.loads(text)
            result_map.update(data)
        except Exception as e:
            logging.warning(f"Gemini 分群失败（批次 {i}）: {e}")
            for kw in batch:
                result_map[kw] = "其他"

        if i + batch_size < len(keywords):
            time.sleep(2)

    return result_map


def generate_output(all_data: dict):
    """生成 CSV + Markdown 报告"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")

    # 转为列表并排序
    rows = sorted(all_data.values(), key=lambda x: x["gpts_ratio"], reverse=True)

    # ── CSV ──
    csv_path = os.path.join(OUTPUT_DIR, f"re9_keywords_{today}.csv")
    df = pd.DataFrame(rows, columns=[
        "keyword", "type", "value", "gpts_ratio",
        "source", "seed_keyword", "cluster", "is_difficulty_mode"
    ])
    df.to_csv(csv_path, index=False)
    logging.info(f"CSV 已保存: {csv_path}")

    # ── Markdown ──
    md_path = os.path.join(OUTPUT_DIR, f"re9_keywords_{today}.md")
    lines = [
        f"# RE9 关键词研究报告 - {datetime.now().strftime('%Y-%m-%d')}",
        "",
        f"> 时间范围: {TIMEFRAME} | 种子词: {len(SEED_KEYWORDS)} | "
        f"发现关键词: {len(rows)} | GPTs比例阈值: ≥{MIN_GPTS_RATIO}",
        "",
        "## 汇总统计",
        "",
    ]

    # 统计
    cluster_counts = df["cluster"].value_counts()
    difficulty_count = df["is_difficulty_mode"].sum()
    lines.append(f"| 分群 | 关键词数 |")
    lines.append(f"|---|---|")
    for cluster, count in cluster_counts.items():
        lines.append(f"| {cluster} | {count} |")
    lines.append(f"| **涉及难度模式的词** | **{difficulty_count}** |")
    lines.append("")

    # 按分群输出详细表格
    for cluster in CLUSTER_CATEGORIES:
        group = df[df["cluster"] == cluster].sort_values("gpts_ratio", ascending=False)
        if group.empty:
            continue

        lines.append(f"## {cluster}")
        lines.append("")
        lines.append("| 关键词 | 类型 | 搜索值 | GPTs比值 | 来源 | 难度模式 |")
        lines.append("|---|---|---|---|---|---|")

        for _, row in group.iterrows():
            diff_tag = "✓" if row["is_difficulty_mode"] else ""
            val_display = f"{row['value']}%" if row["type"] == "rising" else str(row["value"])
            lines.append(
                f"| {row['keyword']} | {row['type']} | {val_display} | "
                f"{row['gpts_ratio']:.4f} | {row['source']} | {diff_tag} |"
            )
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logging.info(f"Markdown 已保存: {md_path}")

    return csv_path, md_path


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def run_research():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_keywords = {}  # key: keyword.lower(), value: dict

    # ── Round 1: 种子词查询 ──────────────────────────────────────────────────
    logging.info(f"=== Round 1: 查询 {len(SEED_KEYWORDS)} 个种子词 ===")

    for idx, seed in enumerate(SEED_KEYWORDS):
        logging.info(f"[Round1] 查询: {seed}")
        data = get_related_queries(seed, geo=GEO, timeframe=TIMEFRAME)

        if data:
            items = extract_keywords_from_data(data, max_top=20, max_rising=20)
            for item in items:
                key = item["keyword"].lower()
                if key not in all_keywords:
                    all_keywords[key] = {
                        "keyword": item["keyword"],
                        "type": item["type"],
                        "value": item["value"],
                        "source": "round1",
                        "seed_keyword": seed,
                    }
            logging.info(f"  → 获得 {len(items)} 条，累计 {len(all_keywords)} 个唯一关键词")

        # 批次间隔
        if (idx + 1) % BATCH_SIZE == 0 and idx + 1 < len(SEED_KEYWORDS):
            logging.info(f"批次间隔，等待 {BATCH_INTERVAL}s...")
            time.sleep(BATCH_INTERVAL)
        else:
            delay = random.uniform(10, 20)
            logging.info(f"等待 {delay:.1f}s...")
            time.sleep(delay)

    logging.info(f"Round 1 完成，共 {len(all_keywords)} 个唯一关键词")

    # ── 选择 Round2 种子词 ────────────────────────────────────────────────────
    sorted_r1 = sorted(all_keywords.values(), key=score_for_round2, reverse=True)
    round2_seeds = [item["keyword"] for item in sorted_r1[:ROUND2_TOP_N]]
    logging.info(f"Round 2 种子词（Top {ROUND2_TOP_N}）: {round2_seeds}")

    # ── Round 2: 扩展查询 ─────────────────────────────────────────────────────
    logging.info(f"=== Round 2: 查询 {len(round2_seeds)} 个扩展词 ===")

    for idx, seed in enumerate(round2_seeds):
        logging.info(f"[Round2] 查询: {seed}")
        data = get_related_queries(seed, geo=GEO, timeframe=TIMEFRAME)

        if data:
            items = extract_keywords_from_data(data, max_top=15, max_rising=15)
            new_count = 0
            for item in items:
                key = item["keyword"].lower()
                if key not in all_keywords:
                    all_keywords[key] = {
                        "keyword": item["keyword"],
                        "type": item["type"],
                        "value": item["value"],
                        "source": "round2",
                        "seed_keyword": seed,
                    }
                    new_count += 1
            logging.info(f"  → 新增 {new_count} 条，累计 {len(all_keywords)} 个唯一关键词")

        # 批次间隔
        if (idx + 1) % BATCH_SIZE == 0 and idx + 1 < len(round2_seeds):
            logging.info(f"批次间隔，等待 {BATCH_INTERVAL}s...")
            time.sleep(BATCH_INTERVAL)
        else:
            delay = random.uniform(10, 20)
            logging.info(f"等待 {delay:.1f}s...")
            time.sleep(delay)

    logging.info(f"Round 2 完成，共 {len(all_keywords)} 个唯一关键词")

    # ── Stage 3: 计算 gpts 比值 ───────────────────────────────────────────────
    all_kw_list = [v["keyword"] for v in all_keywords.values()]
    logging.info(f"=== Stage 3: 计算 gpts 比值（{len(all_kw_list)} 个词）===")
    ratio_map = get_gpts_ratio_batch(all_kw_list, geo=GEO, timeframe=TIMEFRAME)

    for key, data in all_keywords.items():
        data["gpts_ratio"] = round(ratio_map.get(data["keyword"], 0.0), 4)

    # 过滤低流量词
    filtered = {k: v for k, v in all_keywords.items() if v["gpts_ratio"] >= MIN_GPTS_RATIO}
    logging.info(f"过滤后（gpts_ratio ≥ {MIN_GPTS_RATIO}）：{len(filtered)} 个关键词")

    # ── Stage 4: 难度模式标注 ─────────────────────────────────────────────────
    for key, data in filtered.items():
        data["is_difficulty_mode"] = tag_difficulty_mode(data["keyword"])

    diff_count = sum(1 for v in filtered.values() if v["is_difficulty_mode"])
    logging.info(f"涉及难度模式的关键词：{diff_count} 个")

    # ── Stage 5: Gemini 分群 ──────────────────────────────────────────────────
    kw_list = [v["keyword"] for v in filtered.values()]
    logging.info(f"=== Stage 5: Gemini 分群（{len(kw_list)} 个词）===")
    cluster_map = cluster_keywords_with_gemini(kw_list)

    for key, data in filtered.items():
        # 难度模式词优先标注为"难度模式"分群
        if data["is_difficulty_mode"]:
            data["cluster"] = "难度模式"
        else:
            data["cluster"] = cluster_map.get(data["keyword"], "其他")

    # ── Stage 6: 输出报告 ─────────────────────────────────────────────────────
    logging.info("=== Stage 6: 生成报告 ===")
    csv_path, md_path = generate_output(filtered)

    logging.info("=" * 60)
    logging.info(f"研究完成！共发现 {len(filtered)} 个有效关键词")
    logging.info(f"CSV: {csv_path}")
    logging.info(f"Markdown: {md_path}")
    logging.info("=" * 60)

    return filtered


if __name__ == "__main__":
    run_research()
