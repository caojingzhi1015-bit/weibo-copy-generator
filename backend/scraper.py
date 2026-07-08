"""
微博爬取模块
基于 weiboSpider (https://github.com/dataabc/weiboSpider) 爬取指定大营销号的微博数据。

工作流程:
  1. 读取 config.json 中配置的 user_id_list（音乐演出行业营销号）
  2. 通过 weibo_spider 库爬取每个账号近7天的微博
  3. 后处理过滤：互动量≥100、粉丝≥500、过滤广告/敏感内容
  4. 将结果交给 classifier 提取话术元素

也可作为独立脚本运行:
    python scraper.py
"""

import json
import os
import sys
import logging
import tempfile
import subprocess
import re
import html as html_mod
from datetime import datetime, timedelta
from collections import Counter

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from config import load_config, save_config, is_cookie_configured

logger = logging.getLogger('weibo_scraper')

# ============================================================
# 知名音乐演出行业微博营销号 UID 列表（用户可根据需要增减）
# ============================================================
# 获取方式：打开微博用户主页，URL 中的数字即为 user_id
# 如 https://weibo.com/u/1669879400 → user_id = 1669879400

DEFAULT_MUSIC_MARKETING_UIDS = [
    # ---- 音乐演出官方/资讯 ----
    '1721030997',  # 微博音乐
    '1340425601',  # 新浪音乐
    '1749127163',  # 音乐圈
    # ---- 票务平台 ----
    '1644395354',  # 大麦网
    '1782906052',  # 猫眼演出
    # ---- 演出主办方(示例，请替换为实际UID) ----
    # 'XXXXXXXXXX',  # 摩登天空
    # 'XXXXXXXXXX',  # 太合音乐
    # ---- 音乐节/演唱会(示例) ----
    # 'XXXXXXXXXX',  # 草莓音乐节
    # ---- 娱乐资讯/营销号(示例) ----
    # 'XXXXXXXXXX',  # 新浪娱乐
    # 'XXXXXXXXXX',  # 圈内老鬼
]

# 也可通过 user_id_list.txt 文件指定（每行一个UID）
USER_ID_LIST_FILE = os.path.join(os.path.dirname(__file__), 'user_id_list.txt')

# 广告/硬广过滤关键词
AD_FILTER_KEYWORDS = [
    '抽奖', '转发抽', '福利抽', '下单', '领券', '满减', '优惠券',
    '购买链接', '戳链接', '限时折扣', '秒杀', '拼团',
    '立即购买', '去购买', '购课', '报名链接', '注册即送',
]

# 敏感/违规过滤关键词
SENSITIVE_KEYWORDS = ['敏感', '违规']


def get_user_id_list(config=None):
    """
    获取要爬取的用户 UID 列表。
    优先级: user_id_list.txt > config.json > 内置默认列表
    """
    # 1. 优先从 user_id_list.txt 读取
    if os.path.exists(USER_ID_LIST_FILE):
        with open(USER_ID_LIST_FILE, 'r', encoding='utf-8') as f:
            uids = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        if uids:
            logger.info(f'从 user_id_list.txt 加载了 {len(uids)} 个用户UID')
            return uids

    # 2. 从 config.json 读取
    cfg = config or load_config()
    uid_list = cfg.get('user_id_list', [])
    if uid_list:
        logger.info(f'从 config.json 加载了 {len(uid_list)} 个用户UID')
        return uid_list

    # 3. 使用内置默认列表
    logger.info(f'使用内置默认营销号列表 ({len(DEFAULT_MUSIC_MARKETING_UIDS)} 个UID)')
    return DEFAULT_MUSIC_MARKETING_UIDS


def _build_weibo_spider_config(user_ids, output_dir, cookie_str, since_date, end_date='now'):
    """
    构建 weibo_spider 库所需的 config.json 格式。

    Args:
        user_ids: 用户 UID 列表
        output_dir: 输出目录
        cookie_str: 微博 Cookie 字符串
        since_date: 起始日期 yyyy-mm-dd
        end_date: 结束日期，默认 "now"

    Returns:
        dict: weibo_spider 格式的配置
    """
    return {
        'user_id_list': user_ids,
        'filter': 0,  # 0=全部微博, 1=仅原创
        'since_date': since_date,
        'end_date': end_date,
        'random_wait_pages': [1, 3],
        'random_wait_seconds': [3, 8],
        'global_wait': [[500, 1800], [300, 900]],
        'write_mode': ['json'],  # 输出 JSON 便于解析
        'pic_download': 0,       # 不下载图片（节省时间）
        'video_download': 0,     # 不下载视频
        'result_dir_name': 0,    # 用UID命名目录
        'cookie': cookie_str,
    }


def scrape_via_weibo_spider(user_ids=None, cookie_str=None, since_date=None, output_dir=None):
    """
    使用 weibo_spider 库爬取指定用户列表的微博。

    通过 subprocess 调用 weibo_spider 的 CLI 入口，
    避免 absl flags 与 Flask 的 import 冲突。

    Args:
        user_ids: 要爬取的用户 UID 列表
        cookie_str: 微博 Cookie 字符串
        since_date: 起始日期 (yyyy-mm-dd)，默认7天前
        output_dir: 输出目录

    Returns:
        list[dict]: 所有爬取到的微博数据列表
    """
    config = load_config()

    if not user_ids:
        user_ids = get_user_id_list(config)

    if not user_ids:
        logger.warning('没有配置任何用户UID，无法爬取')
        return []

    if not cookie_str:
        cookie_str = config.get('cookies', '')
    if not cookie_str or len(cookie_str) < 20:
        logger.error('Cookie 未配置或无效，无法爬取')
        return []

    if not since_date:
        since_date = (datetime.now() - timedelta(days=config.get('max_age_days', 7))).strftime('%Y-%m-%d')

    # 使用临时目录存储输出
    tmpdir = output_dir or tempfile.mkdtemp(prefix='weibo_spider_')

    # 构建 weibo_spider 配置文件
    ws_config = _build_weibo_spider_config(user_ids, tmpdir, cookie_str, since_date)

    config_path = os.path.join(tmpdir, 'ws_config.json')
    os.makedirs(tmpdir, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(ws_config, f, ensure_ascii=False, indent=2)

    logger.info(f'启动 weibo_spider 爬取 {len(user_ids)} 个用户...')
    logger.info(f'配置: since_date={since_date}, 配置路径={config_path}')

    try:
        # 通过 subprocess 调用 weibo_spider
        result = subprocess.run(
            [sys.executable, '-m', 'weibo_spider', '--config_path=' + config_path],
            capture_output=True,
            text=True,
            timeout=600,  # 10分钟超时
            cwd=tmpdir,
        )

        if result.returncode != 0:
            logger.error(f'weibo_spider 执行失败 (返回码 {result.returncode})')
            logger.error(f'stderr: {result.stderr[-500:]}')
            # 不return，尝试读取已有的输出文件

        logger.info(f'weibo_spider 执行完成，开始解析输出文件...')

    except subprocess.TimeoutExpired:
        logger.error('weibo_spider 执行超时（10分钟），尝试读取已爬取数据...')
    except Exception as e:
        logger.error(f'weibo_spider 执行异常: {e}')
        return []

    # 读取输出 JSON 文件
    all_weibos = _read_spider_output(tmpdir)

    logger.info(f'从 {len(user_ids)} 个用户中解析到 {len(all_weibos)} 条微博')

    # 清理临时目录（如果未指定输出目录）
    if not output_dir:
        try:
            import shutil
            shutil.rmtree(tmpdir)
        except Exception:
            pass

    return all_weibos


def _read_spider_output(output_dir):
    """
    读取 weibo_spider 输出的 JSON 文件。

    weibo_spider 的输出结构:
        output_dir/
          ├── {user_nickname or uid}/
          │   └── {uid}.json    ← 包含该用户全部微博
          ├── ...

    每个 .json 文件是一个包含 'user' 和 'weibo' 键的 dict，
    或者直接是一个 weibo 数组。

    Returns:
        list[dict]: 标准化的微博数据列表
    """
    weibos = []

    if not os.path.exists(output_dir):
        return weibos

    # 遍历输出目录中每个用户文件夹
    for dirname in os.listdir(output_dir):
        dirpath = os.path.join(output_dir, dirname)
        if not os.path.isdir(dirpath):
            continue

        for fname in os.listdir(dirpath):
            if not fname.endswith('.json'):
                continue

            fpath = os.path.join(dirpath, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f'读取 {fpath} 失败: {e}')
                continue

            # weibo_spider JSON 输出格式: { "user": {...}, "weibo": [...] }
            if isinstance(data, dict):
                user_info = data.get('user', {})
                weibo_list = data.get('weibo', [])
            elif isinstance(data, list):
                weibo_list = data
                user_info = {}
            else:
                continue

            for w in weibo_list:
                normalized = _normalize_weibo(w, user_info)
                if normalized:
                    weibos.append(normalized)

    return weibos


def _normalize_weibo(raw, user_info=None):
    """
    将 weibo_spider 的原始微博数据标准化为我们的内部格式。

    weibo_spider 字段:
        id, content, article_url, original_pictures, retweet_pictures,
        original, video_url, publish_place, publish_time, publish_tool,
        up_num, retweet_num, comment_num

    user_info 字段:
        id, screen_name (nickname), followers_count, statuses_count,
        verified, verified_reason, description
    """
    ui = user_info or {}

    # 提取字段
    text = raw.get('content', '')
    if not text:
        return None

    # 清理 HTML
    clean_text = _html_to_text(text)

    # 过滤纯图片/视频无文字
    if len(clean_text) < 10:
        return None

    # 过滤广告
    if _is_ad(clean_text):
        return None

    # 过滤敏感
    if _is_sensitive(clean_text):
        return None

    # 互动量
    up_num = raw.get('up_num', 0) or 0
    retweet_num = raw.get('retweet_num', 0) or 0
    comment_num = raw.get('comment_num', 0) or 0
    total_engagement = up_num + retweet_num + comment_num

    # 粉丝数
    followers = ui.get('followers_count', 0) or raw.get('user', {}).get('followers_count', 0)

    # 配置阈值
    config = load_config()
    min_engagement = config.get('min_engagement', 100)
    min_followers = config.get('min_followers', 500)
    max_age_days = config.get('max_age_days', 7)

    # 互动量过滤
    if total_engagement < min_engagement:
        return None

    # 粉丝数过滤
    if followers < min_followers:
        return None

    # 时间过滤
    publish_time = raw.get('publish_time', '') or raw.get('created_at', '')
    if not _is_within_days(publish_time, max_age_days):
        return None

    return {
        'id': str(raw.get('id', '')),
        'text': clean_text,
        'text_html': text,
        'created_at': publish_time,
        'publish_time': publish_time,
        'attitudes_count': up_num,
        'comments_count': comment_num,
        'reposts_count': retweet_num,
        'total_engagement': total_engagement,
        'user': {
            'id': str(ui.get('id', raw.get('user_id', ''))),
            'screen_name': ui.get('screen_name', ui.get('nickname', '')),
            'followers_count': followers,
            'verified': ui.get('verified', False),
            'verified_reason': ui.get('verified_reason', ''),
            'description': ui.get('description', ''),
        },
        'scraped_at': datetime.now().isoformat(),
    }


def _html_to_text(html_text):
    """将微博 HTML 文本转换为纯文本。"""
    if not html_text:
        return ''

    # 移除 HTML 标签
    text = re.sub(r'<br\s*/?>', '\n', html_text)
    text = re.sub(r'<[^>]+>', '', text)
    # 解码 HTML 实体
    text = html_mod.unescape(text)
    # 清理空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_ad(text):
    """判断是否为广告硬广内容。"""
    for kw in AD_FILTER_KEYWORDS:
        if kw in text:
            return True
    return False


def _is_sensitive(text):
    """判断是否包含敏感违规内容。"""
    for kw in SENSITIVE_KEYWORDS:
        if kw in text:
            return True
    return False


def _is_within_days(time_str, max_days):
    """判断微博发布时间是否在指定天数内。"""
    if not time_str:
        return True  # 无时间信息则保留

    try:
        # weibo_spider 格式: "yyyy-mm-dd HH:MM" 或 "yyyy-mm-dd"
        formats = [
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%a %b %d %H:%M:%S %z %Y',
        ]
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str.strip(), fmt)
                break
            except ValueError:
                continue

        if dt is None:
            # 尝试相对时间
            return _parse_relative_time(time_str, max_days)

        delta = datetime.now() - dt.replace(tzinfo=None)
        return delta.days <= max_days
    except Exception:
        return True


def _parse_relative_time(time_str, max_days):
    """解析相对时间字符串。"""
    now = datetime.now()
    if '分钟前' in time_str:
        return True  # 几分钟前肯定在范围内
    if '小时前' in time_str:
        hours = int(re.search(r'(\d+)', time_str).group(1))
        return hours / 24 <= max_days
    if '昨天' in time_str:
        return max_days >= 1
    if '前天' in time_str:
        return max_days >= 2
    return True  # 无法解析则不排除


def scrape_all(config=None):
    """
    执行全量爬取：
    1. 通过 weibo_spider 爬取配置的营销号用户列表
    2. 对爬取结果按内容分类

    Returns:
        dict: { 'live': [...], 'brand': [...], 'show': [...], 'daily': [...], 'hotspot': [...] }
    """
    cfg = config or load_config()

    if not is_cookie_configured():
        logger.warning('Cookie 未配置！请编辑 backend/config.json 填入有效的微博 Cookie')
        return {c: [] for c in ['live', 'brand', 'show', 'daily', 'hotspot']}

    # 获取用户列表
    user_ids = get_user_id_list(cfg)
    logger.info(f'准备爬取 {len(user_ids)} 个营销号用户')

    # 执行爬取
    all_weibos = scrape_via_weibo_spider(user_ids=user_ids)

    logger.info(f'共获取 {len(all_weibos)} 条有效微博（已过滤互动量/粉丝数/广告）')

    # 按内容分类
    categorized = _classify_all(all_weibos)

    # 每类按互动量排序
    for cat in categorized:
        categorized[cat].sort(key=lambda p: p['total_engagement'], reverse=True)

    for cat, posts in categorized.items():
        logger.info(f'  [{cat}] {len(posts)} 条')

    return categorized


def _classify_all(weibos):
    """
    将微博按内容分类到 5 个文案类型。

    分类策略：基于关键词匹配 + 内容特征
    """
    config = load_config()
    keywords = config.get('keywords', {})

    categorized = {
        'live': [],
        'brand': [],
        'show': [],
        'daily': [],
        'hotspot': [],
    }

    for w in weibos:
        text = w['text']
        text_html = w.get('text_html', '')

        # 多关键词匹配打分
        scores = {}
        for cat, kws in keywords.items():
            score = 0
            for kw in kws:
                if kw in text or kw in text_html:
                    score += 1
            scores[cat] = score

        # 选择得分最高的类别
        best_cat = max(scores, key=scores.get)
        if scores[best_cat] > 0:
            w['category'] = best_cat
            categorized[best_cat].append(w)
        else:
            # 无关键词匹配，根据内容特征推断
            inferred = _infer_category(text)
            w['category'] = inferred
            categorized[inferred].append(w)

    return categorized


def _infer_category(text):
    """根据内容特征推断文案类型。"""
    live_signals = ['直播', '空降', 'ING', '实时', '连线']
    brand_signals = ['代言', '品牌', '官宣', '大使', '挚友', '同款']
    show_signals = ['巡演', '演唱会', '开票', '音乐节', 'livehouse', '现场', '抢票', '购票']
    daily_signals = ['营业', '互动', '翻牌', '宠粉', '日常', '更新', '分享']
    hotspot_signals = ['联动', '破圈', '跨界', '联名', '合作']

    scores = {
        'live': sum(1 for s in live_signals if s in text),
        'brand': sum(1 for s in brand_signals if s in text),
        'show': sum(1 for s in show_signals if s in text),
        'daily': sum(1 for s in daily_signals if s in text),
        'hotspot': sum(1 for s in hotspot_signals if s in text),
    }

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'daily'


# ============================================================
# 独立运行入口
# ============================================================
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    print('微博音乐演出营销号爬取工具')
    print('=' * 50)
    config = load_config()

    if not is_cookie_configured():
        print('⚠️  请先在 backend/config.json 中填入有效的微博 Cookie')
        print('   之后重新运行: python scraper.py')
        sys.exit(1)

    print(f'Cookie 已配置 ✓')
    print(f'用户列表: {len(get_user_id_list(config))} 个UID')
    print(f'开始爬取...')

    results = scrape_all(config)

    total = sum(len(posts) for posts in results.values())
    print(f'\n爬取完成！共获取 {total} 条有效微博')
    for cat, posts in results.items():
        print(f'  {cat}: {len(posts)} 条')

    # 保存结果到 data/ 目录
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)

    output_path = os.path.join(data_dir, 'scraped_posts.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f'\n结果已保存到: {output_path}')
