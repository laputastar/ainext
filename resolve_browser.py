"""用真实浏览器解析 PH /r/ 跟踪链 -> 真实官网（pilot / 批量两用）。

用法：
  python resolve_browser.py --limit 20          # 先跑 20 条看成功率
  python resolve_browser.py --limit 300 --workers 5 --apply   # 批量写回 tools.json

输出：website_map.json（id -> 真实官网），website_fail_browser.json（失败时间戳，720 小时内不重试）
"""
import argparse
import json
import os
import random
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("需要 playwright：pip install playwright && playwright install chromium")
    sys.exit(2)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 隐藏自动化痕迹，降低被 Cloudflare 判为 bot 的概率
STEALTH = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || {runtime: {}};
"""


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def pick_channel():
    """优先用完整 Chromium（新 headless 模式），比 headless shell 更难被识别"""
    return os.environ.get("PW_CHANNEL") or None


def resolve_one(page, ph_url, timeout=30000):
    try:
        page.goto(ph_url, wait_until="domcontentloaded", timeout=timeout)
        try:
            page.wait_for_url(lambda u: "producthunt.com" not in u, timeout=20000)
        except Exception:
            pass
        final = page.url
        if "producthunt.com" not in final:
            return final, "OK"
        return final, "BLOCKED"
    except Exception as e:
        return str(e)[:80], "ERR"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--tools", default="tools.json")
    ap.add_argument("--apply", action="store_true", help="写回 tools.json（默认仅输出统计）")
    ap.add_argument("--retry-hours", type=int, default=720)
    args = ap.parse_args()

    tools = load_json(args.tools, [])
    tools = tools if isinstance(tools, list) else tools.get("tools", [])
    print("tools 总数:", len(tools))

    wmap = load_json("website_map.json", {})
    wfails = load_json("website_fail_browser.json", {})
    print("website_map 已有:", len(wmap), "| 已有失败记录:", len(wfails))

    threshold = time.time() - args.retry_hours * 3600
    pending = []
    for t in tools:
        tid = str(t["id"])
        site = t.get("website") or ""
        if "producthunt.com/r/" not in site:
            continue
        if tid in wmap:
            continue
        if tid in wfails and wfails[tid] > threshold:
            continue
        pending.append(t)

    print("待解析:", len(pending), "-> 本次处理:", min(args.limit, len(pending)))
    todo = pending[: args.limit] if args.limit else pending
    if not todo:
        print("没有可处理的条目")
        return

    ok = fail = 0
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel=pick_channel(),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        ctx = browser.new_context(
            user_agent=UA, locale="en-US", viewport={"width": 1366, "height": 768}
        )
        ctx.add_init_script(STEALTH)
        page = ctx.new_page()

        for i, t in enumerate(todo, 1):
            tid = str(t["id"])
            final, status = resolve_one(page, t["website"])
            if status == "OK":
                wmap[tid] = final
                ok += 1
            else:
                wfails[tid] = time.time()
                fail += 1
            est = time.time() - t0
            print(
                f"[{i}/{len(todo)}] {status:7s} {str(t.get('name'))[:26]:28s} -> {final[:60]}  ({(est/i):.1f}s/条)",
                flush=True,
            )
            # 每 25 条落盘一次，防止中断丢进度
            if i % 25 == 0:
                with open("website_map.json", "w", encoding="utf-8") as f:
                    json.dump(wmap, f, ensure_ascii=False, indent=2)
                with open("website_fail_browser.json", "w", encoding="utf-8") as f:
                    json.dump(wfails, f, ensure_ascii=False, indent=2)

        browser.close()

    with open("website_map.json", "w", encoding="utf-8") as f:
        json.dump(wmap, f, ensure_ascii=False, indent=2)
    with open("website_fail_browser.json", "w", encoding="utf-8") as f:
        json.dump(wfails, f, ensure_ascii=False, indent=2)

    total = ok + fail
    dt = time.time() - t0
    print()
    print("=" * 60)
    print(f"成功率: {ok}/{total} = {(ok/total*100 if total else 0):.0f}%")
    print(f"耗时: {dt:.0f}s（{dt/total:.1f}s/条）")
    if ok and len(pending) > total:
        print(f"按此速度剩余 {len(pending)-total} 条约需 {(len(pending)-total)*dt/total/3600:.1f} 小时")

    if args.apply:
        n = 0
        for t in tools:
            tid = str(t["id"])
            if tid in wmap and "producthunt.com" not in wmap[tid]:
                t["website"] = wmap[tid]
                n += 1
        with open(args.tools, "w", encoding="utf-8") as f:
            json.dump(tools, f, ensure_ascii=False, indent=2)
        # 同步精简版
        slim = load_json("tools-slim.json", None)
        if slim:
            for t in slim:
                tid = str(t["id"])
                if tid in wmap and "producthunt.com" not in wmap[tid]:
                    t["website"] = wmap[tid]
            with open("tools-slim.json", "w", encoding="utf-8") as f:
                json.dump(slim, f, ensure_ascii=False, indent=2)
        print(f"已写回 {n} 条真实官网到 {args.tools}")


if __name__ == "__main__":
    main()
