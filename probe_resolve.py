"""多策略解析 PH /r/ 跟踪链 —— 对照实验（pilot）。

核心设计：用 website_map.json 里已确认的真实官网作为「标准答案」，
逐个验证每种策略能否从 PH /r/ 链接还原出正确的官网域名。

用法：python probe_resolve.py --n 12
"""
import argparse
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request

PH_TOKEN = "dQ-Dxt9-u5cMHSrAYe04He1M0OdWZaR9a96Vh3nofhk"
API = "https://api.producthunt.com/v2/api/graphql"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 聚合站 / 社交站，搜索结果里命中这些就算无有效答案
BLACKLIST = {
    "producthunt.com", "wikipedia.org", "linkedin.com", "twitter.com", "x.com",
    "facebook.com", "instagram.com", "youtube.com", "reddit.com", "medium.com",
    "github.com", "gitlab.com", "crunchbase.com", "g2.com", "capterra.com",
    "trustradius.com", "getapp.com", "softwareadvice.com", "alternativeto.net",
    "appsumo.com", "play.google.com", "apps.apple.com", "discord.com",
    "substack.com", "notion.site", "redditstatic.com", "google.com",
    "techcrunch.com", "forbes.com", "venturebeat.com", "quora.com",
    "glassdoor.com", "indiehackers.com", "news.ycombinator.com", "slack.com",
    "toolify.ai", "futurepedia.io", "theresanaiforthat.com",
}

try:
    import requests
except Exception:
    requests = None

try:
    from curl_cffi import requests as creq
except Exception:
    creq = None


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
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def host_of(url):
    try:
        h = urllib.parse.urlparse(url).hostname or ""
        return h.lower()
    except Exception:
        return ""


def ph_api_rlinks(ids):
    """批量取 post(id) 的 website 字段（PH /r/ 链接）"""
    if not ids:
        return {}
    out = {}
    for i in range(0, len(ids), 10):
        chunk = ids[i:i + 10]
        frag = " ".join(
            'p%s: post(id:"%s"){ id website }' % (j, pid) for j, pid in enumerate(chunk)
        )
        body = json.dumps({"query": "{%s}" % frag}).encode()
        req = urllib.request.Request(
            API, data=body,
            headers={"Authorization": "Bearer " + PH_TOKEN,
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
            data = d.get("data") or {}
            for j, pid in enumerate(chunk):
                v = data.get("p%d" % j)
                if v and v.get("website"):
                    out[str(pid)] = v["website"]
        except Exception as e:
            print("  PH API 批次失败:", str(e)[:120])
    return out


# ---------------- 策略实现 ----------------

def s_curl_cffi(url, name):
    if not creq:
        return None, "no-lib"
    try:
        r = creq.get(url, impersonate="chrome", timeout=25, allow_redirects=True)
        final = str(r.url)
        if "producthunt.com" in final:
            return None, "HTTP %s" % r.status_code
        return final, "OK"
    except Exception as e:
        return None, type(e).__name__ + ":" + str(e)[:60]


def s_requests(url, name):
    if not requests:
        return None, "no-lib"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25,
                         allow_redirects=True)
        final = r.url
        if "producthunt.com" in final:
            return None, "HTTP %s" % r.status_code
        return final, "OK"
    except Exception as e:
        return None, type(e).__name__


def s_jina(url, name):
    try:
        req = urllib.request.Request(
            "https://r.jina.ai/" + url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode("utf-8", "ignore")
        m = re.search(r"URL Source:\s*(\S+)", txt)
        cand = m.group(1) if m else None
        if cand and "producthunt.com" not in cand:
            return cand, "OK"
        return None, (cand or "no-source")
    except Exception as e:
        return None, type(e).__name__ + ":" + str(e)[:60]


def s_wayback(url, name):
    try:
        code = url.rstrip("/").split("/")[-1]
        api = ("http://web.archive.org/cdx/search/cdx?url=producthunt.com%2Fr%2F"
               + urllib.parse.quote(code) + "&output=json&limit=5&fl=statuscode,redirect")
        with urllib.request.urlopen(api, timeout=40) as r:
            rows = json.loads(r.read().decode())
        for row in rows[1:]:
            target = row[1] if len(row) > 1 else ""
            if target and "producthunt.com" not in target:
                return target, "OK"
        return None, "no-snapshot"
    except Exception as e:
        return None, type(e).__name__ + ":" + str(e)[:40]


def _search_pick(cands, name):
    tok = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) >= 2]
    scored = []
    for u in cands:
        h = root(host_of(u))
        if not h or h in BLACKLIST:
            continue
        s = 0
        base = h.split(".")[0]
        if tok and tok[0] and tok[0] in base:
            s += 3
        s += sum(1 for t in tok if t and t in base)
        scored.append((s, u, h))
    if not scored:
        return None, "no-candidate"
    scored.sort(key=lambda x: -x[0])
    return scored[0][1], "OK(%d)" % scored[0][0]


def _bing(search_name):
    try:
        u = "https://www.bing.com/search?q=" + urllib.parse.quote(search_name) + "&format=rss&count=10"
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30) as r:
            xml = r.read().decode("utf-8", "ignore")
        return [x for x in re.findall(r"<link>(https?://[^<]+)</link>", xml)][1:]
    except Exception:
        return []


def _ddg(search_name):
    try:
        body = urllib.parse.urlencode({"q": search_name}).encode()
        with urllib.request.urlopen(
            urllib.request.Request("https://html.duckduckgo.com/html/", data=body,
                                   headers={"User-Agent": UA}), timeout=30) as r:
            html = r.read().decode("utf-8", "ignore")
        out = []
        for m in re.finditer(r'uddg=([^&"]+)', html):
            out.append(urllib.parse.unquote(m.group(1)))
        return out
    except Exception:
        return []


def _mojeek(search_name):
    try:
        u = "https://www.mojeek.com/search?q=" + urllib.parse.quote(search_name)
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30) as r:
            html = r.read().decode("utf-8", "ignore")
        return re.findall(r'<a[^>]+class="ob"[^>]+href="(https?://[^"]+)"', html) or \
               re.findall(r'href="(https?://[^"]+)"', html)[:15]
    except Exception:
        return []


def mk_search(fn):
    def f(url, name):
        cands = fn(name)
        res, note = _search_pick(cands, name)
        return res, "%s|%d条" % (note, len(cands))
    return f


STRATEGIES = [
    ("1 curl_cffi(TLS伪装)", s_curl_cffi),
    ("2 requests(基线)", s_requests),
    ("3 jina.ai 代理", s_jina),
    ("4 wayback 快照", s_wayback),
    ("5 Bing 搜索", mk_search(_bing)),
    ("6 DuckDuckGo", mk_search(_ddg)),
    ("7 Mojeek", mk_search(_mojeek)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tools", default="tools.json")
    args = ap.parse_args()

    tools = load_json(args.tools, [])
    tools = tools if isinstance(tools, list) else tools.get("tools", [])
    wmap = load_json("website_map.json", {})
    truth_map = {k: v for k, v in wmap.items() if "producthunt.com" not in str(v)}
    print("tools:", len(tools), "| 标准答案库:", len(truth_map))

    by_id = {str(t.get("id")): t for t in tools}
    cands = [tid for tid in truth_map if tid in by_id]
    random.seed(args.seed)
    random.shuffle(cands)
    cands = cands[: args.n]
    print("抽样已确认真实官网的工具:", len(cands))

    print("从 PH API 取当前 /r/ 链接 ...")
    rlinks = ph_api_rlinks(cands)
    samples = [(tid, truth_map[tid], rlinks.get(tid)) for tid in cands if rlinks.get(tid)]
    print("拿到 /r/ 链接:", len(samples), "/", len(cands))
    if not samples:
        return

    print()
    stats = {name: {"hit": 0, "right": 0, "res": []} for name, _ in STRATEGIES}
    for i, (tid, truth, rlink) in enumerate(samples, 1):
        tool = by_id[tid]
        name = tool.get("name") or "?"
        truth_root = root(host_of(truth))
        print("--- [%d/%d] %s | 正确答案: %s" % (i, len(samples), name[:30], truth_root))
        for sname, fn in STRATEGIES:
            t0 = time.time()
            try:
                got, note = fn(rlink, name)
            except Exception as e:
                got, note = None, "EXC"
            dt = time.time() - t0
            gr = root(host_of(got)) if got else ""
            ok = bool(gr) and gr == truth_root
            st = stats[sname]
            if got:
                st["hit"] += 1
            if ok:
                st["right"] += 1
            st["res"].append(dt)
            flag = "✔" if ok else ("~" if gr else "✘")
            print("    %s %-22s %-8s -> %-28s %s (%.1fs)" % (
                flag, sname, note[:8], gr or "-", ("≠ " + truth_root) if not ok else "", dt))
        time.sleep(0.5)

    print()
    print("=" * 68)
    print("%-22s %8s %8s %10s" % ("策略", "出结果", "正确", "平均耗时"))
    print("-" * 68)
    for sname, _ in STRATEGIES:
        st = stats[sname]
        avg = sum(st["res"]) / len(st["res"]) if st["res"] else 0
        print("%-22s %5d/%2d %5d/%2d %8.1fs" % (
            sname, st["hit"], len(samples), st["right"], len(samples), avg))
    print("=" * 68)
    best = max(stats.items(), key=lambda kv: kv[1]["right"])
    print("最佳策略: %s  正确率 %.0f%%" % (best[0], best[1]["right"] / len(samples) * 100))


if __name__ == "__main__":
    main()
