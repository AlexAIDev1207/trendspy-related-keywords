import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# Notification Configuration
NOTIFICATION_CONFIG = {
    'method': 'email',  # 可选值: 'email', 'wechat', 'both'
    'wechat_receiver': os.getenv('TRENDS_WECHAT_RECEIVER', ''),  # 微信接收者的备注名或微信号
}

# Email Configuration
EMAIL_CONFIG = {
    'smtp_server': os.getenv('TRENDS_SMTP_SERVER', 'smtp.gmail.com'),
    'smtp_port': int(os.getenv('TRENDS_SMTP_PORT', '587')),
    'sender_email': os.getenv('TRENDS_SENDER_EMAIL', ''),
    'sender_password': os.getenv('TRENDS_SENDER_PASSWORD', ''),
    'recipient_email': os.getenv('TRENDS_RECIPIENT_EMAIL', '')
}

# Keywords to monitor
# 已移除硬编码列表，由 keyword_loader.load_root_keywords() 从 root-keywords-tracker.md 动态加载
# KEYWORDS = ["Image", "Video", ...]


# Trends Query Configuration
TRENDS_CONFIG = {
    'timeframe': 'last-2-d',  # 可选值: now 1-d, now 7-d, now 30-d, now 90-d, today 12-m, 
                            # last-2-d, last-3-d 或者 "2024-01-01 2024-01-31"
    'geo': '',  # 地区代码，例如: 'US' 表示美国, 'CN' 表示中国, '' 表示全球
}

# Rate Limiting Configuration
RATE_LIMIT_CONFIG = {
    'max_retries': 3,
    'min_delay_between_queries': 15,  # 最小延迟（秒）
    'max_delay_between_queries': 25,  # 最大延迟（秒）
    'batch_size': 3,                  # 每批处理的关键词数量
    'batch_interval': 300,            # 批次间隔时间（秒）
}

# Schedule Configuration
SCHEDULE_CONFIG = {
    'hour': 23,                    # 计划执行的小时（0-23）
    'minute': 5,                 # 计划执行的分钟（0-59）
    'random_delay_minutes': 15   # 随机延迟的最大分钟数（可选）
}

# Monitoring Configuration
MONITOR_CONFIG = {
    'rising_threshold': 500,  # 高增长趋势阈值
}

# Logging Configuration
LOGGING_CONFIG = {
    'log_file': 'trends_monitor.log',
    'level': 'INFO',
    'format': '%(asctime)s - %(levelname)s - %(message)s'
}

# Data Storage Configuration
STORAGE_CONFIG = {
    'data_dir_prefix': 'data_',  # 数据目录前缀
    'report_filename_prefix': 'daily_report_',  # 报告文件名前缀
    'enhanced_report_prefix': 'enhanced_report_',  # 增强报告前缀
    'json_filename_prefix': 'related_queries_'  # JSON文件名前缀
}

# Gemini API 配置
GEMINI_CONFIG = {
    'api_key': os.getenv('GEMINI_API_KEY', ''),
    'model': 'gemini-2.5-flash',         # 快速、低成本
    'max_tokens': 4096,
    'analysis_batch_size': 20,         # 每次 API 调用分析的关键词数量
}

# GPTs 比例过滤配置
GPTS_FILTER_CONFIG = {
    'baseline_keyword': 'gpts',
    'min_ratio': 0.3,
    'batch_size': 4,                    # 每次 interest_over_time 携带的候选词数（4 + baseline = 5，已是上限）
    'min_batch_delay_seconds': 40,      # gpts过滤批次间最小等待
    'max_batch_delay_seconds': 65,      # gpts过滤批次间最大等待
    'pre_filter_threshold': 0,          # 预筛阈值：0=不启用；设为如1000则只对>=1000%的词查gpts，减少批次数
}

# 关键词长度过滤配置（GPTs 阶段前，跳过不适合建站的长关键词）
KEYWORD_LENGTH_FILTER = {
    'enabled': True,
    'max_words': 4,           # 超过此词数的关键词跳过 GPTs 查询
    'max_chars': 30,          # 超过此字符数的关键词跳过 GPTs 查询
    'dedup_enabled': True,    # 启用去重：短词已覆盖的长词变体跳过 GPTs 查询
    'min_subset_words': 2,    # 去重时短词至少包含的词数（避免单词误匹配）
}

# 请求异常等待配置
RETRY_WAIT_CONFIG = {
    'rate_limit_wait_min_seconds': 300,     # 429/API quota 最小等待
    'rate_limit_wait_max_seconds': 360,     # 429/API quota 最大等待
    'empty_response_wait_min_seconds': 60,  # NoneType 最小等待
    'empty_response_wait_max_seconds': 120, # NoneType 最大等待
}

# 内容黑名单过滤配置（关键词匹配，不区分大小写）
CONTENT_FILTER_CONFIG = {
    # 赌博 / 灰黑产
    'gambling': [
        'casino', 'kasyno', 'สล็อต', 'สล็อต', 'gambling', 'betting', 'bookmaker',
        'poker', 'roulette', 'jackpot', 'baccarat', 'cruks', 'wagering',
        'sportsbetting', 'sportsbook',
    ],
    # 考试 / 试卷
    'exam': [
        'sample paper', 'question paper', 'exam paper', 'model paper',
        'past paper', 'mock exam', 'practice paper', 'test paper',
        'cbse', 'class 10', 'class 9', 'class 8', 'class 11', 'class 12',
    ],
}
