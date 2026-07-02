#!/usr/bin/env python3
"""
Product Hunt API 数据获取脚本
功能：
1. 从 Product Hunt API 获取产品数据
2. 使用两步筛选法识别 AI 工具
3. 生成 tools.json 文件
4. 下载工具图片到本地
"""

import requests
import json
import time
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path

# Product Hunt API 配置
PH_API_URL = "https://api.producthunt.com/v2/api/graphql"
PH_TOKEN = "dQ-Dxt9-u5cMHSrAYe04He1M0OdWZaR9a96Vh3nofhk"

# 请求头
HEADERS = {
    "Authorization": f"Bearer {PH_TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "AINext/1.0"
}

# 图片保存目录
IMAGES_DIR = "images"

# 两步筛选法：AI 相关话题列表（第一步）
AI_TOPIC_SLUGS = {
    "artificial-intelligence",
    "machine-learning",
    "natural-language-processing",
    "computer-vision",
    "ai-tool",
    "chatbot",
    "gpt",
    "llm",
    "deep-learning",
    "neural-network",
    "code-assistant",
    "ai-powered"
}

# 两步筛选法：AI 关键词列表（第二步，正则单词边界匹配）
AI_KEYWORDS = [
    r"\bai\b", r"\bgpt\b", r"\bllms?\b", r"\bgenerative\b",
    r"\bagents?\b", r"\bcopilot\b", r"\bneural\b", r"\bchatbot\b",
    r"\bmachine learning\b", r"\bdeep learning\b",
    r"\bopenai\b", r"\bchatgpt\b", r"\bclaude\b", r"\bgemini\b",
    r"\bstable diffusion\b", r"\bmidjourney\b", r"\bdalle\b",
    r"\bopenrouter\b", r"\bjarvis\b",
    r"\bnatural language\b", r"\bai dictation\b",
    r"\btranscripts?\b", r"\btranscribes?\b",
    r"\bhugging face\b",
    "人工智能", "机器学习", "深度学习"
]

# 创建图片目录
Path(IMAGES_DIR).mkdir(exist_ok=True)


def download_image(url: str, tool_id: str, index: int = 0) -> str:
    """
    下载图片到本地
    返回本地文件路径
    """
    try:
        # 获取文件扩展名
        ext = url.split('?')[0].split('.')[-1].lower()
        if ext not in ['png', 'jpg', 'jpeg', 'gif', 'webp', 'jpeg']:
            ext = 'png'
        
        # 保存路径
        filename = f"{tool_id}_{index}.{ext}"
        save_path = os.path.join(IMAGES_DIR, filename)
        
        # 如果文件已存在，跳过下载
        if os.path.exists(save_path):
            return f"images/{filename}"
        
        # 下载图片
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        print(f"  📷 下载图片: {filename}")
        time.sleep(0.5)  # 避免请求过快
        return f"images/{filename}"
    
    except Exception as e:
        print(f"  ⚠️ 下载图片失败: {e}")
        return url  # 返回原 URL 作为备用


def load_website_map():
    """加载 website redirect 缓存映射表"""
    if os.path.exists("website_map.json"):
        with open("website_map.json", "r") as f:
            return json.load(f)
    return {}


def save_website_map(cache):
    """保存 website redirect 缓存映射表"""
    with open("website_map.json", "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def resolve_website_url(ph_url, tool_id, cache):
    """
    解析 PH 重定向链接，获取真实官网 URL
    使用缓存避免重复请求
    """
    if tool_id in cache:
        return cache[tool_id]
    
    try:
        resp = requests.head(
            ph_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            allow_redirects=True,
            timeout=10
        )
        real_url = resp.url
        if real_url and "producthunt.com" not in real_url:
            cache[tool_id] = real_url
            save_website_map(cache)
            return real_url
    except Exception:
        pass
    
    # 回退到原 PH 链接
    cache[tool_id] = ph_url
    save_website_map(cache)
    return ph_url


def resolve_all_websites(tools):
    """批量解析所有工具的 website 重定向"""
    cache = load_website_map()
    needs_resolve = sum(1 for t in tools if str(t["id"]) not in cache)
    if needs_resolve == 0:
        return cache
    
    print(f"\n🔗 解析 {needs_resolve} 个工具的官网重定向...")
    resolved, total, skipped = 0, needs_resolve, len(tools) - needs_resolve
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # 找出需要解析的工具
    to_resolve = [t for t in tools if str(t["id"]) not in cache]
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(resolve_website_url, t["website"], str(t["id"]), cache): t for t in to_resolve}
        for future in as_completed(futures):
            t = futures[future]
            try:
                real_url = future.result()
                cache[str(t["id"])] = real_url
                resolved += 1
                if resolved % 100 == 0:
                    print(f"  ... {resolved}/{total}")
            except Exception:
                pass
        # 最终保存
        save_website_map(cache)
    
    print(f"  ✅ {resolved} 个已解析, {skipped} 个已有缓存")
    return cache


def apply_website_map(tools, cache):
    """将解析后的真实 URL 写入 tools 数据"""
    for t in tools:
        tid = str(t["id"])
        if tid in cache and "producthunt.com" not in cache[tid]:
            t["website"] = cache[tid]
            t["website_resolved"] = True
    return tools


def is_ai_tool_by_topics(topics: List[Dict]) -> bool:
    """
    第一步：按话题标签筛选
    如果产品的话题标签匹配 AI_TOPIC_SLUGS → 直接判定为 AI 工具
    """
    for topic in topics:
        if topic.get("slug", "").lower() in AI_TOPIC_SLUGS:
            return True
    return False


def is_ai_tool_by_keywords(name: str, tagline: str, description: str) -> bool:
    """
    第二步：按关键词筛选（正则单词边界匹配）
    对于第一步未匹配的产品，检查名称、标语、描述是否包含 AI 关键词
    """
    import re
    text = f"{name} {tagline} {description}".lower()
    for keyword in AI_KEYWORDS:
        if re.search(keyword, text):
            return True
    return False


def is_ai_tool(post: Dict) -> bool:
    """
    两步筛选法识别 AI 工具
    第一步：按话题标签筛选（优先）
    第二步：按关键词筛选（补充）
    """
    # 获取话题标签
    topics = []
    if "topics" in post and "edges" in post["topics"]:
        topics = [edge["node"] for edge in post["topics"]["edges"]]
    
    # 第一步：按话题标签筛选
    if is_ai_tool_by_topics(topics):
        return True
    
    # 第二步：按关键词筛选
    name = post.get("name", "")
    tagline = post.get("tagline", "")
    description = post.get("description", "")
    if is_ai_tool_by_keywords(name, tagline, description):
        return True
    
    return False


def fetch_posts(after: str = None) -> tuple:
    """
    从 Product Hunt API 获取产品列表
    返回：(posts, page_info)
    """
    query = """
    query($first: Int!, $after: String) {
      posts(first: $first, after: $after, order: RANKING) {
        edges {
          node {
            id
            name
            tagline
            description
            createdAt
            votesCount
            commentsCount
            reviewsRating
            website
            url
            thumbnail {
              url
            }
            media {
              url
              type
            }
            topics(first: 10) {
              edges {
                node {
                  name
                  slug
                  description
                }
              }
            }
          }
        }
        pageInfo {
          endCursor
          hasNextPage
        }
      }
    }
    """
    
    variables = {
        "first": 20,
        "after": after
    }
    
    payload = {
        "query": query,
        "variables": variables
    }
    
    try:
        response = requests.post(PH_API_URL, headers=HEADERS, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            print(f"❌ API 错误: {data['errors']}")
            return [], None
        
        posts_data = data.get("data", {}).get("posts", {})
        posts = [edge["node"] for edge in posts_data.get("edges", [])]
        page_info = posts_data.get("pageInfo", {})
        
        return posts, page_info
    
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return [], None


def fetch_all_ai_tools(max_pages: int = 20) -> List[Dict]:
    """
    获取所有 AI 工具（分页获取）
    """
    all_tools = []
    after = None
    page = 1
    
    print(f"📡 开始获取 Product Hunt 数据...")
    
    while page <= max_pages:
        print(f"\n📄 获取第 {page} 页...")
        posts, page_info = fetch_posts(after=after)
        
        if not posts:
            break
        
        # 识别 AI 工具
        for post in posts:
            if is_ai_tool(post):
                # 处理数据格式
                tool = {
                    "id": post.get("id"),
                    "name": post.get("name"),
                    "tagline": post.get("tagline"),
                    "tagline_zh": "",  # 待翻译
                    "description": post.get("description"),
                    "description_zh": "",  # 待翻译
                    "createdAt": post.get("createdAt"),
                    "votesCount": post.get("votesCount", 0),
                    "commentsCount": post.get("commentsCount", 0),
                    "reviewsRating": post.get("reviewsRating", 0),
                    "website": post.get("website"),
                    "thumbnail": post.get("thumbnail", {}).get("url") if post.get("thumbnail") else None,
                    "media": [{"url": m.get("url"), "type": m.get("type")} for m in (post.get("media") or [])],
                    "topics": [],
                    "ph_url": f"https://www.producthunt.com/products/{post.get('name', '').lower().replace(' ', '-')}"  # 使用 name 生成 slug
                }
                
                # 缩略图直接使用 PH CDN URL（不下载到本地）
                # 处理话题标签
                if "topics" in post and "edges" in post["topics"]:
                    tool["topics"] = [
                        {
                            "name": edge["node"]["name"],
                            "slug": edge["node"]["slug"],
                            "description": edge["node"].get("description", ""),
                            "name_zh": ""  # 待翻译
                        }
                        for edge in post["topics"]["edges"]
                    ]
                
                all_tools.append(tool)
        
        print(f"✅ 第 {page} 页完成，已识别 {len(all_tools)} 个 AI 工具")
        
        # 检查是否有下一页
        if not page_info or not page_info.get("hasNextPage"):
            break
        
        after = page_info.get("endCursor")
        page += 1
        time.sleep(2)  # 避免速率限制
    
    print(f"\n🎉 完成！共识别 {len(all_tools)} 个 AI 工具")
    return all_tools


def save_to_json(tools: List[Dict], filename: str = "tools.json"):
    """
    合并保存：新数据更新旧数据，旧工具保留不删除
    """
    # 加载旧数据
    old_dict = {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            old_list = json.load(f)
            old_dict = {t["id"]: t for t in old_list}
    except FileNotFoundError:
        pass
    
    # 合并：新数据覆盖旧数据对应ID，旧数据中不在新数据里的保留
    new_ids = {t["id"] for t in tools}
    merged = [old_dict[tid] for tid in old_dict if tid not in new_ids]  # 保留旧工具
    merged.extend(tools)  # 加入新工具
    
    # 保留旧工具的翻译数据（避免每次重翻）
    for tool in tools:
        tid = tool["id"]
        if tid in old_dict:
            old = old_dict[tid]
            for field in ["tagline_zh", "description_zh", "name_zh"]:
                if old.get(field) and not tool.get(field):
                    tool[field] = old[field]
    
    merged.sort(key=lambda t: t.get("votesCount", 0), reverse=True)  # 按投票排序
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"💾 数据已保存: {len(merged)} 工具 (新增 {len(tools)-len([t for t in tools if t['id'] in old_dict])}，保留 {len(merged)-len(tools)} 个旧工具)")


def main():
    """
    主函数
    """
    print("🚀 AINext 数据获取脚本")
    print("=" * 50)
    
    # 获取所有 AI 工具
    tools = fetch_all_ai_tools(max_pages=20)
    
    if not tools:
        print("❌ 没有获取到任何工具数据")
        return
    
    # 保存新数据（自动合并旧数据）
    save_to_json(tools, "tools.json")
    
    # 解析 PH 重定向 → 真实官网 URL（全量工具）
    all_tools = json.load(open("tools.json", "r", encoding="utf-8"))
    website_cache = resolve_all_websites(all_tools)
    all_tools = apply_website_map(all_tools, website_cache)
    save_to_json(all_tools, "tools.json")
    
    post_process()
    print("\n✅ 数据获取完成！")
    print(f"📊 统计信息:")
    print(f"   - 工具总数: {len(tools)}")
    print(f"   - 总点赞数: {sum(t['votesCount'] for t in tools):,}")
    print(f"   - 总评论数: {sum(t['commentsCount'] for t in tools):,}")


def post_process():
    """数据后处理：生成 slug、匹配分类、更新 sitemap"""
    import re
    with open("tools.json", "r", encoding="utf-8") as f:
        tools = json.load(f)
    
    for t in tools:
        t['slug'] = re.sub(r'[^a-z0-9]+', '-', t.get('name', '').lower()).strip('-')
        t['slug_url'] = f"{t['slug']}-{t['id']}.html"
    
    try:
        cats = json.load(open("categories.json", "r", encoding="utf-8")).get('categories', [])
        kw = {}
        for c in cats:
            for k in c['keywords']: kw[k.lower()] = c['id']
        for t in tools:
            if t.get('category'): continue
            found = set()
            for tp in t.get('topics', []):
                s, n = tp.get('slug', '').lower(), tp.get('name', '').lower()
                for k, cid in kw.items():
                    if k in s or k in n: found.add(cid)
            t['category'] = list(found)[0] if found else 'ai-tool'
    except:
        print("⚠️ 分类匹配跳过")
    
    save_to_json(tools, "tools.json")
    
    print("🗺️ 生成 sitemap...")
    urls = ['https://www.ainext.com/index.html', 'https://www.ainext.com/about.html', 'https://www.ainext.com/privacy.html', 'https://www.ainext.com/terms.html']
    for t in tools: urls.append(f"https://www.ainext.com/tools/{t['slug']}-{t['id']}.html")
    # Category pages
    try:
        cat_data = json.load(open("categories.json"))
        categories = cat_data.get("categories", [])
    except:
        categories = []
    for c in categories: urls.append(f"https://www.ainext.com/category/{c['id']}.html")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls: xml += f'  <url><loc>{u}</loc></url>\n'
    xml += '</urlset>'
    with open("sitemap.xml", "w", encoding="utf-8") as f: f.write(xml)
    print(f"✅ Sitemap: {len(urls)} URLs")


if __name__ == "__main__":
    main()
