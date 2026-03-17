"""
从已采集的 JSON 文件直接跑后续分析流程（Stage 3.5 ~ Stage 7）。
用法: python run_pipeline_from_json.py [--date 20260304]
"""
import os
import json
import glob
import logging
import argparse
from datetime import datetime

import pandas as pd

from config import (
    MONITOR_CONFIG, LOGGING_CONFIG, STORAGE_CONFIG,
    TRENDS_CONFIG, GPTS_FILTER_CONFIG, GEMINI_CONFIG,
    CONTENT_FILTER_CONFIG, NOTIFICATION_CONFIG,
    KEYWORD_LENGTH_FILTER,
)
from querytrends import get_gpts_ratio_batch
from ai_analyzer import analyze_keywords_batch
from notification import NotificationManager
from trends_monitor import (
    filter_blacklist_rising,
    filter_blacklist_content,
    generate_enhanced_report,
    generate_daily_report,
    get_date_range_timeframe,
)

logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG['level']),
    format=LOGGING_CONFIG['format'],
    handlers=[
        logging.FileHandler(LOGGING_CONFIG['log_file']),
        logging.StreamHandler()
    ]
)


def load_results_from_json(directory: str):
    """从目录中所有 related_queries_*.json 重建 all_results 和 high_rising_trends。"""
    all_results = {}
    high_rising_trends = []
    threshold = MONITOR_CONFIG['rising_threshold']

    files = glob.glob(os.path.join(directory, 'related_queries_*.json'))
    logging.info(f"找到 {len(files)} 个 JSON 文件，开始加载...")

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        keyword = data['keyword']
        rising_list = data['related_queries'].get('rising') or []
        top_list = data['related_queries'].get('top') or []

        rising_df = pd.DataFrame(rising_list) if rising_list else None
        top_df = pd.DataFrame(top_list) if top_list else None

        all_results[keyword] = {'rising': rising_df, 'top': top_df}

        # 收集超过阈值的 rising 关键词
        if rising_df is not None and not rising_df.empty:
            for _, row in rising_df.iterrows():
                raw = str(row['value']).strip().replace(',', '').replace('+', '').replace('%', '')
                numeric = 9999 if raw.lower() == 'breakout' else (float(raw) if raw.lstrip('-').replace('.', '', 1).isdigit() else 0)
                if numeric > threshold:
                    high_rising_trends.append((keyword, row['query'], row['value']))

    logging.info(f"加载完成：{len(all_results)} 个词根，{len(high_rising_trends)} 条 rising 关键词（>{threshold}%）")
    return all_results, high_rising_trends


def filter_long_keywords(
    trends: list[tuple],
) -> tuple[list[tuple], list[tuple]]:
    """过滤不适合建站的长关键词，返回 (保留列表, 跳过列表)。"""
    cfg = KEYWORD_LENGTH_FILTER
    if not cfg.get('enabled', False):
        return trends, []

    max_words = cfg['max_words']
    max_chars = cfg['max_chars']
    kept, skipped = [], []

    for item in trends:
        _, rising_kw, _ = item
        words = len(rising_kw.split())
        chars = len(rising_kw)
        if words > max_words or chars > max_chars:
            skipped.append(item)
        else:
            kept.append(item)

    return kept, skipped


def dedup_subset_keywords(
    trends: list[tuple],
) -> tuple[list[tuple], list[tuple]]:
    """去重：如果短词的所有单词都出现在长词中，跳过长词变体。"""
    cfg = KEYWORD_LENGTH_FILTER
    if not cfg.get('dedup_enabled', False):
        return trends, []

    min_subset = cfg.get('min_subset_words', 2)
    sorted_by_len = sorted(trends, key=lambda x: len(x[1]))
    kept_set: set[int] = set(range(len(sorted_by_len)))
    skipped_indices: set[int] = set()

    for i, (_, long_kw, _) in enumerate(sorted_by_len):
        if i in skipped_indices:
            continue
        long_words = set(long_kw.lower().split())
        for j in range(i):
            if j in skipped_indices:
                continue
            short_kw = sorted_by_len[j][1]
            short_words = set(short_kw.lower().split())
            if len(short_words) >= min_subset and short_words.issubset(long_words):
                skipped_indices.add(i)
                break

    kept = [sorted_by_len[i] for i in range(len(sorted_by_len)) if i not in skipped_indices]
    skipped = [sorted_by_len[i] for i in skipped_indices]
    return kept, skipped


def run_pipeline(date_str: str, skip_gpts: bool = False):
    directory = f"{STORAGE_CONFIG['data_dir_prefix']}{date_str}"
    if not os.path.isdir(directory):
        logging.error(f"目录不存在: {directory}")
        return

    timeframe = get_date_range_timeframe(TRENDS_CONFIG['timeframe'])
    logging.info(f"=== 开始后续分析流程，目录: {directory}，timeframe: {timeframe} ===")

    # Stage 1-3: 从 JSON 加载（跳过采集）
    all_results, high_rising_trends = load_results_from_json(directory)

    # Stage 3.5: 黑名单预过滤
    if high_rising_trends:
        before = len(high_rising_trends)
        high_rising_trends = filter_blacklist_rising(high_rising_trends)
        logging.info(f"Stage 3.5 黑名单过滤: {len(high_rising_trends)}/{before} 条保留")

    # Stage 3.6: 长关键词过滤（跳过不适合建站的长词，减少 GPTs API 调用）
    if high_rising_trends:
        before = len(high_rising_trends)
        high_rising_trends, long_skipped = filter_long_keywords(high_rising_trends)
        if long_skipped:
            logging.info(
                f"Stage 3.6 长词过滤（>{KEYWORD_LENGTH_FILTER['max_words']}词/"
                f">{KEYWORD_LENGTH_FILTER['max_chars']}字符）: "
                f"{len(high_rising_trends)}/{before} 条保留，跳过 {len(long_skipped)} 条"
            )

    # Stage 3.7: 子集去重（短词已覆盖的长词变体跳过 GPTs 查询）
    if high_rising_trends:
        before = len(high_rising_trends)
        high_rising_trends, dedup_skipped = dedup_subset_keywords(high_rising_trends)
        if dedup_skipped:
            logging.info(
                f"Stage 3.7 子集去重: {len(high_rising_trends)}/{before} 条保留，"
                f"跳过 {len(dedup_skipped)} 条变体词"
            )

    # Stage 4: gpts 比例过滤
    if high_rising_trends and not skip_gpts:
        # 可选预筛：只对 value >= pre_filter_threshold 的词做 gpts 查询，减少 API 调用次数
        pre_filter_threshold = GPTS_FILTER_CONFIG.get('pre_filter_threshold', 0)
        if pre_filter_threshold > 0:
            gpts_candidates, auto_excluded = [], []
            for item in high_rising_trends:
                _, _, gv = item
                raw = str(gv).strip().replace(',', '').replace('+', '').replace('%', '')
                numeric = 9999 if raw.lower() == 'breakout' else (
                    float(raw) if raw.lstrip('-').replace('.', '', 1).isdigit() else 0
                )
                (gpts_candidates if numeric >= pre_filter_threshold else auto_excluded).append(item)
            logging.info(
                f"Stage 4 预筛（阈值={pre_filter_threshold}%）: "
                f"{len(gpts_candidates)} 条进入gpts查询，{len(auto_excluded)} 条直接过滤"
            )
            high_rising_trends = gpts_candidates

        checkpoint_path = os.path.join(directory, f'gpts_checkpoint_{date_str}.json')
        logging.info(f"Stage 4: 对 {len(high_rising_trends)} 条 rising 词做 gpts 比例过滤（checkpoint: {checkpoint_path}）...")
        ratio_map = get_gpts_ratio_batch(
            [kw for _, kw, _ in high_rising_trends],
            geo=TRENDS_CONFIG['geo'],
            timeframe=timeframe,
            checkpoint_path=checkpoint_path,
        )
        gpts_filtered = []
        for root_kw, rising_kw, gv in high_rising_trends:
            ratio = ratio_map.get(rising_kw, 0.0)
            if ratio >= GPTS_FILTER_CONFIG['min_ratio']:
                gpts_filtered.append((root_kw, rising_kw, gv, ratio))
            else:
                logging.info(f"Filtered: '{rising_kw}' ratio={ratio:.3f}")
        logging.info(f"Stage 4 完成: {len(gpts_filtered)}/{len(high_rising_trends)} 条保留")
    elif skip_gpts:
        logging.info(f"Stage 4: 跳过 gpts 过滤，直接保留全部 {len(high_rising_trends)} 条")
        gpts_filtered = [(rk, kw, gv, 0.0) for rk, kw, gv in high_rising_trends]
    else:
        gpts_filtered = []

    # Stage 5: Gemini AI 分析
    if gpts_filtered:
        logging.info(f"Stage 5: Gemini 分析 {len(gpts_filtered)} 个关键词...")
        rising_kw_list = [kw for _, kw, _, _ in gpts_filtered]
        analysis_results = analyze_keywords_batch(rising_kw_list)
        analysis_map = {r['keyword']: r for r in analysis_results}
        enriched = [{
            'root_keyword': rk,
            'rising_keyword': kw,
            'growth_value': gv,
            'gpts_ratio': round(ratio, 4),
            'search_intent': analysis_map.get(kw, {}).get('search_intent', ''),
            'site_type': analysis_map.get(kw, {}).get('site_type', ''),
        } for rk, kw, gv, ratio in gpts_filtered]
        logging.info(f"Stage 5 完成")
    else:
        enriched = []

    # Stage 5.5: 黑名单兜底过滤
    if enriched:
        before = len(enriched)
        enriched = filter_blacklist_content(enriched)
        logging.info(f"Stage 5.5 黑名单兜底: {len(enriched)}/{before} 条保留")

    # Stage 6: 生成报告
    legacy_report = generate_daily_report(all_results, directory)
    enhanced_csv, enhanced_md = generate_enhanced_report(enriched, directory)
    logging.info(f"Stage 6 报告已生成: {enhanced_md}")

    # Stage 7: 通知
    attachments = [f for f in [legacy_report, enhanced_csv, enhanced_md] if f]
    notification_manager = NotificationManager()
    if legacy_report:
        notification_manager.send_notification(
            subject=f"Daily Trends Report (partial) - {date_str}",
            body=f"""<h2>趋势报告（部分数据）</h2>
            <p>本次采集词根数：{len(all_results)}（共124个，因IP限流中断）</p>
            <p>Rising关键词过滤后：{len(enriched)} 条</p>""",
            attachments=attachments
        )

    logging.info("=== 后续分析流程全部完成 ===")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=datetime.now().strftime('%Y%m%d'),
                        help='数据目录日期，格式 YYYYMMDD，默认今天')
    parser.add_argument('--skip-gpts', action='store_true',
                        help='跳过 gpts 比例过滤，直接送 Gemini 分析')
    args = parser.parse_args()
    run_pipeline(args.date, skip_gpts=args.skip_gpts)
