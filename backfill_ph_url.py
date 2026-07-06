#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定向/全量回填 PH 官方产品页 URL 到 tools.json 的 ph_url 字段（断点续传、限流自适应）。

设计要点：
- 断点续传：进度缓存到 ph_url_map.json（id -> 官方url，原子写），重跑自动跳过已拉取项；
  进程被中断后再次运行从断点继续，不会被截断损坏。
- 限流自适应：遇到 HTTP 429 时解析错误中的 reset_in 字段，休眠到窗口重置后重试同一批，
  使单次运行可跨多个 15 分钟限流窗口续跑（适合 GitHub Actions 长时任务）。
- 原生 url：直接采用 PH API 返回的 post.url，仅去掉 utm 归因 query 参数（用户要求"用官方返回、别自己编"）。
- 仅修改 tools.json 的 ph_url；tools-slim.json 不含该字段，无需动；每日更新按 id 合并，回填结果不会被覆盖。

用法：
  python backfill_ph_url.py                 # 全量（所有未缓存的）
  RISKY_ONLY=1 python backfill_ph_url.py    # 仅回填名字含 数字/&/+/()/ 的高风险产品
  MAX_PER_RUN=200 python backfill_ph_url.py # 单次最多处理 N 个（便于 CI 分批）
"""
import os
import re
import time
import json
import requests

PH_API_URL = "https://api.producthunt.com/v2/api/graphql"
PH_TOKEN = "dQ-Dxt9-u5cMHSrAYe04He1M0OdWZaR9a96Vh3nofhk"
HEADERS = {
    "Authorization": f"Bearer {PH_TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "AINext/1.0",
}

TOOLS = "tools.json"
MAP = "ph_url_map.json"
BATCH = int(os.environ.get("BATCH", "10") or "10")
DELAY = 0.15                       # 每批请求间隔（秒）
RISKY_ONLY = os.environ.get("RISKY_ONLY", "0") == "1"
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "0") or "0")
# 名字含这些字符时，正则 slug 可能与 PH 实际路径不符（版本号/&/+/()/等）
RISKY_RE = re.compile(r'[0-9&+/()]')


def is_risky(name: str) -> bool:
    return bool(RISKY_RE.search(name or ""))


def regex_fallback(name: str) -> str:
    """PH 产品页 URL 的最后兜底：用 name 规范成 slug（仅当 API 完全拿不到时用）。"""
    return "https://www.producthunt.com/products/" + re.sub(
        r'[^a-z0-9]+', '-', (name or '').lower()
    ).strip('-')


def fetch_batch(ids: list, retries: int = 5) -> dict:
    """
    批量按 id 拉取官方产品页 URL（单请求用别名一次取 BATCH 个）。
    遇到 429：解析 reset_in 休眠后重试同一批（跨限流窗口续跑）。
    返回：{id: 官方url(去utm)}；拿不到的 id 不出现于返回字典。
    """
    if not ids:
        return {}
    alias_parts = [f'  p{i}: post(id:"{tid}"){{ id url }}' for i, tid in enumerate(ids)]
    query = "query {\n" + "\n".join(alias_parts) + "\n}"
    out: dict = {}
    for attempt in range(retries):
        try:
            r = requests.post(PH_API_URL, headers=HEADERS, json={"query": query}, timeout=40)
        except Exception as e:
            print(f"  ⚠️ 批量请求异常: {e}，重试 {attempt+1}/{retries}")
            time.sleep(5)
            continue
        if r.status_code == 429:
            wait = 60
            try:
                errs = r.json().get("errors", [])
                if errs and errs[0].get("details", {}).get("reset_in"):
                    wait = int(errs[0]["details"]["reset_in"]) + 5
            except Exception:
                pass
            print(f"  ⚠️ 限流，休眠 {wait}s 后重试同一批 {attempt+1}/{retries}")
            time.sleep(wait)
            continue
        try:
            r.raise_for_status()
        except Exception as e:
            print(f"  ⚠️ HTTP 错误 {r.status_code}: {e}，重试 {attempt+1}/{retries}")
            time.sleep(5)
            continue
        try:
            data = r.json()
        except Exception:
            time.sleep(5)
            continue
        if data.get("errors"):
            print(f"  ⚠️ API 错误: {data['errors'][:2]}")
        posts = (data.get("data") or {})
        for i, tid in enumerate(ids):
            node = posts.get(f"p{i}")
            if node and node.get("url"):
                out[str(tid)] = node["url"].split("?")[0]
        return out
    return out


def atomic_dump(obj, path: str, indent=0):
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def main():
    tools = json.load(open(TOOLS, encoding="utf-8"))
    url_map: dict = {}
    if os.path.exists(MAP):
        url_map = json.load(open(MAP, encoding="utf-8"))

    # 构造待拉取列表
    todo = []
    for t in tools:
        tid = str(t.get("id") or "")
        if not tid or tid in url_map:
            continue
        if RISKY_ONLY and not is_risky(t.get("name", "")):
            continue
        todo.append(tid)

    if MAX_PER_RUN:
        todo = todo[:MAX_PER_RUN]

    print(f"载入 {len(tools)} 个工具，缓存已有 {len(url_map)} 条"
          + (" | RISKY_ONLY" if RISKY_ONLY else "")
          + (f" | MAX_PER_RUN={MAX_PER_RUN}" if MAX_PER_RUN else "")
          + f"\n待拉取（未缓存）: {len(todo)} 个")

    success = failed = 0
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        res = fetch_batch(chunk)
        for tid in chunk:
            if tid in res and res[tid]:
                url_map[tid] = res[tid]
                success += 1
            else:
                failed += 1
        atomic_dump(url_map, MAP)   # 每批落盘，断点续传安全
        if (start + BATCH) % 500 < BATCH:
            print(f"进度 {min(start + BATCH, len(todo))}/{len(todo)} | 新拉取 {success} 失败 {failed}")
        time.sleep(DELAY)

    # 应用 url_map 写回 tools.json（原子写）
    applied = 0
    for t in tools:
        key = str(t.get("id") or "")
        if key in url_map and url_map[key]:
            t["ph_url"] = url_map[key]
            applied += 1
        elif not t.get("ph_url"):
            t["ph_url"] = regex_fallback(t.get("name"))
    atomic_dump(tools, TOOLS, indent=2)

    print(f"✅ 完成 | 新拉取 {success} 应用 {applied} | 失败(保留原值) {failed}")
    print(f"📦 缓存文件 {MAP} 共 {len(url_map)} 条")

    bad = [t.get("name") for t in tools if not (t.get("ph_url") or "").startswith(
        ("https://www.producthunt.com/products/", "/products/"))]
    print(f"🔎 校验：非法 ph_url 条数 = {len(bad)}", bad[:5])


if __name__ == "__main__":
    main()
