"""
内容分类与话术提取模块
对爬取的微博内容进行分析，提取：
  - 高频动词
  - 引导动作短语
  - 氛围渲染词
  - 句式模板
  - 粉丝向/官宣向/营销向话术片段
  - Emoji 使用模式
"""

import re
import json
from collections import Counter
from bs4 import BeautifulSoup


# ============================================================
# 预定义词库（用于匹配和提取）
# ============================================================

# 高频动词候选（按类型）
VERB_CANDIDATES = {
    'live':    ['直击', '空降', '蹲守', '速来', '锁定', '集结', '奔赴', '解锁',
                '围观', '拿下', '霸屏', '刷屏', '应援', '打call', '见证', '开启',
                '引爆', '沉浸', '来袭', '上线', '放送', '连线', '互动'],
    'brand':   ['解锁', '拿下', '官宣', '携手', '共赴', '宣告', '集结', '见证',
                '刷新', '开启', '诠释', '定义', '引领', '加持', '共鸣', '演绎',
                '升级', '焕新', '揭晓', '官泄'],
    'show':    ['开票', '抢票', '奔赴', '集结', '锁定', '共赴', '直击', '见证',
                '解锁', '霸屏', '刷屏', '沉浸', '燃爆', '开启', '限定', '启程',
                '巡演', '来袭', '引爆', '嗨翻'],
    'daily':   ['分享', '解锁', '掉落', '更新', '营业', '上线', '空降', '翻牌',
                '宠粉', '互动', '放送', '官宣', '预告', '集结', '闪现', '冒泡'],
    'hotspot': ['联动', '破圈', '集结', '共赴', '解锁', '直击', '见证', '霸屏',
                '刷屏', '引爆', '空降', '奔赴', '点燃', '开启', '跨界', '碰撞'],
}

# 引导动作候选
GUIDE_CANDIDATES = {
    'live':    ['速来直播间', '点击锁定席位', '直击精彩现场', '马上空降',
                '不见不散', '戳链接进入', '速来蹲守', '一键预约', '快来围观',
                '赶紧来蹲', '快来互动', '一起见证'],
    'brand':   ['同款安排上', '点击解锁详情', '速来get同款', '关注解锁更多',
                '一键加购', '戳链接了解', '马上安排', '速来解锁', '快来Pick'],
    'show':    ['速来抢票', '点击购票', '现场见', '不见不散', '一键抢票',
                '戳链接购票', '锁定席位', '共赴现场', '手慢无', '速来约'],
    'daily':   ['来看看', '点击查收', '关注不迷路', '一起解锁', '速来互动',
                '戳链接查看', '不见不散', '来聊天', '点个赞再走'],
    'hotspot': ['速来围观', '点击了解', '不容错过', '一起见证', '戳链接参与',
                '速来解锁', '一键三连', '来吃瓜', '速来关注'],
}

# 氛围词候选
ATMOSPHERE_CANDIDATES = {
    'live':    ['高能', '燃炸', '实时', '限定', '沉浸', '惊喜', '精彩', '高燃',
                '炸裂', '温暖', '治愈', '爆笑', '走心', '上头', '封神'],
    'brand':   ['清爽', '元气', '高能', '契合', '惊喜', '限定', '质感', '清新',
                '霸气', '温暖', '心动', '绝美', '惊艳', '有范', '高级'],
    'show':    ['限定', '沉浸', '燃炸', '视听盛宴', '高能', '惊喜', '震撼',
                '精彩', '温暖', '狂欢', '炸场', '封神', '难忘', '绝美'],
    'daily':   ['治愈', '温暖', '惊喜', '日常', '限定', '可爱', '高能', '欢乐',
                '走心', '清新', '元气', '甜美', '帅气'],
    'hotspot': ['破圈', '高能', '限定', '惊喜', '重磅', '燃炸', '炸裂', '顶流',
                '出圈', '神仙', '梦幻', '史诗', '炸场'],
}


def extract_phrases_from_posts(category, posts):
    """
    从爬取的微博数据中提取高频话术元素。

    Args:
        category: 文案类型 (live/brand/show/daily/hotspot)
        posts: 该类型的微博列表

    Returns:
        dict: 提取到的话术元素
    """
    if not posts:
        return _get_default_phrases(category)

    all_text = ' '.join(p['text'] for p in posts)

    # 提取高频动词
    verbs = _extract_by_candidates(all_text, VERB_CANDIDATES.get(category, []))

    # 提取引导短语
    guides = _extract_by_candidates(all_text, GUIDE_CANDIDATES.get(category, []))

    # 提取氛围词
    atmospheres = _extract_by_candidates(all_text, ATMOSPHERE_CANDIDATES.get(category, []))

    # 提取 Emoji
    emojis = _extract_emojis(all_text)

    # 提取粉丝向/官宣向/营销向话术片段
    fan_phrases = _extract_fan_phrases(posts)
    official_phrases = _extract_official_phrases(posts)
    marketing_phrases = _extract_marketing_phrases(posts)

    # 提取句式模板
    templates = _extract_templates(posts)

    return {
        'verbs': verbs if verbs else VERB_CANDIDATES.get(category, [])[:15],
        'guides': guides if guides else GUIDE_CANDIDATES.get(category, [])[:12],
        'atmospheres': atmospheres if atmospheres else ATMOSPHERE_CANDIDATES.get(category, [])[:12],
        'emojis': emojis if emojis else ['✨', '🎵', '🔥'],
        'fan_phrases': fan_phrases,
        'official_phrases': official_phrases,
        'marketing_phrases': marketing_phrases,
        'templates': templates,
        'sample_texts': [p['text'][:100] for p in posts[:10]],
    }


def _extract_by_candidates(text, candidates):
    """从文本中匹配候选词，按出现频率排序返回出现过的词。"""
    found = Counter()
    for candidate in candidates:
        count = text.count(candidate)
        if count > 0:
            found[candidate] = count
    # 返回出现过的词，按频率排序
    return [word for word, _ in found.most_common(20)]


def _extract_emojis(text):
    """提取文本中的 Emoji 表情。"""
    emoji_pattern = re.compile(
        '[☀-➿⭐❤︀-️'
        '\U0001F300-\U0001F64F'
        '\U0001F680-\U0001F6FF'
        '\U0001F900-\U0001F9FF'
        '\U0001F1E0-\U0001F1FF'
        '‍⃣️]+',
        re.UNICODE,
    )
    emojis = emoji_pattern.findall(text)
    counter = Counter(emojis)
    # 返回前 10 个最常见的 emoji
    return [e for e, _ in counter.most_common(10)]


def _extract_fan_phrases(posts):
    """提取粉丝向话术片段。"""
    fan_patterns = [
        r'谁还没[^\s，。！？]{2,6}',
        r'太[^\s，。！？]{1,4}了',
        r'[^\s，。！？]{2,4}狂喜',
        r'不允许[^\s，。！？]{2,8}',
        r'快冲',
        r'狠狠[^\s，。！？]{2,4}了',
        r'谁能不[^\s，。！？]{1,4}',
        r'真的[^\s，。！？]{2,6}',
        r'终于[^\s，。！？]{2,8}了',
        r'谁懂啊',
        r'好会啊',
        r'被[^\s，。！？]{2,6}拿捏了',
        r'双向奔赴',
        r'这也太[^\s，。！？]{2,4}了',
        r'粉丝[^\s，。！？]{2,6}',
    ]
    return _match_patterns(posts, fan_patterns)


def _extract_official_phrases(posts):
    """提取官宣向话术片段。"""
    official_patterns = [
        r'正式官宣',
        r'重磅[^\s，。！？]{2,4}',
        r'[^\s，。！？]{2,4}即将开启',
        r'邀[^\s，。！？]{2,6}见证',
        r'锁定[^\s，。！？]{2,6}',
        r'官宣[^\s，。！？]{2,6}',
        r'全新[^\s，。！？]{2,4}',
        r'共同见证[^\s，。！？]{2,6}',
        r'诚邀[^\s，。！？]{2,6}',
        r'正式启动',
        r'隆重[^\s，。！？]{2,4}',
    ]
    return _match_patterns(posts, official_patterns)


def _extract_marketing_phrases(posts):
    """提取营销向话术片段。"""
    marketing_patterns = [
        r'速报[！!]?',
        r'前方高能',
        r'别怪[^\s，。！？]{2,6}',
        r'懂的都懂',
        r'来都来了',
        r'手慢无',
        r'还在等什么',
        r'再不上车[^\s，。！？]{2,6}',
        r'别犹豫[^\s，。！？]{2,4}',
        r'这是什么[^\s，。！？]{2,6}',
        r'来真的[？?]',
        r'搞事情[^\s，。！？]{2,4}',
        r'闭眼入',
        r'[^\s，。！？]{2,4}预警',
        r'[^\s，。！？]{2,6}爆款',
    ]
    return _match_patterns(posts, marketing_patterns)


def _match_patterns(posts, patterns):
    """从微博列表中匹配指定模式，提取匹配到的短语。"""
    found = Counter()
    for post in posts:
        text = post['text']
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                if isinstance(m, str):
                    found[m] += 1
                elif isinstance(m, tuple):
                    for sub in m:
                        if sub:
                            found[sub] += 1

    # 返回 top 15
    return [phrase for phrase, _ in found.most_common(15)]


def _extract_templates(posts):
    """从微博文案中提取句式模板。

    通过分析文案结构：@账号位置、#话题#位置、动词位置、emoji位置，构建通用模板。
    """
    templates = set()

    for post in posts[:30]:
        text = post['text']

        # 生成抽象模板
        template = text

        # 替换 @账号 为占位符
        template = re.sub(r'@\S+', '{S}', template)

        # 替换 #话题# 为占位符
        template = re.sub(r'#[^#]+#', '{H}', template)

        # 替换链接为占位符
        template = re.sub(r'https?://\S+', '{L}', template)

        # 替换 Emoji 为占位符
        emoji_pattern = re.compile(
            '[☀-➿⭐❤︀-️'
            '\U0001F300-\U0001F64F'
            '\U0001F680-\U0001F6FF'
            '\U0001F900-\U0001F9FF'
            '\U0001F1E0-\U0001F1FF'
            '‍⃣️]+',
            re.UNICODE,
        )
        # 只替换第一个 emoji，保留模板信息
        template = emoji_pattern.sub('{M}', template, count=1)
        template = emoji_pattern.sub('', template)  # 去掉多余的

        # 清理多余空白
        template = re.sub(r'\s+', ' ', template).strip()

        # 过滤太短或太长的模板
        if 10 <= len(template) <= 120:
            templates.add(template)

    return list(templates)[:20]


def _get_default_phrases(category):
    """当没有爬取数据时，返回默认话术数据。"""
    defaults = {
        'verbs': VERB_CANDIDATES.get(category, [])[:15],
        'guides': GUIDE_CANDIDATES.get(category, [])[:12],
        'atmospheres': ATMOSPHERE_CANDIDATES.get(category, [])[:12],
        'emojis': ['✨', '🎵', '🔥', '💫', '🎙️'],
        'fan_phrases': [],
        'official_phrases': [],
        'marketing_phrases': [],
        'templates': [],
        'sample_texts': [],
    }
    return defaults


def build_library(scraped_data):
    """
    将爬取数据构建为完整的话术库。

    Args:
        scraped_data: scrape_all() 返回的按类型分类的微博数据

    Returns:
        dict: 完整话术库 { type: { verbs, guides, atmospheres, ... } }
    """
    library = {}
    for category in ['live', 'brand', 'show', 'daily', 'hotspot']:
        posts = scraped_data.get(category, [])
        library[category] = extract_phrases_from_posts(category, posts)

    # 添加元数据
    library['_meta'] = {
        'updated_at': __import__('datetime').datetime.now().isoformat(),
        'total_posts': sum(len(scraped_data.get(c, [])) for c in
                          ['live', 'brand', 'show', 'daily', 'hotspot']),
        'counts': {c: len(scraped_data.get(c, []))
                   for c in ['live', 'brand', 'show', 'daily', 'hotspot']},
    }

    return library
