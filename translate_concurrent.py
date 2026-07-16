#!/usr/bin/env python3
"""
并发翻译模块 — 多引擎异步并发，单引擎 RPM 限速
优势：5 引擎 × 2 RPM × 10 条/批 ≈ 100 条/分钟，1300 条约 13 分钟
用法：python translate_concurrent.py tools.json
      python translate_concurrent.py tools.json --force
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import aiohttp

# ── 配置 ──────────────────────────────────────────────
BATCH_SIZE = 10
MAX_RETRIES = 2             # 单批最大重试（并发模式下不宜过高）
CHECKPOINT_FILE = ".translate_checkpoint.json"

# ── 引擎配置 ──────────────────────────────────────────
# 每个引擎独立 RPM 限速，并发运行互不干扰
# rpm: 每分钟最多请求数（免费模型建议 1-2）
ENGINES = [
    {
        "name": "GLM-4.6v",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "GLM46_API_KEY",     # 如跟 GLM_API_KEY 共用请修改
        "model": "glm-4.6v",
        "rpm": 2,
    },
    {
        "name": "GLM-4.5-Air",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "GLM45_API_KEY",
        "model": "glm-4.5-air",
        "rpm": 2,
    },
    {
        "name": "GLM-4.7-Flash",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key_env": "GLM_API_KEY",
        "model": "glm-4.7-flash",
        "rpm": 2,
    },
    {
        "name": "Agnes-2.0-Flash",
        "url": lambda: os.environ.get("AGNES_API_URL", "https://apihub.agnes-ai.com/v1/chat/completions"),
        "key_env": "AGNES_API_KEY",
        "model": "agnes-2.0-flash",
        "rpm": 2,
    },
    # Long-Cat — 请补充 API 地址和 model name
    # {
    #     "name": "Long-Cat",
    #     "url": "https://api.longcat.chat/v1/chat/completions",
    #     "key_env": "LONGCAT_API_KEY",
    #     "model": "longcat",
    #     "rpm": 2,
    # },
]


# ── 工具函数 ──────────────────────────────────────────
def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip()


def save_checkpoint(remaining_batches, translated_count):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"remaining": remaining_batches, "done": translated_count}, f)


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _write_slim(tools: list):
    """从工具列表同步生成 tools-slim.json"""
    slim = []
    for t in tools:
        slim.append({
            "id": t["id"], "name": t["name"], "slug": t["slug"],
            "tagline": t.get("tagline", ""), "tagline_zh": t.get("tagline_zh", ""),
            "thumbnail": t.get("thumbnail", ""),
            "votesCount": t.get("votesCount", 0), "commentsCount": t.get("commentsCount", 0),
            "createdAt": t.get("createdAt", ""), "website": t.get("website", ""),
            "category": t.get("category", ""),
            "topics": [{"name": tp["name"]} for tp in (t.get("topics") or [])[:3]],
        })
    with open("tools-slim.json", "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)
    print(f"📦 已同步生成 tools-slim.json ({len(slim)} 条)")


# ── 翻译核心 ──────────────────────────────────────────

async def translate_batch(session, texts, engine):
    """用指定引擎翻译一批文本，返回结果列表或 None"""
    items = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))

    prompt = f"""Translate the following English tool taglines/descriptions to Simplified Chinese.
Follow these rules:
1. Keep AI/product terminology untranslated (e.g., "API", "LLM", "GPT")
2. Make the Chinese sound natural for Chinese users
3. Return ONLY a valid JSON array of strings, one per input line
4. Do NOT include any other text, explanation, or markdown

Input:
{items}

Output (JSON array only):"""

    url = engine["url"]() if callable(engine["url"]) else engine["url"]
    payload = {
        "model": engine["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {engine['key']}",
    }

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status == 429:
                return None  # 限流，跳过本次
            if resp.status != 200:
                body = await resp.text()
                print(f"  [{engine['name']}] HTTP {resp.status}: {body[:100]}")
                return None
            data = await resp.json()
            content = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [{engine['name']}] 请求异常: {str(e)[:80]}")
        return None

    # 解析 JSON
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        result = json.loads(content)
        if len(result) == len(texts):
            return result
    except json.JSONDecodeError:
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1:
            try:
                result = json.loads(content[start:end+1])
                if len(result) == len(texts):
                    return result
            except json.JSONDecodeError:
                pass
    return None


class RateLimiter:
    """简易 RPM 限速器"""
    def __init__(self, rpm):
        self.interval = 60.0 / rpm
        self.last = 0

    async def wait(self):
        now = time.time()
        wait = self.interval - (now - self.last)
        if wait > 0:
            await asyncio.sleep(wait)
        self.last = time.time()


async def engine_worker(engine, queue, tools, stats, lock):
    """单引擎 worker：从队列取批次 → 翻译 → 回填 tools"""
    name = engine["name"]
    limiter = RateLimiter(engine["rpm"])
    import ssl as _ssl
    connector = aiohttp.TCPConnector(ssl=False)  # SSL 豁免（Agnes 证书在本机/CI 报错）
    session = aiohttp.ClientSession(connector=connector)
    eng_stats = {"ok": 0, "fail": 0}  # 单引擎统计
    stats[f"_eng_{name}"] = eng_stats

    try:
        while True:
            try:
                batch_items = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            batch_idx, batch = batch_items
            texts = [item[2] for item in batch]
            ok = False

            for attempt in range(1, MAX_RETRIES + 1):
                await limiter.wait()
                results = await translate_batch(session, texts, engine)
                if results:
                    async with lock:
                        for (i, field, _), result in zip(batch, results):
                            if result and result.strip():
                                tools[i][field] = result.strip()
                                stats["translated"] += 1
                    eng_stats["ok"] += 1
                    print(f"  [{name}] ✅ 批次 {batch_idx}", flush=True)
                    ok = True
                    break
                elif attempt < MAX_RETRIES:
                    wait = 2 ** attempt
                    print(f"  [{name}] ⚠️ 批次 {batch_idx} 重试 {attempt+1}/{MAX_RETRIES}", flush=True)
                    await asyncio.sleep(wait)
            if not ok:
                eng_stats["fail"] += 1

            async with lock:
                stats["batches_done"] += 1
                done = stats["batches_done"]
                # 每 5 批输出汇总
                if done % 5 == 0:
                    parts = []
                    for k, v in stats.items():
                        if k.startswith("_eng_"):
                            e = v
                            parts.append(f"{k[5:]}:{e['ok']}/{e['ok']+e['fail']}")
                    print(f"  📊 [{done}/{stats['total_batches']}] {' | '.join(parts)}  ✓{stats['translated']}", flush=True)
                # 每 20 批存盘
                if done % 20 == 0:
                    _save_tools(tools)
                    save_checkpoint([], stats["translated"])

            queue.task_done()
    finally:
        await session.close()


def _save_tools(tools):
    """原子写回 tools.json"""
    tmp = "tools.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tools, f, ensure_ascii=False, indent=2)
    os.replace(tmp, "tools.json")


# ── 合并 / 继承 ──────────────────────────────────────

def merge_translations(tools):
    """从 git HEAD 继承已有翻译（若 fail 则静默跳过）"""
    inherited = 0
    try:
        old_raw = subprocess.run(
            ["git", "show", "HEAD:tools.json"],
            capture_output=True, text=True, timeout=10,
        )
        if old_raw.returncode == 0 and old_raw.stdout.strip():
            old_list = json.loads(old_raw.stdout)
            old_dict = {t["id"]: t for t in old_list}
            for t in tools:
                tid = t["id"]
                if tid in old_dict:
                    o = old_dict[tid]
                    for f in ["tagline_zh", "description_zh", "name_zh"]:
                        if o.get(f) and not t.get(f):
                            t[f] = o[f]
                            inherited += 1
            print(f"📋 从旧版继承了 {inherited} 条翻译")
    except Exception as e:
        print(f"⚠️ 读取旧版失败: {e}")
    return inherited


# ── 主流程 ────────────────────────────────────────────

async def translate_tools(tools_json_path: str, force: bool = False):
    # 1. 加载
    with open(tools_json_path, "r", encoding="utf-8") as f:
        tools = json.load(f)

    # 2. 继承旧翻译
    merge_translations(tools)

    # 3. 收集待翻译
    to_translate = []
    for i, t in enumerate(tools):
        if (force or not t.get("tagline_zh")) and t.get("tagline"):
            to_translate.append((i, "tagline_zh", t["tagline"]))
        if (force or not t.get("description_zh")) and t.get("description"):
            to_translate.append((i, "description_zh", t["description"]))

    if not to_translate:
        print("✅ 所有工具已有中文翻译")
        _write_slim(tools)
        return tools

    total = len(to_translate)
    print(f"📝 共 {total} 条待翻译文本")

    # 4. 分批
    batches = [
        (bi, to_translate[i:i+BATCH_SIZE])
        for bi, i in enumerate(range(0, total, BATCH_SIZE))
    ]
    print(f"📦 分 {len(batches)} 批，每批 {BATCH_SIZE} 条")

    # 5. 筛选可用引擎
    active = []
    for eng in ENGINES:
        key = os.environ.get(eng["key_env"], "")
        if key:
            eng = {**eng, "key": key}
            active.append(eng)
        else:
            print(f"  ⏭ {eng['name']}: 未配置 API Key ({eng['key_env']})，跳过")

    if not active:
        print("❌ 所有引擎均未配置 API Key")
        _write_slim(tools)
        return tools

    print(f"🚀 启动 {len(active)} 个并发引擎:")
    for e in active:
        print(f"    {e['name']} (RPM={e['rpm']})")

    # 6. 恢复断点
    queue = asyncio.Queue()
    ckpt = load_checkpoint()
    if ckpt and ckpt["remaining"]:
        print(f"🔄 从断点恢复，已完成 {ckpt['done']}/{total} 条")
        for item in ckpt["remaining"]:
            await queue.put(item)
    else:
        for b in batches:
            await queue.put(b)

    # 7. 启动并发 workers
    stats = {"translated": ckpt["done"] if ckpt else 0, "batches_done": 0, "total_batches": len(batches)}
    lock = asyncio.Lock()

    workers = [
        asyncio.create_task(engine_worker(e, queue, tools, stats, lock))
        for e in active
    ]
    await asyncio.gather(*workers, return_exceptions=True)

    # 8. 最终存盘
    _save_tools(tools)
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    remaining = total - stats["translated"]
    print(f"\n✅ 翻译完成: {stats['translated']}/{total} 条成功"
          + (f" (剩余 {remaining} 条)" if remaining else ""))
    _write_slim(tools)
    return tools


# ── 命令行入口 ──────────────────────────────────────────
if __name__ == "__main__":
    import sys

    load_env()
    args = sys.argv[1:]
    force = "--force" in args
    path = next((a for a in args if not a.startswith("--")), "tools.json")
    try:
        asyncio.run(translate_tools(path, force=force))
    except Exception as e:
        traceback.print_exc()
        print(f"\n❌ translate_concurrent 异常: {e}")
    finally:
        # 兜底 slim 生成
        try:
            with open(path, "r", encoding="utf-8") as f:
                _write_slim(json.load(f))
        except Exception as se:
            print(f"⚠️ slim 兜底生成失败: {se}")
