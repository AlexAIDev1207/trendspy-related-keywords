#!/usr/bin/env python3
"""
Compute gpts ratios for all rising queries in data_20260313/.
Uses hardcoded B1-B27 results from previous browsermcp session,
then calls trendspy API for remaining unprocessed queries.
"""
import json
import os
import glob
import sys
import time

# Already computed ratios from B1-B27 (browsermcp session)
EXISTING_RATIOS = {
    # B1 (gpts=95)
    "google alternative nyt": 0.084,
    "google alternative nyt mini": 0.021,
    "google alternative crossword": 0.074,
    "common fixture in a gym bathroom": 0.263,
    # B2 (gpts=14)
    "jeanine mason": 0.429,
    "carlton assistant coaches": 0.0,
    "rashmika mandanna": 6.071,
    "rashmika mandanna audio clip": 0.143,
    # B3 (gpts=26)
    "chrome web store": 3.577,
    "adult team avatar": 0.038,
    "avata 360": 2.500,
    "draftly": 0.308,
    # B4 (gpts=95)
    "draftly ai website builder": 0.011,
    "draftly website builder": 0.032,
    "car shipping cost calculator amerifreight": 0.074,
    "cartoon frame nyt": 0.042,
    # B5 (gpts=6)
    "paddy power day 4 cheat sheet": 0.0,
    "zeus 200": 5.833,
    "eaes result checker": 0.0,
    "shadowban checker": 0.333,
    # B6 (gpts=96)
    "xylophone": 0.0,
    "lever recipe": 0.031,
    "comparator preturi gaze naturale": 0.0,
    "das lied von der erde composer": 0.115,
    # B7 (gpts=35)
    "das lied von der erde": 1.171,
    "das lied von der erde composer crossword": 0.029,
    "turpitude": 1.429,
    "humorist david": 0.086,
    # B8 (gpts=7)
    "five below dungeon crawler carl": 0.0,
    "5 below": 8.714,
    "five below": 13.286,
    "pledgemanager": 0.0,
    # B9 (gpts=5)
    "tsunameez dungeon crawler carl": 0.0,
    "tsunameez": 0.0,
    "cloudflare crawl": 0.4,
    "cloudflare": 19.8,
    # B10 (gpts=96)
    "cloudflare crawler": 0.104,
    "miss marple's creator": 0.031,
    "plant that grows from spores 7 little words": 0.073,
    "miss marples creator 7 little words": 0.021,
    # B11 (gpts=26)
    "in a dire condition 7 little words": 0.077,
    "lemonade lucy": 0.538,
    "nysc registration": 2.385,
    "katie perry designer": 0.192,
    # B12 (gpts=29)
    "katie perry": 2.069,
    "kiely irish designer": 0.103,
    "australian designer katie perry": 0.034,
    "designer kiely": 0.103,
    # B13 (gpts=9)
    "katy perry": 10.222,
    "2018 cardi b hit single": 0.111,
    "katy perry designer": 0.111,
    "1986 kenny loggins hit single": 0.111,
    # B14 (gpts=96)
    "2019 dua lipa hit single": 0.167,
    "1972 eagles hit single": 0.094,
    "irish designer kiely known for her stem leaf print": 0.010,
    "anthariya designer studio": 0.052,
    # B15 (gpts=95)
    "african daisy": 0.263,
    "technical name for a lie detector": 0.021,
    "lie detector crossword clue": 0.042,
    "instagram down detector": 0.232,
    # B16 (gpts=96)
    "telegram down detector": 0.010,
    "draw a diagram of image formed by concave lens": 0.042,
    "end of central directory record signature not found": 0.042,
    "letter to editor class 12 format": 0.188,
    # B17 (gpts=96)
    "waning crescent emoji": 0.052,
    "pikachu emoji": 0.188,
    "eveline advance volumiere": 0.021,
    "peroptyx map evaluator": 0.0,
    # B18 (gpts=87)
    "article writing class 12 format": 0.299,
    "article writing class 12": 0.759,
    "article format class 12": 0.368,
    "article writing format class 12": 0.299,
    # B19 (gpts=96)
    "invitation writing format class 12": 0.250,
    "invitation writing class 12": 0.573,
    "json path finder": 0.021,
    "jwt decode": 0.479,
    # B20 (gpts=96)
    "yml formatter": 0.0,
    "trackblazer guide": 0.156,
    "paradox junction easter egg guide": 0.063,
    "guide de pose lebra d'un évier dans une cuisine neuve": 0.083,
    # B21 (gpts=96)
    "hay coaching carriere": 0.177,
    "scarpetta parents guide": 0.052,
    "lego ideas fusée tintin": 0.219,
    "lego ideas tintin": 0.302,
    # B22 (gpts=42)
    "juifs": 1.548,
    "lego playstation": 0.548,
    "vêtements kiabi rappelés": 0.786,
    "isotrétinoïne": 0.857,
    # B23 (gpts=95)
    "mexican flag image": 0.305,
    "investigating crossword clue": 0.021,
    "lodgings crossword clue": 0.011,
    "looked at crossword clue": 0.011,
    # B24 (gpts=96)
    "insults crossword clue": 0.021,
    "nba most points in a game list": 0.292,
    "the hundred auction list": 0.281,
    "a drop of water on a glass surface": 0.313,
    # B25 (gpts=95)
    "criminology board exam result 2026 list of passers": 0.263,
    "criminology board exam result 2026 list of passers pdf download": 0.179,
    "logo gobierno de chile": 0.579,
    "logo gobierno kast": 0.200,
    # B26 (gpts=96)
    "nuevo logo gobierno de chile": 0.135,
    "handala logo": 0.115,
    "nuevo logo gobierno": 0.250,
    "stirring popcorn maker": 0.469,
    # B27 (gpts=94)
    "stiring popcorn maker": 0.021,
    "thursday work meme": 0.074,
    "thursday meme": 0.436,
    "hump day meme": 0.106,
}

DATA_DIR = 'data_20260313'
TIMEFRAME = '2026-03-11 2026-03-13'
GEO = ''
RESULTS_FILE = 'gpts_ratios_all.json'


def load_all_rising_queries():
    """Read all JSON files and extract rising queries with >=500% growth."""
    queries = {}  # {query: {"root_keyword": ..., "value": ...}}
    pattern = os.path.join(DATA_DIR, 'rising_*.json')
    for filepath in sorted(glob.glob(pattern)):
        with open(filepath, encoding='utf-8') as f:
            data = json.load(f)
        root_keyword = data.get('keyword', '')
        for item in data.get('rising_queries_above_500pct', []):
            query = item['query']
            value = item['value']
            if query not in queries:
                queries[query] = {'root_keyword': root_keyword, 'value': value}
    return queries


def get_gpts_ratios_api(queries_list, timeframe, geo):
    """Call trendspy interest_over_time for batches of 4 + gpts."""
    from trendspy import Trends
    import random

    BATCH_SIZE = 4
    baseline = 'gpts'
    ratios = {}

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    ]

    for i in range(0, len(queries_list), BATCH_SIZE):
        batch = queries_list[i:i + BATCH_SIZE]
        kw_list = batch + [baseline]
        print(f"\n[Batch {i//BATCH_SIZE + 1}] Processing: {batch}")

        retry_count = 0
        while True:
            try:
                tr = Trends(hl='en-US')
                headers = {
                    'referer': 'https://www.google.com/',
                    'User-Agent': random.choice(user_agents),
                    'Accept-Language': 'en-US,en;q=0.9',
                }
                time.sleep(random.uniform(1, 3))
                df = tr.interest_over_time(kw_list, headers=headers, geo=geo, timeframe=timeframe)
                print(f"  Got data: {df.shape if df is not None else 'None'}")

                if df is None or df.empty:
                    print("  Empty result, setting ratios to 0.0")
                    for kw in batch:
                        ratios[kw] = 0.0
                else:
                    cols_lower = {c.lower(): c for c in df.columns}
                    gpts_col = cols_lower.get(baseline.lower())
                    if gpts_col is None:
                        print(f"  'gpts' column not found. Columns: {list(df.columns)}")
                        for kw in batch:
                            ratios[kw] = 0.0
                    else:
                        gpts_avg = df[gpts_col].mean()
                        print(f"  gpts avg: {gpts_avg:.2f}")
                        if gpts_avg == 0:
                            for kw in batch:
                                ratios[kw] = 0.0
                        else:
                            for kw in batch:
                                kw_col = cols_lower.get(kw.lower())
                                if kw_col is None:
                                    print(f"  Column not found for '{kw}'")
                                    ratios[kw] = 0.0
                                else:
                                    kw_avg = df[kw_col].mean()
                                    ratio = round(kw_avg / gpts_avg, 3)
                                    ratios[kw] = ratio
                                    print(f"  {kw}: avg={kw_avg:.2f}, ratio={ratio:.3f}")
                break  # success

            except Exception as e:
                error_msg = str(e)
                retry_count += 1
                print(f"  Error (attempt {retry_count}): {error_msg}")

                if "429" in error_msg or "API quota" in error_msg or "Too Many Requests" in error_msg:
                    wait = random.uniform(300, 360)
                    print(f"  Rate limited. Waiting {wait:.0f}s...")
                    time.sleep(wait)
                elif "'NoneType' object" in error_msg:
                    wait = random.uniform(60, 120)
                    print(f"  Empty response. Waiting {wait:.0f}s...")
                    time.sleep(wait)
                elif retry_count >= 5:
                    print(f"  Too many retries, setting ratios to 0.0 for batch")
                    for kw in batch:
                        ratios[kw] = 0.0
                    break
                else:
                    wait = random.uniform(30, 60)
                    print(f"  Other error. Waiting {wait:.0f}s before retry...")
                    time.sleep(wait)

        # Save progress after each batch
        save_progress(ratios)

        # Delay between batches
        if i + BATCH_SIZE < len(queries_list):
            delay = random.uniform(35, 55)
            print(f"  Batch delay: {delay:.0f}s...")
            time.sleep(delay)

    return ratios


def save_progress(new_ratios):
    """Save current state to results file."""
    combined = {**EXISTING_RATIOS, **new_ratios}
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(combined)} ratios to {RESULTS_FILE}")


def generate_report(all_queries, all_ratios):
    """Generate final Markdown report."""
    lines = [
        "# Google Trends Rising Keywords Report",
        f"**Date Range:** 2026-03-11 to 2026-03-13 | **Geo:** Worldwide",
        f"**Generated:** 2026-03-13",
        "",
        "## Rising Queries with ≥500% Growth (gpts ratio computed)",
        "",
        "| Root Keyword | Rising Query | Growth | gpts Ratio |",
        "|---|---|---|---|",
    ]

    # Sort by gpts ratio descending
    sorted_items = sorted(
        all_queries.items(),
        key=lambda x: all_ratios.get(x[0], 0.0),
        reverse=True
    )

    for query, meta in sorted_items:
        ratio = all_ratios.get(query, 'N/A')
        ratio_str = f"{ratio:.3f}" if isinstance(ratio, float) else str(ratio)
        root = meta['root_keyword']
        value = meta['value']
        lines.append(f"| {root} | {query} | {value} | {ratio_str} |")

    # High-ratio section (ratio >= 0.3)
    lines.extend([
        "",
        "## High-Interest Rising Queries (gpts ratio ≥ 0.3)",
        "",
        "| Root Keyword | Rising Query | Growth | gpts Ratio |",
        "|---|---|---|---|",
    ])

    for query, meta in sorted_items:
        ratio = all_ratios.get(query, 0.0)
        if isinstance(ratio, float) and ratio >= 0.3:
            ratio_str = f"{ratio:.3f}"
            root = meta['root_keyword']
            value = meta['value']
            lines.append(f"| {root} | {query} | {value} | {ratio_str} |")

    report_text = "\n".join(lines)
    report_path = os.path.join(DATA_DIR, 'gpts_ratio_report_20260313.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"\nReport saved to: {report_path}")
    return report_text


def main():
    print("=== Loading rising queries from JSON files ===")
    all_queries = load_all_rising_queries()
    print(f"Total unique rising queries: {len(all_queries)}")

    # Load existing results if file exists
    new_ratios = {}
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, encoding='utf-8') as f:
            saved = json.load(f)
        # Extract only the keys not in EXISTING_RATIOS (previously saved new batches)
        for k, v in saved.items():
            if k not in EXISTING_RATIOS:
                new_ratios[k] = v
        print(f"Loaded {len(new_ratios)} previously saved new ratios from {RESULTS_FILE}")

    already_done = set(EXISTING_RATIOS.keys()) | set(new_ratios.keys())
    unprocessed = [q for q in all_queries if q not in already_done]
    print(f"Already processed (B1-B27 + saved): {len(already_done)}")
    print(f"Still unprocessed: {len(unprocessed)}")

    if unprocessed:
        print("\n=== Fetching gpts ratios via trendspy API ===")
        fetched = get_gpts_ratios_api(unprocessed, TIMEFRAME, GEO)
        new_ratios.update(fetched)

    all_ratios = {**EXISTING_RATIOS, **new_ratios}
    print(f"\nTotal ratios computed: {len(all_ratios)}")

    # Save final combined results
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_ratios, f, ensure_ascii=False, indent=2)
    print(f"Final ratios saved to {RESULTS_FILE}")

    print("\n=== Generating Markdown report ===")
    report = generate_report(all_queries, all_ratios)
    print("\nFirst 50 lines of report:")
    print("\n".join(report.split("\n")[:50]))


if __name__ == '__main__':
    main()
