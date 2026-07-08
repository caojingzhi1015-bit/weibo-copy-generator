"""
话术库管理模块
负责话术库的读取、更新、持久化存储，以及用户自定义话术的管理。
"""

import json
import os
import logging
from datetime import datetime

from config import LIBRARY_PATH, CUSTOM_PATH, load_config

logger = logging.getLogger('library_manager')


def load_library():
    """加载话术库。如果文件不存在，返回空库。"""
    if os.path.exists(LIBRARY_PATH):
        with open(LIBRARY_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return _empty_library()


def save_library(library):
    """保存话术库到文件。"""
    os.makedirs(os.path.dirname(LIBRARY_PATH), exist_ok=True)
    with open(LIBRARY_PATH, 'w', encoding='utf-8') as f:
        json.dump(library, f, ensure_ascii=False, indent=2)


def load_custom_phrases():
    """加载用户自定义话术。"""
    if os.path.exists(CUSTOM_PATH):
        with open(CUSTOM_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_custom_phrases(phrases):
    """保存用户自定义话术。"""
    os.makedirs(os.path.dirname(CUSTOM_PATH), exist_ok=True)
    with open(CUSTOM_PATH, 'w', encoding='utf-8') as f:
        json.dump(phrases, f, ensure_ascii=False, indent=2)


def add_custom_phrase(category, text):
    """
    添加用户自定义话术到对应类型。

    Args:
        category: 文案类型 (live/brand/show/daily/hotspot)
        text: 话术文本

    Returns:
        dict: 更新后的话术库
    """
    library = load_library()
    phrases = load_custom_phrases()

    if category not in phrases:
        phrases[category] = []

    phrases[category].append({
        'text': text,
        'added_at': datetime.now().isoformat(),
    })

    save_custom_phrases(phrases)

    # 同时更新话术库的 sample_texts
    if category in library and 'sample_texts' in library[category]:
        library[category]['sample_texts'].insert(0, text)
        library[category]['sample_texts'] = library[category]['sample_texts'][:30]
        save_library(library)

    return library


def update_library(new_data):
    """
    用新爬取的数据更新话术库。

    Args:
        new_data: 新的话术数据（来自 classifier.build_library）

    Returns:
        dict: 更新后的话术库
    """
    existing = load_library()
    custom = load_custom_phrases()

    # 合并数据：新数据覆盖旧数据，但保留最多数量的条目
    for category in ['live', 'brand', 'show', 'daily', 'hotspot']:
        if category not in new_data:
            continue

        new_cat = new_data[category]
        old_cat = existing.get(category, {})

        merged = {}
        for field in ['verbs', 'guides', 'atmospheres', 'emojis',
                       'fan_phrases', 'official_phrases', 'marketing_phrases', 'templates']:
            new_items = new_cat.get(field, [])
            old_items = old_cat.get(field, [])
            # 去重合并，保留最多 30 条
            combined = list(dict.fromkeys(new_items + old_items))
            merged[field] = combined[:30]

        # sample_texts 优先保留新的
        merged['sample_texts'] = new_cat.get('sample_texts', [])[:10]

        existing[category] = merged

    # 更新元数据
    existing['_meta'] = new_data.get('_meta', {
        'updated_at': datetime.now().isoformat(),
        'total_posts': 0,
        'counts': {c: 0 for c in ['live', 'brand', 'show', 'daily', 'hotspot']},
    })

    # 注入用户自定义话术到 sample_texts
    for category, items in custom.items():
        if category in existing and 'sample_texts' in existing[category]:
            for item in items[-5:]:  # 最近5条
                existing[category]['sample_texts'].insert(0, item['text'])
            existing[category]['sample_texts'] = existing[category]['sample_texts'][:15]

    save_library(existing)
    return existing


def get_library_preview(category, limit=10):
    """
    获取指定类型的话术库预览（最新文案样本）。

    Args:
        category: 文案类型
        limit: 返回条数

    Returns:
        list[str]: 文案样本列表
    """
    library = load_library()
    cat_data = library.get(category, {})
    return cat_data.get('sample_texts', [])[:limit]


def get_library_status():
    """
    获取话术库状态信息。

    Returns:
        dict: { updated_at, counts: { category: count }, total_posts }
    """
    library = load_library()
    meta = library.get('_meta', {})
    return {
        'updated_at': meta.get('updated_at', '从未更新'),
        'counts': meta.get('counts', {
            'live': 0, 'brand': 0, 'show': 0, 'daily': 0, 'hotspot': 0
        }),
        'total_posts': meta.get('total_posts', 0),
    }


def _empty_library():
    """返回空话术库结构。"""
    empty = {}
    for cat in ['live', 'brand', 'show', 'daily', 'hotspot']:
        empty[cat] = {
            'verbs': [], 'guides': [], 'atmospheres': [], 'emojis': [],
            'fan_phrases': [], 'official_phrases': [], 'marketing_phrases': [],
            'templates': [], 'sample_texts': [],
        }
    empty['_meta'] = {
        'updated_at': '从未更新',
        'total_posts': 0,
        'counts': {'live': 0, 'brand': 0, 'show': 0, 'daily': 0, 'hotspot': 0},
    }
    return empty
