# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 Python 的 Google Trends 自动化监控工具，定期查询指定关键词的相关查询趋势数据，生成 CSV/JSON 报告，并通过邮件（Gmail SMTP）和/或微信发送通知。

## 环境搭建与运行

```bash
# 环境搭建
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 然后编辑填入真实凭据

# 测试模式（立即执行一次）
python trends_monitor.py --test

# 指定关键词测试
python trends_monitor.py --test --keywords "Python" "AI" "Game"

# 生产模式（每日定时守护进程）
python trends_monitor.py

# 微信联系人查询工具（交互式 CLI）
python wechat_utils.py
```

本项目无自动化测试套件（无 pytest/unittest）。`--test` 参数用于手动验证单次数据采集流程。

## 架构说明

四个 Python 模块各司其职，由 `trends_monitor.py` 统一调度：

```
trends_monitor.py  ──→  querytrends.py      （通过 trendspy 库调用 Google Trends API）
    （主调度器）    ──→  notification.py     （邮件 + 微信消息分发）
                         └──→ wechat_utils.py （微信登录/消息发送，基于 itchat-uos）
```

- **`config.py`** — 集中配置中心，从 `.env` 文件加载环境变量并设定默认值。所有可调参数均在此定义：关键词列表、时间范围、请求频率限制、定时任务、增长阈值、通知方式等。
- **`trends_monitor.py`** — 程序入口。支持 CLI 参数（`--test`、`--keywords`）。将关键词分批处理（默认 batch_size=5），使用指数退避重试机制（`@backoff.on_exception`）查询趋势数据，在 `data_YYYYMMDD/` 目录下生成每日 CSV 报告，并通过 `NotificationManager` 发送报告和高增长趋势告警。
- **`querytrends.py`** — 封装 `trendspy.Trends` 的 `related_queries()` 调用。内置 `RequestLimiter` 类（每分钟 30 次、每小时 200 次请求限制）。API 配额超限时无限重试（等待 5-6 分钟），NoneType 错误等待 1-2 分钟后重试。使用随机 User-Agent 轮换。
- **`notification.py`** — `NotificationManager` 支持三种通知模式：`email`、`wechat`、`both`。邮件使用 Gmail SMTP+TLS，支持 HTML 正文和 CSV 附件。微信消息按 2000 字符分段发送，自动将 HTML 转为纯文本，最多重试 3 次。
- **`wechat_utils.py`** — 单例模式 `WeChatManager`，线程安全登录，使用 `itchat.pkl` 缓存登录状态。支持通过备注名/昵称/微信号搜索联系人和群聊。也可作为独立的交互式联系人查询工具运行。

## 核心配置项（config.py）

- `NOTIFICATION_CONFIG['method']`：通知方式，可选 `'email'`、`'wechat'`、`'both'`
- `KEYWORDS`：待监控的关键词列表
- `TRENDS_CONFIG['timeframe']`：时间范围，支持 `'now 1-d'`、`'now 7-d'`、`'last-2-d'`、`'last-3-d'`，或日期范围如 `'2024-01-01 2024-01-31'`
- `TRENDS_CONFIG['geo']`：地区代码（如 `'US'`、`'CN'`），留空为全球
- `RATE_LIMIT_CONFIG`：控制重试次数、请求间隔（10-20 秒）、批次大小（5）、批次间隔（300 秒）
- `SCHEDULE_CONFIG`：每日执行的小时/分钟 + 可选随机延迟
- `MONITOR_CONFIG['rising_threshold']`：高增长告警阈值（默认 500）

## 数据输出

报告保存在 `data_YYYYMMDD/` 目录下：
- `daily_report_YYYYMMDD.csv` — 字段：keyword, related_keywords, value, type（rising/top）
- `related_queries_<关键词>_<时间戳>.json` — 每个关键词的原始查询数据

## 重要注意事项

- **请求频率控制至关重要** — Google Trends 有未公开的请求配额限制，切勿绕过 `RequestLimiter` 或移除 backoff 装饰器。
- `last-X-d` 时间范围格式是自定义的 — `trends_monitor.py` 中的 `get_date_range_timeframe()` 会将其转换为 `YYYY-MM-DD YYYY-MM-DD` 日期范围格式。
- 微信功能测试时应使用 `'filehelper'`（文件传输助手）作为接收者，避免打扰真实联系人。
- `wechat_utils.py` 在导入时会实例化全局 `WeChatManager`，如果通知方式包含微信，会触发登录状态检查。
