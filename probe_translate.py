#!/usr/bin/env python3
"""
翻译引擎体检 —— 一次性诊断每个 API Key 的真实状态，并自动寻找可用替代模型。

背景：日常更新跑了 3 小时只成功 50/4248 条翻译，且日志里 429 分支被静默吞掉、
毫无报错。本脚本用于在不猜测的前提下，把每个引擎的死因挖出来。

用法：python probe_translate.py
"""
import asyncio
import json
import os
import re

import aiohttp

ERR_NOTE = {
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

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"


def extract_detail(body):
    try:
        d = json.loads(body)
    except Exception:
        return body[:150].replace("\n", " ")
    if isinstance(d, dict):
        for k in ("message", "detail", "msg", "error_description"):
            if d.get(k):
                return str(d[k])[:200]
        if isinstance(d.get("error"), dict):
            return str(d["error"].get("message"))[:200]
    return str(d)[:200]


async def test_model(session, url, key, model, extra_note=""):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "temperature": 0,
        "max_tokens": 8,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status == 200:
                d = await resp.json()
                out = ""
                try:
                    out = d["choices"][0]["message"]["content"].strip()[:20]
                except Exception:
                    pass
                return "OK", f"可用 ✓ 回显「{out}」{extra_note}"
            body = await resp.text()
            return "FAIL", f"HTTP {resp.status} ({ERR_NOTE.get(resp.status,'未知')}) {extract_detail(body)[:120]}"
    except Exception as e:
        return "FAIL", f"{type(e).__name__}: {str(e)[:120]}"


async def list_nvidia_models(session, key):
    """NVIDIA 是 OpenAI 兼容接口，/v1/models 可直接列出全部可用模型，不用猜。"""
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with session.get(NVIDIA_BASE + "/models", headers=headers,
                               timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status != 200:
                return None, f"HTTP {resp.status} {extract_detail(await resp.text())[:120]}"
            d = await resp.json()
            return [m["id"] for m in d.get("data", [])], None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def pick_translation_candidates(models):
    """从可用模型里挑适合「短文本英译中」的：优先 instruct/chat，避开超大与推理型。"""
    if not models:
        return []
    skip = ("rerank", "embed", "guard", "safety", "vision", "image", "video",
            "speech", "tts", "whisper", "clip", "diffusion", "flux", "sd-",
            "nim-", "reasoning", "r1", "distill")
    scored = []
    for m in models:
        low = m.lower()
        if any(s in low for s in skip):
            continue
        if not any(k in low for k in ("instruct", "chat")):
            continue
        s = 0
        # 小模型更适合批量短翻译，也更省配额
        for pat, pts in ((("3b", "2b", "1b", "mini", "8b"), 6),
                         (("flash", "lite", "nano", "small"), 4),
                         (("qwen", "glm", "deepseek"), 3),   # 中文语感更好
                         (("70b", "405b", "large"), -3)):
            if any(p in low for p in pat):
                s += pts
        scored.append((s, m))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [m for _s, m in scored[:8]]


async def main():
    print("=" * 72)
    print("翻译引擎体检报告")
    print("=" * 72)

    glm_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    targets = [
        ("GLM-4.6v",      glm_url, os.environ.get("GLM46_API_KEY", ""), "glm-4.6v"),
        ("GLM-4.5-Air",   glm_url, os.environ.get("GLM45_API_KEY", ""), "glm-4.5-air"),
        ("GLM-4.7-Flash", glm_url, os.environ.get("GLM_API_KEY", ""),   "glm-4.7-flash"),
    ]
    nv_key = os.environ.get("NVIDIA_API_KEY", "")

    async with aiohttp.ClientSession() as sess:
        print("\n【一】已配置引擎逐个测试")
        print("-" * 72)
        for name, url, key, model in targets:
            if not key:
                print(f"  ⚪ {name:16s} 未配置 Key")
                continue
            masked = key[:8] + "…" + key[-4:]
            st, note = await test_model(sess, url, key, model)
            flag = "✅" if st == "OK" else ("🚨" if ("HTTP 429" in note or "HTTP 402" in note or "HTTP 401" in note) else "❌")
            print(f"  {flag} {name:16s} ({model})")
            print(f"       Key {masked} → {note}")

        print(f"\n  NVIDIA key: {'已配置' if nv_key else '未配置'}")
        if nv_key:
            st, note = await test_model(sess, NVIDIA_BASE + "/chat/completions",
                                        nv_key, "meta/llama-3.1-8b-instruct")
            print(f"  {'✅' if st=='OK' else '❌'} NVIDIA-Llama-3.1-8B (当前配置的模型)")
            print(f"       → {note}")

            print("\n【二】向 NVIDIA 查询当前可用的全部模型")
            print("-" * 72)
            models, err = await list_nvidia_models(sess, nv_key)
            if err:
                print("  ❌ 无法获取模型列表:", err)
            else:
                print(f"  共 {len(models)} 个模型可用")
                cands = pick_translation_candidates(models)
                print(f"\n  自动筛选出适合短文本翻译的候选 {len(cands)} 个，逐个实测：")
                working = []
                for m in cands:
                    st, note = await test_model(sess, NVIDIA_BASE + "/chat/completions", nv_key, m)
                    print(f"    {'✅' if st=='OK' else '❌'} {m}")
                    print(f"         {note}")
                    if st == "OK":
                        working.append(m)
                    await asyncio.sleep(0.5)
                if working:
                    print("\n  🎯 建议替换 translate_concurrent.py 中 NVIDIA 引擎的 model 为：")
                    print(f"     \"model\": \"{working[0]}\"")
                else:
                    print("\n  ⚠️ 全部候选模型均不可用，NVIDIA 通道建议停用")

    print("\n" + "=" * 72)
    print("体检结束")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
