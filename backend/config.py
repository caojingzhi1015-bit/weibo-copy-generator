"""
配置管理模块
负责加载和管理 config.json 中的爬取配置、Cookie、关键词等。
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
LIBRARY_PATH = os.path.join(os.path.dirname(__file__), 'data', 'library.json')
SCRAPE_LOG_PATH = os.path.join(os.path.dirname(__file__), 'data', 'scrape_log.json')
CUSTOM_PATH = os.path.join(os.path.dirname(__file__), 'data', 'custom_phrases.json')

DEFAULT_CONFIG = {
    'cookies': '',
    'keywords': {
        'live': ['音乐直播', '超话空降', '直播ING'],
        'brand': ['品牌代言人', '代言官宣'],
        'show': ['巡演', '演唱会', '开票'],
        'daily': ['粉丝互动', '宠粉', '营业'],
        'hotspot': ['音乐联动', '破圈合作', '梦幻联动'],
    },
    'scrape_interval_hours': 24,
    'max_pages_per_keyword': 3,
    'min_engagement': 100,
    'min_followers': 500,
    'max_age_days': 7,
    'request_delay_seconds': 2,
    'user_agents': [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
    ],
}


def load_config():
    """加载配置文件，不存在则创建默认配置。"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # 合并默认值，确保所有字段都存在
        merged = {**DEFAULT_CONFIG, **config}
        merged['keywords'] = {**DEFAULT_CONFIG['keywords'], **config.get('keywords', {})}
        return merged

    # 创建默认配置文件
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """保存配置到文件。"""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_cookie_dict():
    """将 cookie 字符串解析为字典。"""
    config = load_config()
    cookie_str = config.get('cookies', '')
    if not cookie_str:
        return {}

    cookies = {}
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies


def is_cookie_configured():
    """检查 cookie 是否已配置。"""
    config = load_config()
    cookie_str = config.get('cookies', '').strip()
    # 检查是否包含实际的 cookie 值（不是占位符）
    if not cookie_str or cookie_str.startswith('SUB=_2A25...') or cookie_str == 'your_cookie_here':
        return False
    return len(cookie_str) > 20
