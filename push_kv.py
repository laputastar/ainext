#!/usr/bin/env python3
"""
push_kv.py — 增量推送 tools.json 数据到 Cloudflare Workers KV

用法：
  python push_kv.py tools.json                    # 增量（对比 tools.prev.json，无则全量）
  python push_kv.py tools.json --full             # 强制全量写入（首次初始化用）
  python push_kv.py tools.json --dry-run          # 只打印将写入的 key，不实际推送

环境变量：
  CLOUDFLARE_API_TOKEN   Cloudflare API Token（Workers KV Storage Edit 权限）
  KV_NAMESPACE_ID        KV namespace ID

KV key 格式：tool:{id}，value = 完整工具 JSON 字符串
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.cloudflare.com/client/v4"
BULK_CHUNK = 900          # 单批最大写入数（免费限额 1000/天，留余量）
MAX_WRITES = 900          # 单次运行写入上限，防爆配额


def api_token():
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not tok:
        print("❌ 缺少环境变量 CLOUDFLARE_API_TOKEN")
        sys.exit(1)
    return tok


def namespace_id():
    ns = os.environ.get("KV_NAMESPACE_ID", "")
    if not ns:
        print("❌ 缺少环境变量 KV_NAMESPACE_ID")
        sys.exit(1)
    return ns


def http(method, url, body=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {api_token()}")
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  ❌ HTTP {e.code}: {err[:200]}")
        return None


def get_account_id():
    """通过 token 获取 account_id"""
    data = http("GET", f"{BASE}/accounts")
    if data and data.get("success") and data["result"]:
        return data["result"][0]["id"]
    print("❌ 无法获取 account_id，检查 API Token 权限")
    sys.exit(1)


def kv_put_bulk(account, ns, pairs):
    """批量写入 key-value，pairs = [(key, value_str), ...]"""
    body = [{"key": k, "value": v} for k, v in pairs]
    ok = 0
    for i in range(0, len(body), BULK_CHUNK):
        chunk = body[i:i + BULK_CHUNK]
        data = http("PUT", f"{BASE}/accounts/{account}/storage/kv/namespaces/{ns}/bulk", chunk)
        if data and data.get("success"):
            ok += len(chunk)
            print(f"  ✅ 写入 {len(chunk)} 条 (累计 {ok})")
        else:
            print(f"  ⚠️ 批次 {i // BULK_CHUNK} 失败，将重试")
            time.sleep(3)
            data = http("PUT", f"{BASE}/accounts/{account}/storage/kv/namespaces/{ns}/bulk", chunk)
            if data and data.get("success"):
                ok += len(chunk)
                print(f"  ✅ 重试成功 {len(chunk)} 条 (累计 {ok})")
    return ok


def kv_delete_bulk(account, ns, keys):
    """批量删除 key"""
    if not keys:
        return 0
    body = [{"key": k} for k in keys]
    data = http("DELETE", f"{BASE}/accounts/{account}/storage/kv/namespaces/{ns}/bulk", body)
    if data and data.get("success"):
        print(f"  🗑 删除 {len(keys)} 条")
        return len(keys)
    print("  ⚠️ 批量删除失败")
    return 0


def tool_hash(tool):
    """生成工具哈希，用于判断字段是否变化"""
    # 仅对比核心字段，忽略不稳定顺序
    core = {
        "name": tool.get("name", ""),
        "tagline": tool.get("tagline", ""),
        "tagline_zh": tool.get("tagline_zh", ""),
        "description": tool.get("description", ""),
        "description_zh": tool.get("description_zh", ""),
        "website": tool.get("website", ""),
        "ph_url": tool.get("ph_url", ""),
        "thumbnail": tool.get("thumbnail", ""),
        "votesCount": tool.get("votesCount", 0),
        "commentsCount": tool.get("commentsCount", 0),
        "category": tool.get("category", ""),
    }
    return hashlib.md5(json.dumps(core, sort_keys=True).encode()).hexdigest()


def diff_prev(cur_tools, prev_tools):
    """对比得出 新增/修改/删除 列表"""
    cur_map = {str(t["id"]): t for t in cur_tools}
    prev_map = {str(t["id"]): t for t in prev_tools}

    puts = []       # (key, value)
    deletes = []    # keys

    for tid, t in cur_map.items():
        key = f"tool:{tid}"
        h = tool_hash(t)
        if tid not in prev_map:
            puts.append((key, json.dumps(t, ensure_ascii=False)))
        else:
            ph = tool_hash(prev_map[tid])
            if h != ph:
                puts.append((key, json.dumps(t, ensure_ascii=False)))

    for tid in prev_map:
        if tid not in cur_map:
            deletes.append(f"tool:{tid}")

    return puts, deletes


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    args = sys.argv[1:]
    tools_path = "tools.json"
    full = "--full" in args
    dry = "--dry-run" in args
    for a in args:
        if not a.startswith("--"):
            tools_path = a

    if not os.path.exists(tools_path):
        print(f"❌ 找不到 {tools_path}")
        sys.exit(1)

    cur_tools = load_json(tools_path)
    prev_path = "tools.prev.json"

    if full:
        puts = [(f"tool:{str(t['id'])}", json.dumps(t, ensure_ascii=False)) for t in cur_tools]
        deletes = []
        mode = "全量"
    elif os.path.exists(prev_path):
        prev_tools = load_json(prev_path)
        puts, deletes = diff_prev(cur_tools, prev_tools)
        mode = f"增量 (对比 {prev_path})"
    else:
        puts = [(f"tool:{str(t['id'])}", json.dumps(t, ensure_ascii=False)) for t in cur_tools]
        deletes = []
        mode = "全量 (无上一轮快照)"

    print(f"🔍 模式: {mode}")
    print(f"📦 工具总数: {len(cur_tools)}, 待写入: {len(puts)}, 待删除: {len(deletes)}")

    if len(puts) > MAX_WRITES:
        print(f"  ⚠️ 待写入 {len(puts)} 超过单次上限 {MAX_WRITES}，截断。剩余变更将随下次运行继续。")
        puts = puts[:MAX_WRITES]

    if dry:
        print("\n🧪 Dry-run（不实际推送）:")
        for k, _ in puts[:5]:
            print(f"  PUT    {k}")
        for k in deletes[:5]:
            print(f"  DELETE {k}")
        if len(puts) > 5: print(f"  ... 共 {len(puts)} 条")
        print("✅ Dry-run 完成")
        return

    account = get_account_id()
    ns = namespace_id()

    print(f"\n🚀 开始同步到 KV (account={account[:8]}..., ns={ns[:8]}...)")
    n_put = kv_put_bulk(account, ns, puts)
    n_del = kv_delete_bulk(account, ns, deletes)
    print(f"\n✅ 完成: 写入 {n_put}, 删除 {n_del}")


if __name__ == "__main__":
    main()
