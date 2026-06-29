#!/usr/bin/env python3
"""
AI 工具翻译模块 — LLM 引擎（GLM-4.7-Flash 主，Agnes 备份）
优势：批量翻译 / 指数重试 / 断点续跑 / 比百度 API 更稳定
用法：python translate_llm.py tools.json
"""

import json
import os
import subprocess
import time
import requests
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
BATCH_SIZE = 10          # 每批翻译条数
MAX_RETRIES = 5          # 单批最大重试次数
BASE_DELAY = 2           # 重试基础延迟（秒），2 → 4 → 8 → 16 → 32
CHECKPOINT_FILE = ".translate_checkpoint.json"
GLM_COOLDOWN = 25        # GLM 免费版限流严重，批次间冷却秒数


# ── 加载 .env ──────────────────────────────────────────
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


# ── 引擎配置 ──────────────────────────────────────────
ENGINES = [
    {
        "name": "Agnes-2.0-Flash",
        "url": lambda: (os.environ.get("AGNES_API_URL", "") + "/chat/completions"),
        "key": lambda: os.environ.get("AGNES_API_KEY", ""),
        "model": "agnes-2.0-flash",
    },
    {
        "name": "GLM-4.5-Air",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key": lambda: os.environ.get("GLM45_API_KEY", ""),
        "model": "glm-4.5-air",
    },
    {
        "name": "GLM-4.7-Flash",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "key": lambda: os.environ.get("GLM_API_KEY", ""),
        "model": "glm-4.7-flash",
    },
]


def translate_batch_with_llm(texts, engine):
    """用 LLM 批量翻译 tagline + description"""

    # 构建 prompt：要求 JSON 格式输出
    items = []
    for i, t in enumerate(texts):
        items.append(f"{i+1}. {t}")
    items_text = "\n".join(items)

    prompt = f"""Translate the following English tool taglines/descriptions to Simplified Chinese.
Follow these rules:
1. Keep AI/product terminology untranslated (e.g., "API", "LLM", "GPT")
2. Make the Chinese sound natural for Chinese users
3. Return ONLY a valid JSON array of strings, one per input line
4. Do NOT include any other text, explanation, or markdown

Input:
{items_text}

Output (JSON array only):"""

    payload = {
        "model": engine["model"] if callable(engine["model"]) else engine["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    url = engine["url"]() if callable(engine["url"]) else engine["url"]
    key = engine["key"]()

    resp = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        json=payload,
        timeout=60,
    )

    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()

    # 清理 LLM 偶尔多输出的 markdown 标记
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # 尝试提取 [...] 之间的内容
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1:
            result = json.loads(content[start : end + 1])
        else:
            raise

    return result


def try_translate_batch(texts, tried_engines=None):
    """尝试翻译一批，支持引擎切换和指数退避"""
    if tried_engines is None:
        tried_engines = set()

    for engine in ENGINES:
        if engine["name"] in tried_engines:
            continue
        key = engine["key"]()
        if not key:
            print(f"  ⏭ {engine['name']}: 未配置 API Key，跳过")
            tried_engines.add(engine["name"])
            continue

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"  [{engine['name']}] 尝试 {attempt}/{MAX_RETRIES}...", end=" ")
                result = translate_batch_with_llm(texts, engine)
                if len(result) >= len(texts):
                    print(f"✅ 成功 {len(result)} 条")
                    return result, engine["name"]
                else:
                    print(f"⚠️ 返回 {len(result)}/{len(texts)} 条，不完整")
            except Exception as e:
                print(f"❌ {str(e)[:80]}")

            if attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1))
                print(f"  ⏳ {delay}s 后重试...")
                time.sleep(delay)

        print(f"  🚫 {engine['name']}: 全部 {MAX_RETRIES} 次重试失败")
        tried_engines.add(engine["name"])

    return None, None


def save_checkpoint(remaining_batches, translated_count):
    """保存断点"""
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({"remaining": remaining_batches, "done": translated_count}, f)


def load_checkpoint():
    """加载断点"""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def translate_tools(tools_json_path: str, output_path: str = None, force: bool = False):
    """批量翻译 tools.json 中的 tagline 和 description
    默认增量模式（只翻译无 _zh 的），--force 覆盖全部已有翻译"""

    # ── 1. 加载数据 ──
    with open(tools_json_path, "r", encoding="utf-8") as f:
        tools = json.load(f)

    # ── 2. 从 git 继承已有翻译 ──
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

    # ── 3. 收集待翻译文本 ──
    to_translate = []  # [(tool_index, field, text)]
    for i, t in enumerate(tools):
        if (force or not t.get("tagline_zh")) and t.get("tagline"):
            to_translate.append((i, "tagline_zh", t["tagline"]))
        if (force or not t.get("description_zh")) and t.get("description"):
            to_translate.append((i, "description_zh", t["description"]))

    if not to_translate:
        print("✅ 所有工具已有中文翻译")
        return tools

    total = len(to_translate)
    print(f"📝 共 {total} 条待翻译文本")

    # ── 4. 分批 ──
    batches = [to_translate[i : i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    print(f"📦 分 {len(batches)} 批，每批 {BATCH_SIZE} 条")

    # ── 5. 恢复断点 ──
    ckpt = load_checkpoint()
    if ckpt and ckpt["remaining"]:
        print(f"🔄 从断点恢复，已完成 {ckpt['done']}/{total} 条")
        batches = ckpt["remaining"]

    # ── 6. 逐批翻译 ──
    translated = ckpt["done"] if ckpt else 0
    tried_engines = set()

    for bi, batch in enumerate(batches):
        texts = [item[2] for item in batch]
        print(f"\n📦 批次 {bi+1}/{len(batches)} ({len(texts)} 条)")

        results, engine_name = try_translate_batch(texts, tried_engines)

        if results is None:
            print(f"\n❌ 所有引擎均失败。已完成 {translated}/{total} 条，断点已保存。")
            save_checkpoint(batches[bi:], translated)
            return tools

        # 写回结果
        for (i, field, _), result in zip(batch, results):
            if result and result.strip():
                tools[i][field] = result.strip()
                translated += 1

        # 每批存盘
        output = output_path or tools_json_path
        with open(output, "w", encoding="utf-8") as f:
            json.dump(tools, f, ensure_ascii=False, indent=2)

        remaining = batches[bi + 1 :]
        save_checkpoint(remaining, translated)
        print(f"  💾 已存盘 ({translated}/{total})")

        tried_engines.clear()
        if engine_name and engine_name.startswith("GLM"):
            print(f"  ⏳ GLM 冷却 {GLM_COOLDOWN}s...")
            time.sleep(GLM_COOLDOWN)
        else:
            time.sleep(0.5)

    # ── 7. 完成 ──
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

    print(f"\n✅ 翻译完成: {translated}/{total} 条成功")
    print(f"💾 已保存到: {output_path or tools_json_path}")
    return tools


# ── 命令行入口 ──────────────────────────────────────────
if __name__ == "__main__":
    import sys

    load_env()
    args = sys.argv[1:]
    force = "--force" in args
    path = next((a for a in args if not a.startswith("--")), "tools.json")
    translate_tools(path, force=force)
