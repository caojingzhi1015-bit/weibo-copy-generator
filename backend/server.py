"""
微博音乐演出文案生成器 - 后端 API 服务器 + 前端静态文件服务
基于 Flask，提供话术库查询、爬取触发、自定义话术管理等接口，
同时托管前端 index.html 静态页面（生产模式单文件部署）。

启动方式:
    python server.py
    # 环境变量: PORT=5050 (默认)

部署平台: Render.com / Railway / 任何支持 Python 的平台
"""

import os
import sys
import logging

from flask import Flask, jsonify, request, send_from_directory

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(__file__))

from config import load_config, save_config, is_cookie_configured, SCRAPE_LOG_PATH
from library_manager import (
    load_library, get_library_preview, get_library_status,
    add_custom_phrase,
)
from scheduler import (
    start_scheduler, stop_scheduler, trigger_manual_scrape, _log_scrape,
)
from scraper import get_user_id_list

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('server')

app = Flask(__name__, static_folder='../', static_url_path='')
CORS(app)  # 允许跨域访问（开发时前端可能在不同端口）


# ============================================================
# 前端页面托管（生产模式：前后端同源部署）
# ============================================================

@app.route('/')
def serve_index():
    """托管前端主页面。"""
    return send_from_directory(os.path.join(os.path.dirname(__file__), '..'), 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """托管其他静态资源。"""
    parent = os.path.join(os.path.dirname(__file__), '..')
    file_path = os.path.join(parent, path)
    if os.path.isfile(file_path):
        return send_from_directory(parent, path)
    # 非文件请求返回 404
    return jsonify({'error': 'Not found'}), 404


# ============================================================
# API: 话术库状态
# ============================================================

@app.route('/api/status', methods=['GET'])
def api_status():
    """获取话术库状态信息。"""
    try:
        status = get_library_status()
        status['cookie_configured'] = is_cookie_configured()
        return jsonify(status)
    except Exception as e:
        logger.error(f'获取状态失败: {e}')
        return jsonify({'error': str(e)}), 500


# ============================================================
# API: 获取话术库
# ============================================================

@app.route('/api/library', methods=['GET'])
def api_get_library():
    """获取完整话术库数据。"""
    try:
        library = load_library()
        return jsonify(library)
    except Exception as e:
        logger.error(f'获取话术库失败: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/library/<category>', methods=['GET'])
def api_get_library_category(category):
    """获取指定类型的话术库数据。

    Args:
        category: live | brand | show | daily | hotspot
    """
    valid_categories = ['live', 'brand', 'show', 'daily', 'hotspot']
    if category not in valid_categories:
        return jsonify({'error': f'无效的文案类型: {category}，有效类型: {valid_categories}'}), 400

    try:
        library = load_library()
        cat_data = library.get(category, {})
        return jsonify(cat_data)
    except Exception as e:
        logger.error(f'获取话术库分类失败: {e}')
        return jsonify({'error': str(e)}), 500


# ============================================================
# API: 文案预览
# ============================================================

@app.route('/api/preview/<category>', methods=['GET'])
def api_get_preview(category):
    """获取指定类型的文案预览样本。

    Query params:
        limit: 返回条数（默认 10）
    """
    valid_categories = ['live', 'brand', 'show', 'daily', 'hotspot']
    if category not in valid_categories:
        return jsonify({'error': f'无效的文案类型: {category}'}), 400

    try:
        limit = request.args.get('limit', 10, type=int)
        limit = min(limit, 30)  # 最多 30 条
        samples = get_library_preview(category, limit)
        return jsonify({'category': category, 'samples': samples, 'count': len(samples)})
    except Exception as e:
        logger.error(f'获取预览失败: {e}')
        return jsonify({'error': str(e)}), 500


# ============================================================
# API: 手动触发爬取
# ============================================================

@app.route('/api/scrape', methods=['POST'])
def api_trigger_scrape():
    """手动触发一次全量爬取。"""
    try:
        result = trigger_manual_scrape()
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        logger.error(f'手动爬取异常: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# API: 用户自定义话术
# ============================================================

@app.route('/api/library/custom', methods=['POST'])
def api_add_custom_phrase():
    """添加用户自定义话术。

    Request body (JSON):
        category: 文案类型 (live/brand/show/daily/hotspot)
        text: 话术文本
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体不能为空'}), 400

        category = data.get('category')
        text = data.get('text')

        if not category or not text:
            return jsonify({'error': '请提供 category 和 text 字段'}), 400

        valid_categories = ['live', 'brand', 'show', 'daily', 'hotspot']
        if category not in valid_categories:
            return jsonify({'error': f'无效的文案类型: {category}'}), 400

        if len(text) < 10:
            return jsonify({'error': '话术文本至少需要 10 个字符'}), 400

        if len(text) > 200:
            return jsonify({'error': '话术文本不能超过 200 个字符'}), 400

        updated_library = add_custom_phrase(category, text)
        return jsonify({
            'success': True,
            'message': f'已将话术添加到 [{category}] 类型',
            'category': category,
            'text': text,
        })
    except Exception as e:
        logger.error(f'添加自定义话术失败: {e}')
        return jsonify({'error': str(e)}), 500


# ============================================================
# API: 爬取日志
# ============================================================

@app.route('/api/scrape/logs', methods=['GET'])
def api_get_scrape_logs():
    """获取最近爬取日志。"""
    import json
    try:
        if os.path.exists(SCRAPE_LOG_PATH):
            with open(SCRAPE_LOG_PATH, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []
        return jsonify({'logs': logs[:20]})
    except Exception as e:
        logger.error(f'获取爬取日志失败: {e}')
        return jsonify({'logs': [], 'error': str(e)}), 500


# ============================================================
# API: Cookie 配置
# ============================================================

@app.route('/api/config/cookies', methods=['GET'])
def api_check_cookies():
    """检查 Cookie 配置状态。"""
    cookie_ok = is_cookie_configured()
    config = load_config()
    # 脱敏显示
    cookie_preview = ''
    raw = config.get('cookies', '')
    if len(raw) > 20:
        cookie_preview = raw[:20] + '...' + raw[-10:]

    return jsonify({
        'configured': cookie_ok,
        'preview': cookie_preview if cookie_ok else '',
    })


@app.route('/api/config/cookies', methods=['POST'])
def api_update_cookies():
    """更新 Cookie 配置。

    Request body (JSON):
        cookies: 微博 Cookie 字符串
    """
    try:
        data = request.get_json()
        cookies = data.get('cookies', '').strip()

        if not cookies:
            return jsonify({'error': 'Cookie 不能为空'}), 400

        if len(cookies) < 20:
            return jsonify({'error': 'Cookie 格式不正确，长度过短'}), 400

        config = load_config()
        config['cookies'] = cookies
        save_config(config)

        logger.info('Cookie 配置已更新')

        return jsonify({
            'success': True,
            'message': 'Cookie 已更新。建议立即触发一次爬取以验证有效性。',
        })
    except Exception as e:
        logger.error(f'更新 Cookie 失败: {e}')
        return jsonify({'error': str(e)}), 500


# ============================================================
# API: 营销号 UID 列表管理
# ============================================================

@app.route('/api/config/user_ids', methods=['GET'])
def api_get_user_ids():
    """获取当前配置的爬取用户 UID 列表。"""
    try:
        uids = get_user_id_list()
        return jsonify({
            'count': len(uids),
            'user_ids': uids,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/user_ids', methods=['POST'])
def api_update_user_ids():
    """更新爬取用户 UID 列表。

    Request body (JSON):
        user_ids: [UID1, UID2, ...]
    """
    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])

        if not user_ids or not isinstance(user_ids, list):
            return jsonify({'error': 'user_ids 必须是一个非空数组'}), 400

        config = load_config()
        config['user_id_list'] = [str(uid) for uid in user_ids]
        save_config(config)

        logger.info(f'用户UID列表已更新: {len(user_ids)} 个UID')

        return jsonify({
            'success': True,
            'count': len(user_ids),
            'message': f'UID列表已更新（{len(user_ids)} 个用户）',
        })
    except Exception as e:
        logger.error(f'更新UID列表失败: {e}')
        return jsonify({'error': str(e)}), 500


# ============================================================
# 启动入口
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print('=' * 50)
    print('  微博音乐演出文案生成器')
    print(f'  地址: http://localhost:{port}')
    print(f'  API:  http://localhost:{port}/api/status')
    print('=' * 50)

    # 启动定时爬取调度器
    try:
        start_scheduler()
        logger.info('定时爬取调度器已启动')
    except Exception as e:
        logger.warning(f'调度器启动失败（可能 Cookie 未配置）: {e}')

    # 启动 Flask 服务
    try:
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False,  # 关闭 reloader 避免调度器重复启动
        )
    except KeyboardInterrupt:
        logger.info('收到中断信号，正在关闭...')
        stop_scheduler()
    except Exception as e:
        logger.error(f'服务器异常: {e}')
        stop_scheduler()
