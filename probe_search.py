"""搜索端点可达性探针（pilot）。

目的：确认在 GitHub Actions 出口 IP 上，哪些搜索引擎端点能真正返回可用的搜索结果。
输出：每个端点的 HTTP 状态 / 可用查询数 / 去重候选数 / 前若干条候选 URL。
"""
import argparse
import json
import re
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ACC = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def get(url, data=None, timeout=25):
    h = {"User-Agent": UA, "Accept": ACC, "Accept-Language": "en-US,en;q=0.9"}
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        return getattr(e, "code", 0), body


def extract_links(html, exclude):
    out = []
    for m in re.finditer(r'https?://[^\s"\'<>\\]{8,}', html):
        u = m.group(0).rstrip(".,);]")
        h = (urllib.parse.urlparse(u).hostname or "").lower()
        if any(x in h for x in exclude):
            continue
        if u not in out:
            out.append(u)
    return out


def enc(q):
    return urllib.parse.quote(q)


# (名称, 是否 JSON API, 排除域名关键字, 建 URL 函数)
ENDPOINTS = [
    ("Bing RSS", True, ["bing.", "microsoft.", "msn."],
     lambda q: ("https://www.bing.com/search?q=%s&format=rss" % enc(q), None)),
    ("Bing HTML", False, ["bing.", "microsoft.", "msn.", "w3.org"],
     lambda q: ("https://www.bing.com/search?q=%s&count=20" % enc(q), None)),
    ("Google", False, ["google.", "gstatic.", "googleusercontent.", "w3.org"],
     lambda q: ("https://www.google.com/search?q=%s&num=20&hl=en" % enc(q), None)),
    ("DDG lite", False, ["duckduckgo.", "w3.org"],
     lambda q: ("https://lite.duckduckgo.com/lite/?q=%s" % enc(q), None)),
    ("DDG html", False, ["duckduckgo.", "w3.org"],
     lambda q: ("https://html.duckduckgo.com/html/", urllib.parse.urlencode({"q": q}).encode())),
    ("Mojeek", False, ["mojeek.", "w3.org"],
     lambda q: ("https://www.mojeek.com/search?q=%s" % enc(q), None)),
    ("Brave", False, ["brave.", "w3.org"],
     lambda q: ("https://search.brave.com/search?q=%s" % enc(q), None)),
    ("Ecosia", False, ["ecosia.", "w3.org"],
     lambda q: ("https://www.ecosia.org/search?q=%s" % enc(q), None)),
    ("Startpage", False, ["startpage.", "w3.org"],
     lambda q: ("https://www.startpage.com/sp/search?query=%s" % enc(q), None)),
    ("Yandex", False, ["yandex.", "w3.org"],
     lambda q: ("https://yandex.com/search/?text=%s" % enc(q), None)),
    ("Marginalia", False, ["marginalia.", "w3.org"],
     lambda q: ("https://search.marginalia.nu/search?query=%s" % enc(q), None)),
    ("searx.be JSON", True, [],
     lambda q: ("https://searx.be/search?q=%s&format=json" % enc(q), None)),
    ("searxng.site JSON", True, [],
     lambda q: ("https://searxng.site/search?q=%s&format=json" % enc(q), None)),
    ("priv.au JSON", True, [],
     lambda q: ("https://priv.au/search?q=%s&format=json" % enc(q), None)),
    ("inetol JSON", True, [],
     lambda q: ("https://search.inetol.net/search?q=%s&format=json" % enc(q), None)),
    ("searx.tiekoetter JSON", True, [],
     lambda q: ("https://searx.tiekoetter.com/search?q=%s&format=json" % enc(q), None)),
    ("baresearch JSON", True, [],
     lambda q: ("https://baresearch.org/search?q=%s&format=json" % enc(q), None)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=4)
    args = ap.parse_args()
    queries = ["Seedance 2.5 AI video", "InstaVM", "Boxes.dev"]

    print("查询样本:", queries)
    print()
    print("%-22s %6s %8s %8s" % ("端点", "HTTP", "可用查询", "候选数"))
    print("-" * 52)
    usable = []
    for name, is_json, excl, mk in ENDPOINTS:
        hits, oks, st0 = [], 0, None
        for q in queries:
            url, data = mk(q)
            st, body = get(url, data)
            if st0 is None:
                st0 = st
            if st != 200 or not body:
                continue
            if is_json:
                try:
                    d = json.loads(body)
                    for r in (d.get("results") or [])[:8]:
                        if r.get("url"):
                            hits.append(r["url"])
                    oks += 1
                    continue
                except Exception:
                    pass
            links = extract_links(body, excl)
            if links:
                oks += 1
                hits.extend(links[:12])
        uniq = []
        for u in hits:
            if u not in uniq:
                uniq.append(u)
        print("%-22s %6s %5d/%3d %8d" % (name, st0, oks, len(queries), len(uniq)))
        for u in uniq[: args.show]:
            print("      -", u[:100])
        if oks >= 2 and len(uniq) >= 6:
            usable.append((name, len(uniq)))

    print()
    print("=" * 52)
    if usable:
        print("可用端点（可用于 name→官网 反查）:")
        for n, c in usable:
            print("   ✔", n, "候选", c)
    else:
        print("❌ 无可用搜索端点：GitHub Actions 出口 IP 上的免费搜索全部不可用")


if __name__ == "__main__":
    main()
