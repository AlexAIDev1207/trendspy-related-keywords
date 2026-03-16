import json
import logging
import time
from typing import List, Dict

import google.generativeai as genai

from config import GEMINI_CONFIG

SITE_TYPE_OPTIONS = ["工具站", "内容站", "游戏站", "目录站"]


def analyze_keywords_batch(keywords: List[str]) -> List[Dict]:
    """
    批量分析关键词。每批 batch_size（默认20）个词调用一次 Gemini API。
    返回: [{keyword, search_intent, site_type}, ...]
    失败时对应词返回空字符串，不中断整体流程。
    """
    if not GEMINI_CONFIG['api_key']:
        logging.warning("GEMINI_API_KEY 未配置，跳过 AI 分析")
        return [{'keyword': kw, 'search_intent': '', 'site_type': ''} for kw in keywords]

    genai.configure(api_key=GEMINI_CONFIG['api_key'])
    model = genai.GenerativeModel(GEMINI_CONFIG['model'])
    batch_size = GEMINI_CONFIG['analysis_batch_size']
    results = []

    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i + batch_size]
        batch_results = _analyze_single_batch(model, batch)
        results.extend(batch_results)
        if i + batch_size < len(keywords):
            time.sleep(2)  # 批次间小间隔

    return results


def _analyze_single_batch(model, batch: List[str]) -> List[Dict]:
    """
    向 Gemini 发送单批分析请求，解析 JSON 返回值。

    Prompt 要求模型仅返回 JSON array，格式:
    [{"keyword": "...", "search_intent": "≤30字中文", "site_type": "工具站"}, ...]

    site_type 分类规则:
    - 工具站: 用户想用在线工具完成具体任务（生成、转换、编辑等）
    - 内容站: 用户想获取信息、教程、攻略、列表
    - 游戏站: 与游戏、作弊码、谜题、答案相关
    - 目录站: 用户想比较/发现多个产品、服务或替代品

    失败时返回含空字符串的默认结构列表。
    """
    prompt = f"""You are an SEO keyword analyst. For each English search keyword below, provide:
1. "search_intent": Chinese description of what users want (STRICT max 30 Chinese characters)
2. "site_type": classify as exactly one of: 工具站, 内容站, 游戏站, 目录站

Classification rules:
- 工具站: user wants to use an online tool (generate, convert, edit, compress, etc.)
- 内容站: user wants to read/watch content, guides, tutorials, lists, comparisons
- 游戏站: keyword relates to games, cheats, walkthroughs, puzzles, answers, hints
- 目录站: user wants to find/compare multiple products, services, or alternatives

Keywords to analyze: {json.dumps(batch, ensure_ascii=False)}

Respond ONLY with a valid JSON array. No markdown, no explanation.
Example format: [{{"keyword": "ai image generator", "search_intent": "用AI生成图片的在线工具", "site_type": "工具站"}}]"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # 去除可能的 markdown 代码块包裹
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1])
        data = json.loads(text)
        # 验证并补全缺失词
        result_map = {item['keyword']: item for item in data if 'keyword' in item}
        return [result_map.get(kw, {'keyword': kw, 'search_intent': '', 'site_type': ''}) for kw in batch]
    except Exception as e:
        logging.warning(f"Gemini batch analysis failed: {e}")
        return [{'keyword': kw, 'search_intent': '', 'site_type': ''} for kw in batch]
