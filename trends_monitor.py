import os
import pandas as pd
from datetime import datetime, timedelta
import schedule
import time
import random
from querytrends import batch_get_queries, save_related_queries, RequestLimiter, get_gpts_ratio_batch
import json
import logging
import backoff
import argparse
from config import (
    EMAIL_CONFIG,
    RATE_LIMIT_CONFIG,
    SCHEDULE_CONFIG,
    MONITOR_CONFIG,
    LOGGING_CONFIG,
    STORAGE_CONFIG,
    TRENDS_CONFIG,
    NOTIFICATION_CONFIG,
    GPTS_FILTER_CONFIG,
    GEMINI_CONFIG,
    CONTENT_FILTER_CONFIG,
)
from notification import NotificationManager
from keyword_loader import load_root_keywords
from ai_analyzer import analyze_keywords_batch

# Configure logging（必须在 load_root_keywords 之前，保证日志写入文件）
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG['level']),
    format=LOGGING_CONFIG['format'],
    handlers=[
        logging.FileHandler(LOGGING_CONFIG['log_file']),
        logging.StreamHandler()
    ]
)

# 从 markdown 词根文件动态加载关键词
KEYWORDS = load_root_keywords()

# 创建请求限制器实例
request_limiter = RequestLimiter()

# 创建通知管理器实例
notification_manager = NotificationManager()

def send_email(subject, body, attachments=None):
    """Send email with optional attachments"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['recipient_email']
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html'))

        if attachments:
            for filepath in attachments:
                with open(filepath, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=os.path.basename(filepath))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(filepath)}"'
                msg.attach(part)

        # Gmail使用SMTP然后升级到TLS
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.ehlo()  # 可以帮助识别连接问题
            server.starttls()  # 升级到TLS连接
            server.ehlo()  # 重新识别
            logging.info("Attempting to login to Gmail...")
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            logging.info("Login successful, sending email...")
            server.send_message(msg)
            
        logging.info(f"Email sent successfully: {subject}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        logging.error(f"Email configuration used: server={EMAIL_CONFIG['smtp_server']}, port={EMAIL_CONFIG['smtp_port']}")
        # 不要立即抛出异常，让程序继续运行
        return False

def create_daily_directory():
    """Create a directory for today's data"""
    today = datetime.now().strftime('%Y%m%d')
    directory = f"{STORAGE_CONFIG['data_dir_prefix']}{today}"
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory

def check_rising_trends(data, keyword, threshold=MONITOR_CONFIG['rising_threshold']):
    """Check if any rising trends exceed the threshold"""
    if not data or 'rising' not in data or data['rising'] is None:
        return []
    
    rising_trends = []
    df = data['rising']
    if isinstance(df, pd.DataFrame):
        for _, row in df.iterrows():
            if row['value'] > threshold:
                rising_trends.append((row['query'], row['value']))
    return rising_trends

def generate_daily_report(results, directory):
    """Generate a daily report in CSV format"""
    report_data = []
    
    for keyword, data in results.items():
        if data and isinstance(data.get('rising'), pd.DataFrame):
            rising_df = data['rising']
            for _, row in rising_df.iterrows():
                report_data.append({
                    'keyword': keyword,
                    'related_keywords': row['query'],
                    'value': row['value'],
                    'type': 'rising'
                })
        
        if data and isinstance(data.get('top'), pd.DataFrame):
            top_df = data['top']
            for _, row in top_df.iterrows():
                report_data.append({
                    'keyword': keyword,
                    'related_keywords': row['query'],
                    'value': row['value'],
                    'type': 'top'
                })
    
    if report_data:
        df = pd.DataFrame(report_data)
        filename = f"{STORAGE_CONFIG['report_filename_prefix']}{datetime.now().strftime('%Y%m%d')}.csv"
        report_file = os.path.join(directory, filename)
        df.to_csv(report_file, index=False)
        return report_file
    return None

def get_date_range_timeframe(timeframe):
    """Convert special timeframe formats to date range format
    
    Args:
        timeframe (str): Timeframe string like 'last-2-d' or 'last-3-d'
        
    Returns:
        str: Date range format string like '2024-01-01 2024-01-31'
    """
    if not timeframe.startswith('last-'):
        return timeframe
        
    try:
        # 解析天数
        days = int(timeframe.split('-')[1])
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        # 格式化日期字符串
        return f"{start_date.strftime('%Y-%m-%d')} {end_date.strftime('%Y-%m-%d')}"
    except (ValueError, IndexError):
        logging.warning(f"Invalid timeframe format: {timeframe}, falling back to 'now 1-d'")
        return 'now 1-d'

def process_keywords_batch(keywords_batch, directory, all_results, high_rising_trends, timeframe):
    """处理一批关键词"""
    try:
        logging.info(f"Processing batch of {len(keywords_batch)} keywords")
        logging.info(f"Query parameters: timeframe={timeframe}, geo={TRENDS_CONFIG['geo'] or 'Global'}")
        
        # 使用传入的 timeframe 参数
        results = get_trends_with_retry(keywords_batch, timeframe)
        
        for keyword, data in results.items():
            if data:
                filename = save_related_queries(keyword, data)
                if filename:
                    os.rename(filename, os.path.join(directory, filename))
                
                rising_trends = check_rising_trends(data, keyword)
                if rising_trends:
                    high_rising_trends.extend([(keyword, related_keywords, value) 
                                             for related_keywords, value in rising_trends])
                
                all_results[keyword] = data
        
        return True
    except Exception as e:
        logging.error(f"Error processing batch: {str(e)}")
        return False

@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=RATE_LIMIT_CONFIG['max_retries'],
    jitter=backoff.full_jitter
)
def get_trends_with_retry(keywords_batch, timeframe):
    """使用重试机制获取趋势数据"""
    return batch_get_queries(
        keywords_batch,
        timeframe=timeframe,  # 使用传入的 timeframe
        geo=TRENDS_CONFIG['geo'],
        delay_between_queries=random.uniform(
            RATE_LIMIT_CONFIG['min_delay_between_queries'],
            RATE_LIMIT_CONFIG['max_delay_between_queries']
        )
    )

def filter_by_gpts_ratio(high_rising_trends, timeframe):
    """Stage 4: 用 gpts 搜索量比例过滤 rising 关键词"""
    rising_kw_list = list({kw for _, kw, _ in high_rising_trends})  # 去重
    ratio_map = get_gpts_ratio_batch(
        rising_kw_list,
        geo=TRENDS_CONFIG['geo'],
        timeframe=timeframe
    )
    filtered = []
    for root_kw, rising_kw, growth_val in high_rising_trends:
        ratio = ratio_map.get(rising_kw, 0.0)
        if ratio >= GPTS_FILTER_CONFIG['min_ratio']:
            filtered.append((root_kw, rising_kw, growth_val, ratio))
        else:
            logging.info(f"Filtered: '{rising_kw}' ratio={ratio:.3f} < {GPTS_FILTER_CONFIG['min_ratio']}")
    return filtered


def _get_blacklist_category(keyword):
    """检查关键词是否命中黑名单，返回类别名或 None。"""
    kw_lower = keyword.lower()
    for category, patterns in CONTENT_FILTER_CONFIG.items():
        if any(p in kw_lower for p in patterns):
            return category
    return None


def filter_blacklist_rising(high_rising_trends):
    """
    Stage 3.5: 在 gpts ratio 计算前提前过滤黑名单关键词。
    避免对赌博/考试类词进行不必要的 gpts API 调用。
    输入: [(root_kw, rising_kw, value), ...]
    """
    result = []
    for root_kw, rising_kw, value in high_rising_trends:
        category = _get_blacklist_category(rising_kw)
        if category:
            logging.info(f"Blacklist [{category}] pre-filtered: '{rising_kw}'")
        else:
            result.append((root_kw, rising_kw, value))
    return result


def filter_blacklist_content(enriched):
    """
    Stage 5.5: 黑名单内容过滤（AI分析后的兜底过滤）。
    过滤掉赌博/灰黑产、考试试卷等与AI工具站无关的内容。
    匹配规则：rising_keyword 转小写后包含任一黑名单词组即过滤。
    """
    result = []
    for row in enriched:
        category = _get_blacklist_category(row['rising_keyword'])
        if category:
            logging.info(f"Blacklist [{category}] filtered: '{row['rising_keyword']}'")
        else:
            result.append(row)
    return result


def generate_enhanced_report(enriched, directory):
    """
    Stage 6: 生成增强版报告。
    - enhanced_report_YYYYMMDD.csv（6列）
    - enhanced_report_YYYYMMDD.md（Markdown 表格，按 site_type 分组）
    返回 (csv_path, md_path) 或 (None, None)。
    """
    if not enriched:
        logging.info("No enriched data to write enhanced report")
        return None, None

    today = datetime.now().strftime('%Y%m%d')
    prefix = STORAGE_CONFIG['enhanced_report_prefix']

    # --- CSV ---
    csv_filename = f"{prefix}{today}.csv"
    csv_path = os.path.join(directory, csv_filename)
    df = pd.DataFrame(enriched, columns=[
        'root_keyword', 'rising_keyword', 'growth_value',
        'gpts_ratio', 'search_intent', 'site_type'
    ])
    df.to_csv(csv_path, index=False)
    logging.info(f"Enhanced CSV report saved: {csv_path}")

    # --- Markdown ---
    md_filename = f"{prefix}{today}.md"
    md_path = os.path.join(directory, md_filename)

    date_str = datetime.now().strftime('%Y-%m-%d')
    timeframe_display = TRENDS_CONFIG['timeframe']
    total_roots = len(KEYWORDS)
    rising_threshold = MONITOR_CONFIG['rising_threshold']
    min_ratio = GPTS_FILTER_CONFIG['min_ratio']

    lines = [
        f"# 每日趋势增强报告 - {date_str}",
        "",
        f"> 监控周期: {timeframe_display} | 词根数: {total_roots} | Rising过滤: >{rising_threshold}% | GPTs比例过滤: ≥{min_ratio}",
        "",
    ]

    site_types = ["工具站", "内容站", "游戏站", "目录站"]
    for st in site_types:
        group = [row for row in enriched if row.get('site_type') == st]
        if not group:
            continue
        lines.append(f"## {st}机会")
        lines.append("")
        lines.append("| 词根 | Rising关键词 | 增长率 | GPTs比值 | 搜索意图 |")
        lines.append("|------|------------|--------|----------|---------|")
        for row in group:
            gv = row['growth_value']
            growth_display = f"{gv}%" if isinstance(gv, (int, float)) else str(gv)
            lines.append(
                f"| {row['root_keyword']} | {row['rising_keyword']} | "
                f"{growth_display} | {row['gpts_ratio']:.4f} | {row['search_intent']} |"
            )
        lines.append("")

    # 未分类（site_type 不在上述四类中）
    others = [row for row in enriched if row.get('site_type') not in site_types]
    if others:
        lines.append("## 其他")
        lines.append("")
        lines.append("| 词根 | Rising关键词 | 增长率 | GPTs比值 | 搜索意图 | 类型 |")
        lines.append("|------|------------|--------|----------|---------|------|")
        for row in others:
            gv = row['growth_value']
            growth_display = f"{gv}%" if isinstance(gv, (int, float)) else str(gv)
            lines.append(
                f"| {row['root_keyword']} | {row['rising_keyword']} | "
                f"{growth_display} | {row['gpts_ratio']:.4f} | {row['search_intent']} | {row['site_type']} |"
            )
        lines.append("")

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    logging.info(f"Enhanced Markdown report saved: {md_path}")

    return csv_path, md_path


def process_trends():
    """Main function to process trends data"""
    try:
        logging.info("Starting daily trends processing")
        
        # 处理特殊的 timeframe 格式
        timeframe = TRENDS_CONFIG['timeframe']
        actual_timeframe = get_date_range_timeframe(timeframe)
        
        logging.info(f"Using configuration: timeframe={actual_timeframe}, geo={TRENDS_CONFIG['geo'] or 'Global'}")
        directory = create_daily_directory()
        
        all_results = {}
        high_rising_trends = []
        
        # 将关键词分批处理，使用实际的 timeframe
        for i in range(0, len(KEYWORDS), RATE_LIMIT_CONFIG['batch_size']):
            keywords_batch = KEYWORDS[i:i + RATE_LIMIT_CONFIG['batch_size']]
            # 传递实际的 timeframe 到查询函数
            success = process_keywords_batch(
                keywords_batch, 
                directory, 
                all_results, 
                high_rising_trends,
                actual_timeframe
            )
            
            if not success:
                logging.error(f"Failed to process batch starting with keyword: {keywords_batch[0]}")
                continue
            
            # 如果不是最后一批，等待一段时间再处理下一批
            if i + RATE_LIMIT_CONFIG['batch_size'] < len(KEYWORDS):
                wait_time = RATE_LIMIT_CONFIG['batch_interval'] + random.uniform(
                    0,
                    RATE_LIMIT_CONFIG.get('batch_interval_jitter_max', 60)
                )
                logging.info(f"Waiting {wait_time:.1f} seconds before processing next batch...")
                time.sleep(wait_time)

        # Stage 3.5: 黑名单预过滤（在 gpts ratio 之前，节省 API 调用）
        if high_rising_trends:
            before_count = len(high_rising_trends)
            high_rising_trends = filter_blacklist_rising(high_rising_trends)
            logging.info(f"After blacklist pre-filter: {len(high_rising_trends)}/{before_count} rising trends remain")

        # Stage 4: gpts 比例过滤
        if high_rising_trends:
            logging.info(f"Stage 4: filtering {len(high_rising_trends)} rising trends by gpts ratio...")
            gpts_filtered = filter_by_gpts_ratio(high_rising_trends, actual_timeframe)
            logging.info(f"After gpts filter: {len(gpts_filtered)}/{len(high_rising_trends)} keywords remain")
        else:
            gpts_filtered = []

        # Stage 5: Gemini AI 分析
        if gpts_filtered:
            logging.info(f"Stage 5: running Gemini analysis on {len(gpts_filtered)} keywords...")
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
        else:
            enriched = []

        # Stage 5.5: 黑名单内容过滤（赌博/灰黑产、考试试卷）
        if enriched:
            before_count = len(enriched)
            enriched = filter_blacklist_content(enriched)
            logging.info(f"After blacklist filter: {len(enriched)}/{before_count} keywords remain")

        # Stage 6: 生成报告（保留原有 legacy，新增 enhanced）
        legacy_report = generate_daily_report(all_results, directory)
        enhanced_csv, enhanced_md = generate_enhanced_report(enriched, directory)

        # Stage 7: 通知（附件包含两种报告）
        attachments = [f for f in [legacy_report, enhanced_csv, enhanced_md] if f]

        if legacy_report:
            report_body = """
            <h2>Daily Trends Report</h2>
            <p>Please find attached the daily trends report.</p>
            <p>Query Parameters:</p>
            <ul>
            <li>Time Range: {}</li>
            <li>Region: {}</li>
            </ul>
            <p>Summary:</p>
            <ul>
            <li>Total keywords processed: {}</li>
            <li>Successful queries: {}</li>
            <li>Failed queries: {}</li>
            <li>Rising trends after gpts filter: {}</li>
            </ul>
            """.format(
                TRENDS_CONFIG['timeframe'],
                TRENDS_CONFIG['geo'] or 'Global',
                len(KEYWORDS),
                len(all_results),
                len(KEYWORDS) - len(all_results),
                len(enriched)
            )
            if not notification_manager.send_notification(
                subject=f"Daily Trends Report - {datetime.now().strftime('%Y-%m-%d')}",
                body=report_body,
                attachments=attachments
            ):
                logging.warning("Failed to send daily report, but data collection completed")

        # Send alerts for high rising trends (original alert logic kept for backward compat)
        if high_rising_trends:
            # 将高趋势分批处理，每批最多10个趋势
            batch_size = 10
            for i in range(0, len(high_rising_trends), batch_size):
                batch_trends = high_rising_trends[i:i + batch_size]
                batch_number = i // batch_size + 1
                total_batches = (len(high_rising_trends) + batch_size - 1) // batch_size

                alert_body = f"""
                <h2>📊 High Rising Trends Alert</h2>
                <hr>
                <h3>📌 Query Parameters:</h3>
                <ul>
                    <li>🕒 Time Range: {TRENDS_CONFIG['timeframe']}</li>
                    <li>🌍 Region: {TRENDS_CONFIG['geo'] or 'Global'}</li>
                </ul>
                <h3>📈 Significant Growth Trends:</h3>
                <table border="1" cellpadding="5" style="border-collapse: collapse;">
                    <tr>
                        <th>🔍 Base Keyword</th>
                        <th>🔗 Related Query</th>
                        <th>📈 Growth</th>
                    </tr>
                """

                for keyword, related_keywords, value in batch_trends:
                    alert_body += f"""
                    <tr>
                        <td><strong>🎯 {keyword}</strong></td>
                        <td>➡️ {related_keywords}</td>
                        <td align="right" style="color: #28a745;">⬆️ {value}%</td>
                    </tr>
                    """

                alert_body += "</table>"

                if batch_number < total_batches:
                    alert_body += f"<p><i>This is batch {batch_number} of {total_batches}. More results will follow.</i></p>"

                if not notification_manager.send_notification(
                    subject=f"📊 Rising Trends Alert ({batch_number}/{total_batches})",
                    body=alert_body
                ):
                    logging.warning(f"Failed to send alert notification for batch {batch_number}, but data collection completed")

                # 添加短暂延迟，避免消息发送过快
                time.sleep(2)
        
        logging.info("Daily trends processing completed successfully")
        return True
    except Exception as e:
        logging.error(f"Error in trends processing: {str(e)}")
        notification_manager.send_notification(
            subject="❌ Error in Trends Processing",
            body=f"<p>An error occurred during trends processing:</p><pre>{str(e)}</pre>"
        )
        return False

def run_scheduler():
    """Run the scheduler"""
    # 从配置中获取小时和分钟
    schedule_hour = SCHEDULE_CONFIG['hour']
    schedule_minute = SCHEDULE_CONFIG.get('minute', 0)  # 默认为0分钟
    
    # 添加随机延迟（如果配置了的话）
    if SCHEDULE_CONFIG.get('random_delay_minutes', 0) > 0:
        random_minutes = random.randint(0, SCHEDULE_CONFIG['random_delay_minutes'])
        schedule_minute = (schedule_minute + random_minutes) % 60
        # 如果分钟数超过59，需要调整小时数
        schedule_hour = (schedule_hour + (schedule_minute + random_minutes) // 60) % 24
    
    schedule_time = f"{schedule_hour:02d}:{schedule_minute:02d}"
    
    schedule.every().day.at(schedule_time).do(process_trends)
    
    logging.info(f"Scheduler started. Will run daily at {schedule_time}")
    
    # 如果启动时间接近计划执行时间，等待到下一天
    now = datetime.now()
    scheduled_time = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
    
    if now >= scheduled_time:
        logging.info("Current time is past scheduled time, waiting for tomorrow")
        next_run = scheduled_time + timedelta(days=1)
        time.sleep((next_run - now).total_seconds())
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='Google Trends Monitor')
    parser.add_argument('--test', action='store_true', 
                      help='立即运行一次数据收集，而不是等待计划时间')
    parser.add_argument('--keywords', nargs='+',
                      help='测试时要查询的关键词列表，如果不指定则使用配置文件中的关键词')
    args = parser.parse_args()

    # 检查邮件配置
    if not all([
        EMAIL_CONFIG['sender_email'],
        EMAIL_CONFIG['sender_password'],
        EMAIL_CONFIG['recipient_email']
    ]):
        logging.error("Please configure email settings in config.py before running")
        exit(1)
    
    # 如果是测试模式
    if args.test:
        logging.info("Running in test mode...")
        if args.keywords:
            # 临时替换配置文件中的关键词
            KEYWORDS = args.keywords
            logging.info(f"Using test keywords: {KEYWORDS}")
        process_trends()
    else:
        # 正常的计划任务模式
        run_scheduler() 
