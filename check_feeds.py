"""RSS Feed 健康檢查腳本
檢查 config.json 中所有 feed 的可用性，輸出 feed_status.json 供前端顯示。
"""
import json
import os
import datetime
import feedparser
from datetime import timezone, timedelta
TW = timezone(timedelta(hours=8))
import time
import calendar

def check_feeds():
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    feeds = config.get("feeds", {})
    results = []

    for category, sources in feeds.items():
        for source in sources:
            name = source["name"]
            url = source["url"]
            print(f"🔍 檢查 [{category}] {name}...")

            try:
                start = time.time()
                parsed = feedparser.parse(url)
                elapsed = round(time.time() - start, 2)

                # 檢查 HTTP 狀態
                status_code = parsed.get("status", 0)
                if status_code >= 400 or parsed.bozo:
                    error_msg = str(parsed.get("bozo_exception", f"HTTP {status_code}"))
                    results.append({
                        "name": name,
                        "url": url,
                        "category": category,
                        "status": "error",
                        "error": error_msg,
                        "response_time": elapsed
                    })
                    print(f"  ❌ 錯誤: {error_msg}")
                    continue

                # 檢查 entry 數量與最新日期
                entry_count = len(parsed.entries)
                latest_date = None
                if entry_count > 0:
                    entry = parsed.entries[0]
                    for field in ('published_parsed', 'updated_parsed', 'created_parsed'):
                        t = entry.get(field)
                        if t:
                            try:
                                ts = calendar.timegm(t)
                                latest_date = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                                break
                            except Exception:
                                continue

                results.append({
                    "name": name,
                    "url": url,
                    "category": category,
                    "status": "ok",
                    "entries": entry_count,
                    "latest": latest_date,
                    "response_time": elapsed
                })
                print(f"  ✅ OK ({entry_count} entries, latest: {latest_date}, {elapsed}s)")

            except Exception as e:
                results.append({
                    "name": name,
                    "url": url,
                    "category": category,
                    "status": "error",
                    "error": str(e),
                    "response_time": None
                })
                print(f"  ❌ 例外: {e}")

    # 輸出結果
    output = {
        "last_check": datetime.datetime.now(TW).strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "error": sum(1 for r in results if r["status"] == "error"),
        "feeds": results
    }

    os.makedirs("public", exist_ok=True)
    with open("public/feed_status.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n📊 健康檢查完成：{output['ok']}/{output['total']} feeds 正常")
    if output['error'] > 0:
        print(f"⚠️ {output['error']} 個 feed 有問題！")

if __name__ == "__main__":
    check_feeds()
