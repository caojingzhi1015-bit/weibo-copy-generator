"""
定时爬取调度模块
基于 APScheduler 实现话术库的定时自动更新。

调度规则：
  - 服务启动后立即执行一次爬取（如果 Cookie 已配置）
  - 按配置的间隔（默认24小时）定时执行
  - 记录每次爬取的日志
"""

import json
import os
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import load_config, is_cookie_configured, SCRAPE_LOG_PATH
from scraper import scrape_all
from classifier import build_library
from library_manager import update_library, save_library

logger = logging.getLogger('scheduler')

scheduler = BackgroundScheduler()


def scrape_job():
    """
    定时爬取任务：执行全量爬取 → 分类提取 → 更新话术库。
    """
    logger.info('=' * 50)
    logger.info('定时爬取任务开始...')

    if not is_cookie_configured():
        logger.warning('Cookie 未配置，跳过爬取任务。请在 config.json 中填写有效的微博 Cookie。')
        _log_scrape('skipped', 'Cookie 未配置')
        return

    try:
        # 1. 爬取
        config = load_config()
        logger.info('步骤 1/3: 开始爬取微博数据...')
        scraped_data = scrape_all(config)

        # 2. 分类提取
        logger.info('步骤 2/3: 分类提取话术元素...')
        library = build_library(scraped_data)

        # 3. 更新话术库
        logger.info('步骤 3/3: 更新本地话术库...')
        updated = update_library(library)
        save_library(updated)

        total = library['_meta']['total_posts']
        logger.info(f'爬取任务完成！共获取 {total} 条有效微博')
        _log_scrape('success', f'获取 {total} 条微博')

    except Exception as e:
        logger.error(f'爬取任务失败: {e}', exc_info=True)
        _log_scrape('failed', str(e))


def start_scheduler():
    """启动定时爬取调度器。"""
    config = load_config()
    interval_hours = config.get('scrape_interval_hours', 24)

    scheduler.add_job(
        scrape_job,
        trigger=IntervalTrigger(hours=interval_hours),
        id='weibo_scrape',
        name='微博话术库定时爬取',
        replace_existing=True,
        max_instances=1,  # 同一时间只允许一个实例运行
    )

    scheduler.start()
    logger.info(f'定时爬取调度器已启动，间隔: {interval_hours} 小时')

    # 立即执行一次（如果 Cookie 已配置）
    if is_cookie_configured():
        logger.info('检测到 Cookie 已配置，立即执行首次爬取...')
        # 在后台线程中执行，不阻塞启动
        import threading
        t = threading.Thread(target=scrape_job, daemon=True)
        t.start()
    else:
        logger.info('Cookie 未配置，跳过首次爬取。请编辑 backend/config.json 填写 Cookie。')


def stop_scheduler():
    """停止调度器。"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info('定时爬取调度器已停止')


def trigger_manual_scrape():
    """手动触发一次爬取。返回结果摘要。"""
    if not is_cookie_configured():
        return {'success': False, 'error': 'Cookie 未配置，请先在 config.json 中填写有效的微博 Cookie'}

    try:
        scraped_data = scrape_all()
        library = build_library(scraped_data)
        updated = update_library(library)
        save_library(updated)

        total = library['_meta']['total_posts']
        counts = library['_meta']['counts']

        _log_scrape('success', f'手动触发: 获取 {total} 条微博')

        return {
            'success': True,
            'total_posts': total,
            'counts': counts,
            'updated_at': library['_meta']['updated_at'],
        }

    except Exception as e:
        logger.error(f'手动爬取失败: {e}', exc_info=True)
        _log_scrape('failed', str(e))
        return {'success': False, 'error': str(e)}


def _log_scrape(status, message):
    """记录爬取日志。"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'status': status,
        'message': message,
    }

    logs = []
    if os.path.exists(SCRAPE_LOG_PATH):
        with open(SCRAPE_LOG_PATH, 'r', encoding='utf-8') as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []

    logs.insert(0, log_entry)
    # 保留最近 50 条日志
    logs = logs[:50]

    os.makedirs(os.path.dirname(SCRAPE_LOG_PATH), exist_ok=True)
    with open(SCRAPE_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
