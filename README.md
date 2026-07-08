# 微博音乐演出行业通用文案生成器

基于 weiboSpider 实时爬取微博大V文案，一键生成差异化微博营销文案的轻量化Web应用。

**🎯 公开网站**: [caojingzhi1015-bit.github.io/weibo-copy-generator](https://caojingzhi1015-bit.github.io/weibo-copy-generator/)

---

## 一键部署后端（启用实时爬取）

前端已部署在 GitHub Pages，但要启用**实时微博爬取**功能，需要部署后端：

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/caojingzhi1015-bit/weibo-copy-generator)

点击上方按钮 → 登录 Render → 自动部署，约 2 分钟完成。

部署后需要配置微博 Cookie（`backend/config.json` 中的 `cookies` 字段）才能开始实时爬取。

## 功能特点

- **5种文案类型**: 直播/空降、品牌代言、演出宣发、日常互动、热点联动
- **3种风格调节**: 官方正式风 / 粉丝安利风 / 营销号吃瓜风
- **实时爬取**: 基于 weiboSpider 爬取500粉以上微博音乐演出营销号数据
- **智能生成**: 模板+动态词汇替换，批次级去重校验
- **传播评分**: 基于爬取数据的互动分析，对生成文案进行传播潜力评分
- **多端适配**: 移动端响应式，支持一键复制和导出

## 本地开发

```bash
# 1. 安装依赖
cd backend && pip install -r requirements.txt

# 2. 配置 Cookie（编辑 backend/config.json）
#    浏览器登录 weibo.com → F12 → Application → Cookies → 复制全部

# 3. 配置爬取目标（编辑 backend/config.json 的 user_id_list）
#    或创建 backend/user_id_list.txt（每行一个UID）

# 4. 启动后端
python server.py
# 访问 http://localhost:5050

# 5. 前端直接用浏览器打开 index.html
```

## 技术栈

- **前端**: 纯 HTML+CSS+JS，低饱和度简约风格，localStorage 持久化
- **后端**: Python Flask + APScheduler 定时爬取
- **爬虫**: [weiboSpider](https://github.com/dataabc/weiboSpider) 基于 m.weibo.cn API
- **部署**: GitHub Pages（前端）+ Render.com（后端）

## API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/status` | GET | 话术库状态 |
| `/api/library` | GET | 完整话术库 |
| `/api/library/<type>` | GET | 按类型话术库 |
| `/api/scrape` | POST | 触发 weiboSpider 爬取 |
| `/api/config/cookies` | POST | 配置微博 Cookie |
| `/api/config/user_ids` | POST | 配置爬取用户UID |
