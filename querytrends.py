from trendspy import Trends
import pandas as pd
import json
import os
import time
import random
from datetime import datetime
import requests
from urllib.parse import quote
import re

def get_related_queries(keyword, geo='', timeframe='today 12-m'):
    """
    获取关键词的相关查询数据，带请求限制
    """
    from config import RETRY_WAIT_CONFIG

    while True:  # 添加无限重试循环
        tr = Trends(hl='zh-CN')
        
        # 随机化 User-Agent
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        headers = {
            'referer': 'https://www.google.com/',
            'User-Agent': random.choice(user_agents),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        
        try:
            # 检查请求限制
            request_limiter.wait_if_needed()
            
            # 添加随机延时
            delay = random.uniform(0.5, 1.5)
            time.sleep(delay)

            related_data = tr.related_queries(
                keyword,
                headers=headers,
                geo=geo,
                timeframe=timeframe
            )
            print(f"成功获取数据！")
            return related_data
            
        except Exception as e:
            error_msg = str(e)
            print(f"尝试获取数据时出错: {error_msg}")
            
            # 如果是配额超限错误，等待后重试
            if "API quota exceeded" in error_msg:
                wait_time = random.uniform(
                    RETRY_WAIT_CONFIG.get('rate_limit_wait_min_seconds', 300),
                    RETRY_WAIT_CONFIG.get('rate_limit_wait_max_seconds', 360)
                )
                print(f"API配额超限，等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue  # 继续下一次重试

            # 如果是429限流错误，等待后重试
            if "429" in error_msg or "Too Many Requests" in error_msg:
                wait_time = random.uniform(
                    RETRY_WAIT_CONFIG.get('rate_limit_wait_min_seconds', 300),
                    RETRY_WAIT_CONFIG.get('rate_limit_wait_max_seconds', 360)
                )
                print(f"遭遇429限流，等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue  # 继续下一次重试

            # 如果是NoneType错误，也等待后重试
            if "'NoneType' object has no attribute 'raise_for_status'" in error_msg:
                wait_time = random.uniform(
                    RETRY_WAIT_CONFIG.get('empty_response_wait_min_seconds', 60),
                    RETRY_WAIT_CONFIG.get('empty_response_wait_max_seconds', 120)
                )
                print(f"请求返回为空，等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue  # 继续下一次重试

            # 其他错误则直接抛出
            raise

def batch_get_queries(keywords, geo='', timeframe='today 12-m', delay_between_queries=5):
    """
    批量获取多个关键词的数据，带间隔控制
    """
    results = {}
    
    for keyword in keywords:
        try:
            print(f"\n正在查询关键词: {keyword}")
            results[keyword] = get_related_queries(keyword, geo, timeframe)
            
            # 在请求之间添加延时
            if keyword != keywords[-1]:  # 如果不是最后一个关键词
                delay = delay_between_queries  # 基础延时（已在调用处随机化）
                print(f"等待 {delay:.1f} 秒后继续下一个查询...")
                time.sleep(delay)
                
        except Exception as e:
            print(f"获取 {keyword} 的数据失败: {str(e)}")
            results[keyword] = None
            
            # 如果遇到错误，增加额外等待时间
            time.sleep(10)
    
    return results

def save_related_queries(keyword, related_data):
    """
    保存相关查询数据到JSON文件
    """
    if not related_data:
        return
    
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    json_data = {
        'keyword': keyword,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'related_queries': {
            'top': related_data['top'].to_dict(orient='records') if isinstance(related_data.get('top'), pd.DataFrame) else related_data.get('top'),
            'rising': related_data['rising'].to_dict(orient='records') if isinstance(related_data.get('rising'), pd.DataFrame) else related_data.get('rising')
        }
    }
    
    # 保存为JSON文件
    filename = f"related_queries_{keyword}_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    return filename

def print_related_queries(related_data):
    """
    打印相关查询词数据
    """
    if not related_data:
        print("没有相关查询数据")
        return
    
    print("\n相关查询词统计:")
    print("=" * 50)
    
    # 打印热门查询
    if 'top' in related_data and related_data['top'] is not None:
        print("\n热门查询:")
        print("-" * 30)
        df = related_data['top']
        if isinstance(df, pd.DataFrame):
            for _, row in df.iterrows():
                print(f"- {row['query']:<30} (相关度: {row['value']})")
    
    # 打印上升趋势查询
    if 'rising' in related_data and related_data['rising'] is not None:
        print("\n上升趋势查询:")
        print("-" * 30)
        df = related_data['rising']
        if isinstance(df, pd.DataFrame):
            for _, row in df.iterrows():
                print(f"- {row['query']:<30} (增长: {row['value']})")


# 主函数
# timeframe可能的值：
# today 12-m：12个月
# now 1-d：1天
# now 7-d：7天
# now 30-d：30天
# now 90-d：90天
# 日期格式：2024-12-28 2024-12-30
def main():
    # 设置要查询的关键词列表
    keywords = ['game']  # 可以添加多个关键词
    geo = ''
    timeframe = 'now 1-d'
    
    print("开始批量查询...")
    print(f"地区: {geo if geo else '全球'}")
    print(f"时间范围: {timeframe}")
    
    try:
        # 批量获取数据
        results = batch_get_queries(
            keywords,
            geo=geo,
            timeframe=timeframe,
            delay_between_queries=100  # 设置请求间隔
        )

        # 处理和保存结果
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        for keyword, data in results.items():
            if data:
                print(f"\n处理 {keyword} 的数据:")
                print_related_queries(data)
                filename = save_related_queries(keyword, data)
                print(f"数据已保存到文件: {filename}")
            else:
                print(f"\n未能获取 {keyword} 的数据")
                
    except Exception as e:
        print(f"批量查询过程中出错: {str(e)}")

class RequestLimiter:
    def __init__(self):
        self.requests = []  # 存储请求时间戳
        self.max_requests_per_min = 30  # 每分钟最大请求数
        self.max_requests_per_hour = 200  # 每小时最大请求数
        
    def can_make_request(self):
        """检查是否可以发起新请求"""
        current_time = time.time()
        
        # 清理超过1小时的旧请求记录
        self.requests = [t for t in self.requests if current_time - t < 3600]
        
        # 获取最近1分钟的请求数
        recent_min_requests = len([t for t in self.requests if current_time - t < 60])
        
        # 获取最近1小时的请求数
        recent_hour_requests = len(self.requests)
        
        if (recent_min_requests >= self.max_requests_per_min or 
            recent_hour_requests >= self.max_requests_per_hour):
            return False
        
        return True
    
    def add_request(self):
        """记录新的请求"""
        self.requests.append(time.time())
    
    def wait_if_needed(self):
        """如果需要，等待直到可以发送请求"""
        while not self.can_make_request():
            wait_time = random.uniform(5, 10)
            print(f"达到请求限制，等待 {wait_time:.1f} 秒...")
            time.sleep(wait_time)
        self.add_request()

# 创建全局请求限制器
request_limiter = RequestLimiter()


def get_interest_over_time(keywords_list, geo='', timeframe='today 12-m'):
    """
    获取关键词列表的随时间变化的搜索兴趣数据。
    复用现有 User-Agent 轮换和 request_limiter 单例。
    与 get_related_queries 相同的无限重试逻辑。
    返回 DataFrame 或 None。
    """
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]

    from config import RETRY_WAIT_CONFIG

    while True:
        tr = Trends(hl='zh-CN')
        headers = {
            'referer': 'https://www.google.com/',
            'User-Agent': random.choice(user_agents),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }

        try:
            request_limiter.wait_if_needed()
            delay = random.uniform(0.5, 1.5)
            time.sleep(delay)

            df = tr.interest_over_time(
                keywords_list,
                headers=headers,
                geo=geo,
                timeframe=timeframe
            )
            print(f"成功获取 interest_over_time 数据！关键词: {keywords_list}")
            return df

        except Exception as e:
            error_msg = str(e)
            print(f"获取 interest_over_time 时出错: {error_msg}")

            if "API quota exceeded" in error_msg:
                wait_time = random.uniform(
                    RETRY_WAIT_CONFIG.get('rate_limit_wait_min_seconds', 300),
                    RETRY_WAIT_CONFIG.get('rate_limit_wait_max_seconds', 360)
                )
                print(f"API配额超限，等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue

            if "429" in error_msg or "Too Many Requests" in error_msg:
                wait_time = random.uniform(
                    RETRY_WAIT_CONFIG.get('rate_limit_wait_min_seconds', 300),
                    RETRY_WAIT_CONFIG.get('rate_limit_wait_max_seconds', 360)
                )
                print(f"遭遇429限流，等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue

            if "'NoneType' object has no attribute 'raise_for_status'" in error_msg:
                wait_time = random.uniform(
                    RETRY_WAIT_CONFIG.get('empty_response_wait_min_seconds', 60),
                    RETRY_WAIT_CONFIG.get('empty_response_wait_max_seconds', 120)
                )
                print(f"请求返回为空，等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
                continue

            raise


def get_gpts_ratio_batch(rising_keywords, geo='', timeframe='today 12-m', checkpoint_path=None):
    """
    将 rising_keywords 与 'gpts' 基准词对比，计算搜索量比值。
    按 batch_size=4 分组，每组 + 'gpts' 调用一次 interest_over_time（5个词，已是API上限）。
    返回 {rising_keyword: ratio} 字典。

    支持断点续跑：
      - 若传入 checkpoint_path，每批完成后自动保存进度
      - 重启时从上次中断处继续，跳过已完成的词

    边界处理：
      - 'gpts' 列不存在 → ratio = 0.0
      - gpts_avg == 0 → ratio = 0.0（避免除零）
      - DataFrame 为 None → 本批所有词 ratio = 0.0
    """
    from config import GPTS_FILTER_CONFIG

    baseline = GPTS_FILTER_CONFIG['baseline_keyword']
    batch_size = GPTS_FILTER_CONFIG['batch_size']
    ratio_map = {}

    # 加载 checkpoint（断点续跑）
    if checkpoint_path and os.path.exists(checkpoint_path):
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            ratio_map = json.load(f)
        print(f"[checkpoint] 已加载 {len(ratio_map)} 条已完成记录，从断点继续...")

    # 只处理尚未完成的关键词
    remaining = [kw for kw in rising_keywords if kw not in ratio_map]
    total = len(rising_keywords)
    skipped = total - len(remaining)
    if skipped > 0:
        print(f"[checkpoint] 跳过已完成 {skipped} 条，剩余 {len(remaining)} 条待处理")

    total_batches = (len(remaining) + batch_size - 1) // batch_size

    for i in range(0, len(remaining), batch_size):
        batch = remaining[i:i + batch_size]
        query_keywords = batch + [baseline]
        batch_num = i // batch_size + 1
        print(f"[Stage 4] 批次 {batch_num}/{total_batches}，已完成 {skipped + i}/{total} 词")

        try:
            df = get_interest_over_time(query_keywords, geo=geo, timeframe=timeframe)
        except Exception as e:
            print(f"get_gpts_ratio_batch 批次出错: {e}")
            df = None

        if df is None or df.empty:
            for kw in batch:
                ratio_map[kw] = 0.0
        else:
            # gpts 列名可能含有大小写变化，不区分大小写查找
            cols_lower = {c.lower(): c for c in df.columns}
            gpts_col = cols_lower.get(baseline.lower())

            if gpts_col is None:
                for kw in batch:
                    ratio_map[kw] = 0.0
            else:
                gpts_avg = df[gpts_col].mean()
                if gpts_avg == 0:
                    for kw in batch:
                        ratio_map[kw] = 0.0
                else:
                    for kw in batch:
                        kw_col = cols_lower.get(kw.lower())
                        if kw_col is None:
                            ratio_map[kw] = 0.0
                        else:
                            kw_avg = df[kw_col].mean()
                            ratio_map[kw] = kw_avg / gpts_avg

        # 每批完成后写入 checkpoint
        if checkpoint_path:
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(ratio_map, f, ensure_ascii=False)

        # 批次间延迟（不是最后一批才等）
        if i + batch_size < len(remaining):
            delay = random.uniform(
                GPTS_FILTER_CONFIG.get('min_batch_delay_seconds', 30),
                GPTS_FILTER_CONFIG.get('max_batch_delay_seconds', 60)
            )
            print(f"gpts比例批次间等待 {delay:.1f} 秒...")
            time.sleep(delay)

    return ratio_map


if __name__ == "__main__":
    main()
