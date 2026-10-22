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
import ssl as _ssl

# ── 配置 ──────────────────────────────────────────────
# 单批条数：可用引擎越少，越要靠加大单批来提吞吐（一次请求翻 20 条 = RPM1 也有 20 条/分钟）
BATCH_SIZE = int(os.environ.get("TRANSLATE_BATCH", "20"))
MAX_RETRIES = 2             # 单批最大重试（并发模式下不宜过高）
CHECKPOINT_FILE = ".translate_checkpoint.json"

# ── 错误可见化 ────────────────────────────────────────
# 曾踩坑：429 分支直接 return None 且不打印，导致 4 个引擎全部失效时
# 日志一片"重试 x/2"，跑满 3 小时后只报"翻译完成 50/4248"，真实原因被吞掉。
_WARNED = set()
_ERR_NOTE = {
    400: "请求非法/模型名不存在",
    401: "API Key 无效或已失效",
    402: "账户余额不足/免费额度耗尽",
    403: "无权限访问该模型",
    404: "接口或模型不存在",
    410: "模型已下线，需更换 model 名",
    429: "限流：RPM 超限 或 配额已用尽",
    500: "服务端错误",
    503: "服务不可用",
}

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
        # 2026-10-22 体检：3 个智谱 Key 中只有这一个还有额度（另两个返回 429「余额不足」）。
        # RPM 默认保守值，可用 TRANSLATE_RPM_GLM47 调整；真限流时代码会自动放大退避时间。
        "key_env": "GLM_API_KEY",
        "model": "glm-4.7-flash",
        "rpm": int(os.environ.get("TRANSLATE_RPM_GLM47", "3")),
    },
    {
        # ⚠️ 2026-10-22 停用：
        # 1) meta/llama-3.1-8b-instruct 已于 2026-08-26 EOL，返回 HTTP 410
        # 2) 体检拉取 /v1/models 得到 83 个模型，但逐个实测全部 HTTP 404
        #    "Function ... Not found for account ..." → 该 NVIDIA 账号未订阅任何可用模型
        # 恢复条件：账号拿到 NIM 订阅后，把 enabled 改回 True 并换成实际可调用的模型名
        "name": "NVIDIA-Llama-3.1-8B",
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        "model": "meta/llama-3.1-8b-instruct",
        "rpm": 1,
        "enabled": False,
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

# 这些措辞 = 账户层面没救了（欠费/无资源包），重试多少次都没用
_FATAL_HINTS = ("余额不足", "无可用资源包", "请充值", "insufficient", "quota", "arrears")


async def _probe_engine(session, engine):
    """
    健康探测：发最小请求判断引擎状态，返回 (状态, 说明)。
    状态: "ok" 可用 | "busy" 临时限流（保留但降速） | "dead" 永久失效（剔除）

    踩坑：429 有两种截然不同的含义 ——
      ·「余额不足或无可用资源包，请充值」= 账号没钱，永久失效
      ·「该模型当前访问量过大，请您稍后再试」= 只是繁忙，稍后即可用
    早期版本不区分，把唯一活着的引擎也一起剔了，导致整轮翻译 0 产出。
    """
    url = engine["url"]() if callable(engine["url"]) else engine["url"]
    payload = {
        "model": engine["model"],
        "messages": [{"role": "user", "content": "Reply with: OK"}],
        "temperature": 0,
        "max_tokens": 8,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {engine['key']}",
    }

    last_status, last_detail = None, ""
    for attempt in range(3):                       # 429 值得重试，它经常只是瞬时高峰
        try:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=45)) as resp:
                if resp.status == 200:
                    return "ok", "可用"
                body = await resp.text()
                last_status = resp.status
                last_detail = _extract_detail(body)
                note = _ERR_NOTE.get(resp.status, "未知错误")
                low = last_detail.lower()
                if any(h in low for h in _FATAL_HINTS):
                    return "dead", f"HTTP {resp.status} ({note}) {last_detail}  ← 账号层面失效，需充值"
                if resp.status == 429 and attempt < 2:
                    await asyncio.sleep(15 * (attempt + 1))
                    continue
                return "dead", f"HTTP {resp.status} ({note}) {last_detail}"
        except Exception as e:
            last_status = "EXC"
            last_detail = f"{type(e).__name__}: {str(e)[:120]}"
            if attempt < 2:
                await asyncio.sleep(10)
                continue

    # 三次都被 429 挡回，但措辞不是「欠费」→ 判定为繁忙，保留引擎并降速
    if last_status == 429:
        return "busy", f"429 繁忙（非欠费，措辞：{last_detail[:60]}）→ 保留但降速"
    return "dead", f"{last_status} {last_detail}"


def _extract_detail(body):
    """从各家 API 的错误响应里抽出人话。"""
    import json as _json
    try:
        d = _json.loads(body)
    except Exception:
        return body[:120].replace("\n", " ")
    for k in ("message", "detail", "msg", "error_description"):
        if isinstance(d, dict) and d.get(k):
            return str(d[k])[:160]
    if isinstance(d, dict) and isinstance(d.get("error"), dict):
        return str(d["error"].get("message", ""))[:160]
    return str(d)[:160]


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
        "max_tokens": engine.get("max_tokens", 4096),
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {engine['key']}",
    }

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                body = await resp.text()
                note = _ERR_NOTE.get(resp.status, "未知错误")
                # 同一引擎的同类错误只报一次详情，避免刷屏，但必须可见
                key = (engine["name"], resp.status)
                if key not in _WARNED:
                    _WARNED.add(key)
                    print(f"  🚨 [{engine['name']}] HTTP {resp.status} ({note}): {body[:220]}")
                return None
            data = await resp.json()
            content = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        key = (engine["name"], "EXC")
        if key not in _WARNED:
            _WARNED.add(key)
            print(f"  🚨 [{engine['name']}] 请求异常 {type(e).__name__}: {str(e)[:200]}")
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


# ── 时间预算 ──────────────────────────────────────────
# GitHub Actions job 硬超时 6 小时；翻译任务常被前面步骤吃掉时间。
# 到点主动停 → 写回 tools.json → 后续步骤照常 commit，下一轮接着翻剩下的。
TRANSLATE_BUDGET_MIN = float(os.environ.get("TRANSLATE_BUDGET_MIN", "150"))
_BUDGET_DEADLINE = None  # 由 run_translation() 在开工时设定


def _start_budget():
    global _BUDGET_DEADLINE
    _BUDGET_DEADLINE = time.time() + TRANSLATE_BUDGET_MIN * 60
    print(f"⏱ 翻译时间预算: {TRANSLATE_BUDGET_MIN:.0f} 分钟（到点自动收尾，剩余下轮继续）")


def _over_budget():
    if _BUDGET_DEADLINE is None:
        return False
    return time.time() >= _BUDGET_DEADLINE


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
    ssl_ctx = _ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = _ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    session = aiohttp.ClientSession(connector=connector)
    eng_stats = {"ok": 0, "fail": 0}  # 单引擎统计
    stats[f"_eng_{name}"] = eng_stats

    try:
        while True:
            # 时间预算：到点就停，已翻完的照常落盘提交，剩下的留给下一轮。
            # 曾踩坑：GitHub Actions job 6 小时硬超时，超时的成果全部作废、白白重跑。
            if _over_budget():
                break
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
                    # 退避放大：多数失败是 429 限流，2s/4s 太短，重试等于白刷
                    wait = (5, 20)[attempt - 1] if attempt <= 2 else 30
                    print(f"  [{name}] ⚠️ 批次 {batch_idx} 重试 {attempt+1}/{MAX_RETRIES}（退避 {wait}s）", flush=True)
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

    # 3.5 排序：新发布的先翻
    # 产能有限（当前仅一个免费引擎）时，若按数组原序翻，会先啃历史存量、
    # 而每天新增的工具永远排在后面 —— 缺口只会越拉越大。改为按发布时间倒序，
    # 保证「今天上新的工具明天就有中文」，历史欠账慢慢补。
    if os.environ.get("TRANSLATE_NEWEST_FIRST", "1").strip() not in ("0", "false", "False"):
        to_translate.sort(key=lambda x: (tools[x[0]].get("createdAt") or ""), reverse=True)
        dates = [(tools[x[0]].get("createdAt") or "")[:10] for x in to_translate]
        print(f"🆕 已按发布时间倒序：本轮从 {dates[0]} 的新工具开始，"
              f"末尾是 {dates[-1]} 的历史欠账")

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
        if eng.get("enabled") is False:
            print(f"  ⏭ {eng['name']}: 已停用（{eng.get('disabled_reason', '见配置注释')}）")
            continue
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

    # 5.5 健康探测：逐个发 1 条最小请求，坏引擎直接剔除
    # 曾踩坑：4 引擎全部 429/410 时仍跑满 425 批 × 3 小时，最后只成功 50 条。
    print("🔍 健康探测中...")
    healthy, busy = [], []
    async with aiohttp.ClientSession() as probe_sess:
        for e in active:
            state, note = await _probe_engine(probe_sess, e)
            icon = {"ok": "✅", "busy": "🕐", "dead": "❌"}[state]
            print(f"    {icon} {e['name']}: {note}")
            if state == "ok":
                healthy.append(e)
            elif state == "busy":
                e = {**e, "rpm": 1}   # 繁忙引擎降速参与，别浪费它的额度
                busy.append(e)
    active = healthy + busy
    if busy and not healthy:
        print(f"    ⚠️ 无完全可用引擎，仅保留 {len(busy)} 个繁忙引擎降速运行 "
              f"—— 若持续 429，本轮产出会很低")

    if not active:
        print("❌ 全部引擎不可用，跳过本轮翻译（保留已有中文，不阻塞后续步骤）")
        _write_slim(tools)
        return tools

    print(f"🚀 启动 {len(active)} 个并发引擎:")
    for e in active:
        print(f"    {e['name']} (RPM={e['rpm']})")
    _start_budget()

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
    if _over_budget() and remaining:
        print(f"\n⏱ 时间预算用尽：本轮翻译 {stats['translated']}/{total} 条，"
              f"剩余 {remaining} 条留给下一轮（本轮成果已落盘，会正常提交）")
    else:
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
