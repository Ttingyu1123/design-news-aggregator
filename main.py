import json
import os
import datetime
import time
import calendar
from datetime import timezone, timedelta
TW = timezone(timedelta(hours=8))
import feedparser
import google.generativeai as genai
from dotenv import load_dotenv

# 1. 載入環境變數與設定
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("請在 .env 檔案中設定 GEMINI_API_KEY")

genai.configure(api_key=API_KEY)

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

FEEDS = config.get("feeds", {})
MAX_ITEMS = config.get("summary", {}).get("max_items_per_feed", 3)
MODEL_NAME = config.get("summary", {}).get("model", "gemini-1.5-pro-latest")

# 2. 去重機制：載入與儲存已出現過的文章 URL
SEEN_URLS_FILE = "seen_urls.json"
MAX_SEEN_DAYS = 7  # 保留 7 天內的紀錄

def load_seen_urls():
    """載入已收錄過的 URL 清單"""
    if not os.path.exists(SEEN_URLS_FILE):
        return {}
    try:
        with open(SEEN_URLS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 清理超過 MAX_SEEN_DAYS 天的紀錄
        cutoff = (datetime.datetime.now(TW) - datetime.timedelta(days=MAX_SEEN_DAYS)).strftime("%Y-%m-%d")
        return {url: date for url, date in data.items() if date >= cutoff}
    except Exception:
        return {}

def save_seen_urls(seen_urls):
    """儲存已收錄過的 URL 清單"""
    with open(SEEN_URLS_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_urls, f, ensure_ascii=False, indent=2)

# 3. 日期過濾工具
MAX_AGE_HOURS = 48  # 只收錄 48 小時內的文章

def get_entry_timestamp(entry):
    """從 RSS entry 取得發布時間戳 (UTC epoch)，無法取得時回傳 None"""
    for field in ('published_parsed', 'updated_parsed', 'created_parsed'):
        t = entry.get(field)
        if t:
            try:
                return calendar.timegm(t)
            except Exception:
                continue
    return None

def is_recent(entry):
    """判斷文章是否在 MAX_AGE_HOURS 小時內"""
    ts = get_entry_timestamp(entry)
    if ts is None:
        return True  # 無法判斷日期時保守納入
    age_hours = (time.time() - ts) / 3600
    return age_hours <= MAX_AGE_HOURS

# 4. 定義爬取函數
def fetch_feeds():
    """從訂閱源抓取最新文章標題與摘要 (含日期過濾與去重)"""
    seen_urls = load_seen_urls()
    today_str = datetime.datetime.now(TW).strftime("%Y-%m-%d")
    feed_data = {}
    new_count = 0
    skipped_old = 0
    skipped_dup = 0

    for category, sources in FEEDS.items():
        feed_data[category] = []
        for source in sources:
            print(f"📡 正在抓取 [{category}] - {source['name']}...")
            try:
                parsed_feed = feedparser.parse(source['url'])
                entries = []
                for entry in parsed_feed.entries[:MAX_ITEMS * 3]:  # 多抓一些以補償被過濾掉的
                    link = entry.get('link', '')

                    # 去重：跳過已收錄過的 URL
                    if link and link in seen_urls:
                        skipped_dup += 1
                        continue

                    # 日期過濾：跳過超過 48 小時的舊文章
                    if not is_recent(entry):
                        skipped_old += 1
                        continue

                    title = entry.get('title', '無標題')
                    summary = entry.get('summary', '') or entry.get('description', '')
                    if len(summary) > 500:
                        summary = summary[:500] + "..."
                    entries.append(f"- **標題**: {title}\n  - 連結: {link}\n  - 內文摘要: {summary}")

                    # 標記為已收錄
                    if link:
                        seen_urls[link] = today_str
                    new_count += 1

                    if len(entries) >= MAX_ITEMS:
                        break

                if entries:
                    feed_data[category].append(f"### 來源：{source['name']}\n" + "\n".join(entries))
            except Exception as e:
                print(f"⚠️ 抓取 {source['name']} 失敗: {e}")

    print(f"\n📊 抓取統計：新文章 {new_count} 篇 | 跳過重複 {skipped_dup} 篇 | 跳過過期 {skipped_old} 篇")
    save_seen_urls(seen_urls)
    return feed_data

# 5. 呼叫 Gemini 進行彙整與翻譯摘要
def summarize_with_gemini(feed_data, issue_number):
    """將抓取的內容交給 Gemini 產生繁體中文 Markdown 報告"""
    print(f"\n🧠 正在交由 Gemini 分析裝訂第 {issue_number:03d} 期報表...")
    model = genai.GenerativeModel(
        MODEL_NAME,
        system_instruction="你是一位資深數位產品設計師與設計趨勢分析師，擁有 10 年以上的 UI/UX、品牌設計與設計系統經驗，熟悉 Figma、Framer 等現代設計工具生態。你必須全程使用「繁體中文」(Traditional Chinese, zh-TW) 回覆，絕對不可使用簡體中文。所有標點符號也必須使用全形標點。"
    )

    prompt = "請根據以下 RSS 爬取的最新文章，為我整理出一份「今日設計脈動日報」。\n"
    prompt += "要求：\n1. 【嚴格規定】全文必須使用「繁體中文」(zh-TW)，嚴禁出現任何簡體中文字元（例如：「进」應寫為「進」、「关」應寫為「關」、「项目」應寫為「專案」）。所有新聞標題都必須翻譯為繁體中文（可在括號中附上英文原標題），絕對不可只列英文標題。\n"
    prompt += "2. 【內容過濾規則 — 嚴格執行】本日報的讀者是「數位產品設計師」，只收錄與以下領域**直接相關**的內容：UI/UX 設計、網頁設計、平面設計、品牌識別、設計工具（Figma/Adobe/Sketch 等）、設計系統、字體排印、互動設計、動態設計、AI 輔助設計工具、No-Code 建站工具、CSS/前端視覺技術、設計靈感與作品集。\n"
    prompt += "   **必須排除**以下與設計無關的內容，即使它出現在 RSS 來源中也不可收錄：醫療/健康/藥物、政治/政策/法規、財經/股市/加密貨幣、純軟體工程（無設計面向）、純 AI 研究（無視覺/設計應用）、社會新聞、體育、娛樂八卦。若一篇文章的核心主題不是設計，即使標題含有「設計」二字也應排除。\n"
    prompt += "3. **焦點設計導讀**：從通過上述過濾的資訊中，篩選出最具影響力、最值得設計師關注的 5-8 條消息做詳細導讀，請加入你對設計手法、工具趨勢或產業影響的專業分析。\n"
    prompt += "4. **精細分類**：其餘資訊請務必依照屬性歸類到以下子類別中，並且【每一則資訊都必須用 2~3 句話 (約 50-80 字) 對其設計理念與實務價值進行精要敘述】，不可僅有一句話或單純列出標題：\n"
    prompt += "   【設計工具與 UI/UX (Design Tools & UI/UX)】\n"
    prompt += "   - Design Tools Updates (設計工具動態：Figma、Sketch、Penpot 等)\n"
    prompt += "   - UI/UX Research & Methods (使用者研究與設計方法論)\n"
    prompt += "   - Interaction & Motion Design (互動與動態設計)\n"
    prompt += "   【網頁設計與前端 (Web Design & Frontend)】\n"
    prompt += "   - Web Design Trends (網頁設計趨勢)\n"
    prompt += "   - CSS & Frontend Techniques (CSS 與前端技術)\n"
    prompt += "   - No-Code & Site Builders (無程式碼工具：Framer、Webflow 等)\n"
    prompt += "   【AI 設計與創意科技 (AI Design & Creative Tech)】\n"
    prompt += "   - AI-Powered Design Tools (AI 設計工具)\n"
    prompt += "   - Generative Art & Visual AI (生成式藝術與視覺 AI)\n"
    prompt += "   - Creative Technology (創意科技應用)\n"
    prompt += "   【設計靈感與社群 (Design Inspiration & Community)】\n"
    prompt += "   - Award-Winning Works (得獎作品與案例)\n"
    prompt += "   - Brand & Identity (品牌與識別設計)\n"
    prompt += "   - Design Community News (設計社群動態)\n"
    prompt += "   【設計系統與字體排印 (Design Systems & Typography)】\n"
    prompt += "   - Design Systems & Tokens (設計系統與 Design Tokens)\n"
    prompt += "   - Typography & Type Design (字體排印與字型設計)\n"
    prompt += "5. 每一條資訊都必須附上【原文連結】。\n6. 輸出格式必須是乾淨、易讀的 Markdown，請善用 H2 (##) 或 H3 (###) 標題來呈現。\n"
    today_str = datetime.datetime.now(TW).strftime("%Y-%m-%d")
    prompt += f"7. 輸出文章最開頭必須包含 YAML Frontmatter 屬性: date: {today_str}，請從內容中提取出 3~5 個設計相關關鍵字加入 tags (例如: tags: [Figma, 設計系統, AI設計, 網頁動效, 品牌識別])\n"
    prompt += f"8. 文章的大標題必須剛好是這行字且不可改變：`# ✏️ 設計脈動日報 - 第 {issue_number:03d} 期 ({today_str})`\n"
    prompt += "9. 在繁中報告最末尾，加上一段 `---` 分隔線後，附上 **English Daily Highlights** (300-500 words)，精要回顧今日亮點。\n\n"

    prompt += "【今日抓取內容如下】：\n"
    for category, articles in feed_data.items():
        prompt += f"\n## 領域：{category}\n"
        prompt += "\n".join(articles)

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Gemini API 呼叫失敗: {e}")
        return None

# 6. 儲存報表與維護索引
def save_report(content):
    if not content:
        return

    vault_path = "public/reports"
    os.makedirs(vault_path, exist_ok=True)
    today = datetime.datetime.now(TW).strftime("%Y-%m-%d")
    filename = os.path.join(vault_path, f"{today}_Daily_Report.md")

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 報表已生成：{filename}")

    # 產生更新版的 index.json 供前端讀取
    try:
        files = [f for f in os.listdir(vault_path) if f.endswith('.md')]
        files.sort(reverse=True) # 利用命名規則 YYYY-MM-DD 使最新檔案排前面
        index_data = []
        for f in files:
            date_str = f.split('_')[0]
            index_data.append({"date": date_str, "filename": f})

        with open("public/index.json", "w", encoding="utf-8") as f_idx:
            json.dump(index_data, f_idx, ensure_ascii=False, indent=2)
        print(f"✅ 索引檔已更新：public/index.json")

        # 建立搜尋索引
        search_index = []
        for item in index_data:
            try:
                fpath = os.path.join(vault_path, item["filename"])
                with open(fpath, "r", encoding="utf-8") as sf:
                    text = sf.read()
                title = ""
                for line in text.split("\n"):
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                body = text.split("---", 2)[-1] if text.startswith("---") else text
                preview = body.strip()[:300].replace("\n", " ")
                search_index.append({
                    "date": item["date"],
                    "filename": item["filename"],
                    "title": title,
                    "preview": preview
                })
            except Exception:
                continue

        with open("public/search_index.json", "w", encoding="utf-8") as si:
            json.dump(search_index, si, ensure_ascii=False, indent=2)
        print(f"✅ 搜尋索引已更新：public/search_index.json")
    except Exception as e:
        print(f"⚠️ 更新索引或刪除舊檔時發生錯誤: {e}")

if __name__ == "__main__":
    print(f"🚀 開始執行每日設計脈動彙整 ({datetime.datetime.now(TW).strftime('%Y-%m-%d %H:%M')})")
    data = fetch_feeds()

    # 計算期數
    vault_path = "public/reports"
    os.makedirs(vault_path, exist_ok=True)
    today_str = datetime.datetime.now(TW).strftime("%Y-%m-%d")
    existing_files = [f for f in os.listdir(vault_path) if f.endswith('.md')]
    if f"{today_str}_Daily_Report.md" in existing_files:
        issue_num = len(existing_files)
    else:
        issue_num = len(existing_files) + 1

    report_md = summarize_with_gemini(data, issue_num)
    save_report(report_md)
    print("🎉 任務完成！")
