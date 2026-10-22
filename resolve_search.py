"""基于 Bing RSS 的「产品名 → 真实官网」反查解析器。

设计原则（关键）：宁可漏，不可错。
三步把关：
  1. Bing RSS 搜索产品名（+ 解码 bing.com/ck/a 的 base64 包装链接）
  2. 候选域名打分：排除聚合站/社交站；域名包含产品名 token 的加分
  3. 访问候选官网取 <title>/og:site_name，验证与产品名匹配后才落盘

用法：
  python resolve_search.py --validate 20        # 用已知官网做标准答案验证准确率
  python resolve_search.py --limit 200 --apply  # 批量解析并写回 tools.json
"""
import argparse
import base64
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

try:
    from curl_cffi import requests as creq
except Exception:
    creq = None

# 明显不可能官网的域名
BLACKLIST = {
    "producthunt.com", "wikipedia.org", "linkedin.com", "twitter.com", "x.com",
    "facebook.com", "instagram.com", "youtube.com", "reddit.com", "medium.com",
    "crunchbase.com", "g2.com", "capterra.com", "trustradius.com", "getapp.com",
    "softwareadvice.com", "alternativeto.net", "appsumo.com", "quora.com",
    "glassdoor.com", "indiehackers.com", "news.ycombinator.com", "substack.com",
    "discord.com", "telegram.me", "t.me", "play.google.com", "apps.apple.com",
    "github.com", "gitlab.com", "npmjs.com", "pypi.org", "docker.com",
    "microsoft.com", "bing.com", "amazon.com", "aliexpress.com", "apple.com",
    "google.com", "openai.com", "anthropic.com", "notion.so", "zapier.com",
    "toolify.ai", "futurepedia.io", "theresanaiforthat.com", "topai.tools",
    "scribd.com", "slideshare.net", "issuu.com", "behance.net", "dribbble.com",
}


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def root(host):
    host = (host or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def host_of(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def norm_tokens(name):
    return [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) >= 2]


def http_get(url, timeout=25):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    try:
        if creq:
            r = creq.get(url, impersonate="chrome", timeout=timeout, allow_redirects=True)
            return r.status_code, r.text[:200000]
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as x:
            return x.status, x.read().decode("utf-8", "ignore")[:200000]
    except Exception as e:
        return getattr(e, "code", 0) or 0, ""


# ---------------- 1) Bing RSS 搜索 ----------------

def bing_html_search(query):
    """备用源：Bing HTML 版（RSS 偶发返回空）"""
    url = "https://www.bing.com/search?q=%s&count=30" % urllib.parse.quote(query)
    code, html = http_get(url)
    if code != 200:
        return []
    out = []
    for m in re.finditer(r'href="(https?://[^"]+)"', html):
        u = m.group(1)
        if any(x in u for x in ("bing.com", "microsoft.com", "msn.com", "live.com")):
            u = unwrap_bing(u)
            if not u:
                continue
        out.append(u)
    uniq = []
    for u in out:
        if u not in uniq:
            uniq.append(u)
    return uniq


def bing_search(query):
    url = "https://www.bing.com/search?q=%s&format=rss&count=15" % urllib.parse.quote(query)
    code, body = http_get(url)
    if code != 200 or "<item" not in body:
        return []
    out = []
    for m in re.finditer(r"<item>(.*?)</item>", body, re.S):
        blk = m.group(1)
        lm = re.search(r"<link>(.*?)</link>", blk)
        tm = re.search(r"<title>(.*?)</title>", blk, re.S)
        if not lm:
            continue
        link = lm.group(1).strip()
        title = re.sub(r"<[^>]+>", "", (tm.group(1) if tm else "")).strip()
        real = unwrap_bing(link)
        if real:
            out.append(real)
    return out


def unwrap_bing(link):
    """Bing 会把真实 URL base64 包在 https://www.bing.com/ck/a?...&u=a1xxx 里"""
    if "bing.com/ck/a" not in link:
        return link
    m = re.search(r"[?&]u=a1([A-Za-z0-9_\-]+)", link)
    if not m:
        return ""
    b = m.group(1)
    b += "=" * (-len(b) % 4)
    try:
        decoded = base64.urlsafe_b64decode(b).decode("utf-8", "ignore")
    except Exception:
        return ""
    return decoded if decoded.startswith("http") else ""


# ---------------- 2) 候选打分 ----------------

def name_domain_match(name, base):
    """硬性要求：域名必须与产品名有关联，否则一律丢弃（这是精度的关键）"""
    nb = base.replace("-", "").replace("_", "")
    nn = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    toks = norm_tokens(name)
    if not nn or not nb:
        return False
    if len(nn) >= 4 and (nn in nb or nb in nn):
        return True
    # 首个实词 token 足够长时必须出现在域名里
    if toks and len(toks[0]) >= 4 and toks[0] in nb:
        return True
    return False


def score_candidate(url, name):
    h = host_of(url)
    r = root(h)
    if not r or r in BLACKLIST:
        return -99
    base = r.split(".")[0]
    if not name_domain_match(name, base):
        return -99
    toks = norm_tokens(name)
    s = 0
    joined = "".join(toks)
    nb = base.replace("-", "").replace("_", "")
    if re.sub(r"[^a-z0-9]", "", name.lower()) == nb:
        s += 10
    if joined and joined in nb:
        s += 4
    if toks and len(toks[0]) >= 4 and toks[0] in nb:
        s += 3
    s += sum(1 for t in toks[1:] if len(t) >= 4 and t in nb)
    if base.count("-") == 0 and len(base) <= len(joined):
        s += 1
    return s


# ---------------- 3) 官网验证 ----------------

def verify_site(url, name):
    """访问候选官网，确认标题里确实出现产品名，才算通过"""
    code, html = http_get(url, timeout=20)
    if code != 200 or not html:
        return False, "HTTP%s" % (code or 0)
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        title = re.sub(r"<[^>]+>", " ", m.group(1))
    og = re.search(r'og:site_name"\s+content="([^"]+)"', html)
    if og:
        title += " " + og.group(1)
    title = urllib.parse.unquote(title)
    tl = re.sub(r"[^a-z0-9]+", " ", title.lower())
    toks = norm_tokens(name)
    hit = sum(1 for t in toks if len(t) >= 3 and t in tl)
    base = re.sub(r"[^a-z0-9]", "", name.lower())
    if base and base in re.sub(r"[^a-z0-9]", "", title.lower()):
        hit += 2
    ok = hit >= 1 and len(toks) > 0
    return ok, (title.strip()[:60] or "no-title") + "|hit=%d" % hit


def candidate_pool(name, tagline=""):
    """多组查询取并集：裸名搜往往被词典/新闻站占据，加限定词能显著改善"""
    queries = ['"%s"' % name.strip('"')]
    if tagline:
        head = " ".join(norm_tokens(tagline)[:6])
        if head:
            queries.append('%s %s' % (name, head))
    queries.append("%s official website" % name)
    pool, seen = [], set()
    for q in queries[:3]:
        got = bing_search(q)
        if len(got) < 5:
            got = got + bing_html_search(q)
        for item in got:
            url = item[0] if isinstance(item, tuple) else item
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            if url not in seen:
                seen.add(url)
                pool.append(url)
        time.sleep(0.3)
    return pool


def resolve_one(name, tagline="", do_verify=True):
    pool = candidate_pool(name, tagline)
    scored = []
    for url in pool:
        s = score_candidate(url, name)
        if s > -90:
            scored.append((s, url))
    scored.sort(key=lambda x: -x[0])
    fallback = None
    for s, url in scored[:4]:
        if not url.startswith("http"):
            url = "https://" + url
        if do_verify:
            ok, note = verify_site(url, name)
            if ok:
                return url, "OK verify(%+d) %s" % (s, note[:40])
            if fallback is None:
                fallback = (url, "score(%+d) 未过标题验证" % s)
        else:
            return url, "OK score(%+d)" % s
    return None, "rejected (%d 候选/%d 合格但标题不符)" % (len(pool), len(scored))
    if not scored:
        dbg = "; ".join(host_of(u) for u in pool[:6])
        return None, "no-match (%d 候选) [%s]" % (len(pool), dbg[:70])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", type=int, default=0, help="用已知官网做准确率验证（条数）")
    ap.add_argument("--limit", type=int, default=0, help="批量解析条数")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tools", default="tools.json")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    tools = load_json(args.tools, [])
    tools = tools if isinstance(tools, list) else tools.get("tools", [])
    wmap = load_json("website_map.json", {})
    wfail = load_json("website_fail_search.json", {})
    print("tools:", len(tools), "| 已解析:", len(wmap), "| 历史失败:", len(wfail))

    if args.validate:
        truth = {k: v for k, v in wmap.items() if "producthunt.com" not in str(v)}
        by_id = {str(t.get("id")): t for t in tools}
        ids = [i for i in truth if i in by_id]
        random.seed(11)
        random.shuffle(ids)
        ids = ids[: args.validate]
        ok = wrong = 0
        findable = 0
        findable_ok = 0
        print("验证样本:", len(ids))
        print()
        for i, tid in enumerate(ids, 1):
            t = by_id[tid]
            name = t.get("name") or ""
            tagline = t.get("tagline") or ""
            truth_root = root(host_of(truth[tid]))
            tb = truth_root.split(".")[0]
            can = name_domain_match(name, tb) and tb not in BLACKLIST
            got_strict, note = resolve_one(name, tagline)
            gs = root(host_of(got_strict)) if got_strict else ""
            hit = gs == truth_root
            ok += bool(hit)
            if got_strict and not hit:
                wrong += 1
            if can:
                findable += 1
                findable_ok += bool(hit)
            print("[%d/%d] %-26s 得到=%-22s 答案=%-20s %s %s" % (
                i, len(ids), name[:26], gs or "-", truth_root,
                "✔" if hit else ("✘" + ("理论可找" if can else "(托管域名,不可找)")), note[:40]))
            time.sleep(args.delay)
        print()
        print("=" * 60)
        accepted = ok + wrong
        print("总体覆盖（写对）: %d/%d = %.0f%%" % (ok, len(ids), ok / len(ids) * 100 if ids else 0))
        print("接受写入 %d 条，其中错配 %d 条 => 精确率 %.0f%%" % (
            accepted, wrong, (ok / accepted * 100) if accepted else 0))
        print("其中「域名含产品名」理论上可找到的: %d 条，成功 %d 条 = %.0f%%" % (
            findable, findable_ok, findable_ok / findable * 100 if findable else 0))
        print("（其余 %d 条官网托管在 railway/vercel/google 等通用域名，无法从名字反查）" % (len(ids) - findable))
        return

    # 批量模式
    pending = []
    for t in tools:
        tid = str(t.get("id"))
        site = t.get("website") or ""
        if "producthunt.com/r/" not in site:
            continue
        if tid in wmap:
            continue
        pending.append(t)
    todo = pending[: args.limit] if args.limit else pending
    print("待解析:", len(pending), "-> 本次:", len(todo))
    nok = 0
    t0 = time.time()
    for i, t in enumerate(todo, 1):
        tid = str(t.get("id"))
        name = t.get("name") or ""
        got, note = resolve_one(name)
        if got:
            wmap[tid] = got
            nok += 1
        else:
            wfail[tid] = int(time.time())
        print("[%d/%d] %-26s -> %-30s %s (%.1fs/条)" % (
            i, len(todo), name[:26], (got or "-")[:30], note[:34],
            (time.time() - t0) / i), flush=True)
        if i % 25 == 0:
            json.dump(wmap, open("website_map.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            json.dump(wfail, open("website_fail_search.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        time.sleep(args.delay)
    json.dump(wmap, open("website_map.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(wfail, open("website_fail_search.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    dt = time.time() - t0
    print()
    print("成功: %d/%d = %.0f%%  耗时 %.0fs" % (nok, len(todo), nok / len(todo) * 100 if todo else 0, dt))
    if len(pending) > len(todo) and todo:
        print("剩余 %d 条预计需 %.1f 小时" % (
            len(pending) - len(todo), (len(pending) - len(todo)) * dt / len(todo) / 3600))

    if args.apply:
        n = 0
        for t in tools:
            tid = str(t.get("id"))
            if tid in wmap and "producthunt.com" not in wmap[tid]:
                t["website"] = wmap[tid]
                n += 1
        json.dump(tools, open(args.tools, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        slim = load_json("tools-slim.json", None)
        if slim:
            for t in slim:
                tid = str(t.get("id"))
                if tid in wmap and "producthunt.com" not in wmap[tid]:
                    t["website"] = wmap[tid]
            json.dump(slim, open("tools-slim.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        print("已写回 %d 条真实官网" % n)


if __name__ == "__main__":
    main()
