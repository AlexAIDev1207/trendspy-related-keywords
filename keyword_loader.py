import re
import logging
from typing import List


def load_root_keywords(filepath: str = "root-keywords-tracker.md") -> List[str]:
    """逐行解析 markdown 表格，提取第一列词根（处理多词，如 'interior design'）"""
    keywords = []
    skip_patterns = ['词根', '---', 'Root', 'Keyword', '标记', '含义']
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.startswith('|'):
                continue
            if any(p in line for p in skip_patterns):
                continue
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if not cells:
                continue
            kw = re.sub(r'\*\*(.+?)\*\*', r'\1', cells[0]).strip()
            # 只保留含有英文字母的词根（排除纯 emoji、纯中文等非关键词行）
            if kw and re.search(r'[a-zA-Z]', kw):
                keywords.append(kw)
    logging.info(f"Loaded {len(keywords)} root keywords from {filepath}")
    return keywords


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    kws = load_root_keywords()
    print(f"Total: {len(kws)}")
    print(kws[:5])
