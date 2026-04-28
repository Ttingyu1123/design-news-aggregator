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
import re
import markdown

# --- Site config (for HTML generation) ---
SITE_CONFIG = {
    "name": "設計脈動日報",
    "brand_icon": "✏️",
    "accent": "#9B7EC8",
    "accent_dark": "#7B5EA8",
    "theme_color": "#E0E5EC",
    "base_url": "https://design-news-aggregator.vercel.app",
    "og_image": "https://design-news-aggregator.vercel.app/icon-512.png",
}

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
FALLBACK_MODEL = config.get("summary", {}).get("fallback_model", "")

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
    prompt += "   【格式嚴格規範 — 每條重點導讀必須使用以下結構，禁止使用編號列表(1. 2. 3.)】：\n"
    prompt += "   ```\n"
    prompt += "   ### 序號. 中文標題（English Title）\n"
    prompt += "   \n"
    prompt += "   分析段落：2-3 句說明為何重要、有何影響。\n"
    prompt += "   \n"
    prompt += "   - 原文連結：https://...\n"
    prompt += "   ```\n"
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
    prompt += "5. 每一條資訊都必須附上【原文連結】。\n6. 【Markdown 結構規範】大區塊用 H2 (##)，重點導讀的每條用 H3 (###)，精細分類的子類別用 H4 (####)。每個段落之間必須空一行。嚴禁將重點導讀寫成編號列表。\n"
    prompt += "10. 【格式規定 — 嚴格執行】禁止使用 Markdown 引用區塊（即 `>` blockquote 語法）。所有分析內容請用「無序列表 + 粗體標籤」格式呈現，例如：\n"
    prompt += "   - **原文連結**：https://example.com\n"
    prompt += "   - **趨勢分析**：這篇文章探討了...\n"
    prompt += "   - **設計啟示**：對於設計師而言...\n"
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
        print(f"⚠️ {MODEL_NAME} 呼叫失敗: {e}")
        if FALLBACK_MODEL:
            print(f"🔄 切換到 fallback 模型: {FALLBACK_MODEL}")
            try:
                fallback = genai.GenerativeModel(
                    FALLBACK_MODEL,
                    system_instruction=model._system_instruction,
                )
                response = fallback.generate_content(prompt)
                return response.text
            except Exception as e2:
                print(f"❌ Fallback 也失敗: {e2}")
        return None

# 6. 儲存報表與維護索引
def strip_code_fence(text):
    """移除 Gemini 回傳的 markdown code fence 包裝"""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.index("\n")
        stripped = stripped[first_newline + 1:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()

def normalize_frontmatter(text):
    """確保 YAML frontmatter 使用正確的 --- 分隔符"""
    lines = text.split("\n")
    if not lines:
        return text
    if lines[0].strip() == "---":
        return text
    if not re.match(r"^(date|type|tags|title):", lines[0].strip()):
        return text
    for i in range(1, min(len(lines), 10)):
        stripped = lines[i].strip()
        if stripped == "```":
            lines[i] = "---"
            break
        if stripped == "---":
            break
        if stripped.startswith("#"):
            lines.insert(i, "---")
            break
    lines.insert(0, "---")
    return "\n".join(lines)

def save_report(content):
    if not content:
        return

    content = strip_code_fence(content)
    content = normalize_frontmatter(content)

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

# HTML / Sitemap / RSS 生成
def _extract_title(md_text):
    for line in md_text.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return ""

def _extract_preview(md_text, length=160):
    body = md_text.split("---", 2)[-1] if md_text.startswith("---") else md_text
    text = re.sub(r'[#*\[\]()>_`]', '', body).strip()
    text = re.sub(r'\n+', ' ', text)[:length]
    return text

def _build_sidebar_html(reports, current_filename):
    now = datetime.datetime.now(TW)
    seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    recent, weekly, older = [], [], {}
    for r in reports:
        is_weekly = "Weekly" in r["filename"]
        if is_weekly:
            weekly.append(r)
        elif r["date"] >= seven_days_ago:
            recent.append(r)
        else:
            month = r["date"][:7]
            older.setdefault(month, []).append(r)

    html = ""
    def section(icon, title, items, is_open):
        nonlocal html
        open_cls = " open" if is_open else ""
        html += f'<li class="nav-section{open_cls}">'
        html += f'<button class="nav-section-header"><span class="icon">{icon}</span> {title} <span class="nav-count">{len(items)}</span> <span class="nav-arrow">▼</span></button>'
        html += '<ul class="nav-items">'
        for item in items:
            is_weekly = "Weekly" in item["filename"]
            label = f"⭐ {item['date']}" if is_weekly else item["date"]
            active = " active" if item["filename"] == current_filename else ""
            href = f'/reports/{item["filename"].replace(".md", ".html")}'
            html += f'<li><a class="nav-link{active}" href="{href}">{label}</a></li>'
        html += '</ul></li>'

    if recent:
        section("🕐", "最近日報", recent, True)
    if weekly:
        section("⭐", "每週精華", weekly, False)
    for month_key in sorted(older.keys(), reverse=True):
        y, m = month_key.split("-")
        section("📂", f"{y} 年 {int(m)} 月", older[month_key], False)

    return html

def _xml_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def generate_html_pages():
    vault_path = "public/reports"
    template_path = "public/report_template.html"
    if not os.path.exists(template_path):
        print("⚠️ report_template.html not found, skipping HTML generation")
        return

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    md_files = sorted([f for f in os.listdir(vault_path) if f.endswith('.md')], reverse=True)
    reports = []
    for fname in md_files:
        date_str = fname.split('_')[0]
        with open(os.path.join(vault_path, fname), "r", encoding="utf-8") as f:
            content = f.read()
        reports.append({
            "date": date_str,
            "filename": fname,
            "title": _extract_title(content),
            "preview": _extract_preview(content),
            "md_content": content,
        })

    md_converter = markdown.Markdown(extensions=['tables', 'fenced_code', 'nl2br'])
    _url_re = re.compile(r'(?<!["\'>=/])(https?://[^\s<>\)\"]+)')

    for i, report in enumerate(reports):
        md_converter.reset()
        md_body = report["md_content"]
        if md_body.startswith("---"):
            parts = md_body.split("---", 2)
            md_body = parts[2] if len(parts) > 2 else md_body

        article_html = md_converter.convert(md_body)
        article_html = _url_re.sub(r'<a href="\1" target="_blank" rel="noopener">\1</a>', article_html)
        sidebar_html = _build_sidebar_html(reports, report["filename"])

        prev_link = ""
        next_link = ""
        if i < len(reports) - 1:
            older = reports[i + 1]
            prev_link = f'<a href="/reports/{older["filename"].replace(".md", ".html")}">← {older["date"]}</a>'
        if i > 0:
            newer = reports[i - 1]
            next_link = f'<a href="/reports/{newer["filename"].replace(".md", ".html")}">{newer["date"]} →</a>'

        page_title = report["title"] or f'{SITE_CONFIG["name"]} - {report["date"]}'

        html = template
        html = html.replace("{{PAGE_TITLE}}", page_title)
        html = html.replace("{{META_DESCRIPTION}}", report["preview"])
        html = html.replace("{{CANONICAL_URL}}", f'{SITE_CONFIG["base_url"]}/reports/{report["filename"].replace(".md", ".html")}')
        html = html.replace("{{OG_IMAGE}}", SITE_CONFIG["og_image"])
        html = html.replace("{{THEME_COLOR}}", SITE_CONFIG["theme_color"])
        html = html.replace("{{ACCENT_COLOR}}", SITE_CONFIG["accent"])
        html = html.replace("{{ACCENT_DARK}}", SITE_CONFIG["accent_dark"])
        html = html.replace("{{SITE_NAME}}", SITE_CONFIG["name"])
        html = html.replace("{{BRAND_ICON}}", SITE_CONFIG["brand_icon"])
        html = html.replace("{{TOPBAR_TITLE}}", f'{report["date"]} 日報')
        html = html.replace("{{SIDEBAR_HTML}}", sidebar_html)
        html = html.replace("{{ARTICLE_HTML}}", article_html)
        html = html.replace("{{PREV_LINK}}", prev_link)
        html = html.replace("{{NEXT_LINK}}", next_link)

        out_path = os.path.join(vault_path, report["filename"].replace(".md", ".html"))
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

    print(f"✅ 已生成 {len(reports)} 個 HTML 頁面")

def generate_sitemap():
    vault_path = "public/reports"
    base_url = SITE_CONFIG["base_url"]
    md_files = sorted([f for f in os.listdir(vault_path) if f.endswith('.md')], reverse=True)

    urls = [f'  <url><loc>{base_url}/</loc><priority>1.0</priority></url>']
    for fname in md_files:
        date_str = fname.split('_')[0]
        html_name = fname.replace(".md", ".html")
        urls.append(f'  <url><loc>{base_url}/reports/{html_name}</loc><lastmod>{date_str}</lastmod><priority>0.8</priority></url>')

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += '\n'.join(urls)
    sitemap += '\n</urlset>'

    with open("public/sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap)
    print(f"✅ sitemap.xml 已更新（{len(md_files)} 頁）")

def generate_rss():
    vault_path = "public/reports"
    base_url = SITE_CONFIG["base_url"]
    site_name = SITE_CONFIG["name"]
    md_files = sorted([f for f in os.listdir(vault_path) if f.endswith('.md')], reverse=True)[:20]

    items = []
    for fname in md_files:
        date_str = fname.split('_')[0]
        fpath = os.path.join(vault_path, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        title = _extract_title(content) or f"{site_name} - {date_str}"
        preview = _extract_preview(content, 300)
        html_name = fname.replace(".md", ".html")
        try:
            pub_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y 06:00:00 +0800")
        except ValueError:
            pub_date = datetime.datetime.now(TW).strftime("%a, %d %b %Y 06:00:00 +0800")

        items.append(f'''    <item>
      <title>{_xml_escape(title)}</title>
      <link>{base_url}/reports/{html_name}</link>
      <guid>{base_url}/reports/{html_name}</guid>
      <pubDate>{pub_date}</pubDate>
      <description>{_xml_escape(preview)}</description>
    </item>''')

    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{_xml_escape(site_name)}</title>
    <link>{base_url}</link>
    <description>{_xml_escape(site_name)} — 每日自動彙整</description>
    <language>zh-TW</language>
    <atom:link href="{base_url}/feed.xml" rel="self" type="application/rss+xml"/>
    <lastBuildDate>{datetime.datetime.now(TW).strftime("%a, %d %b %Y %H:%M:%S +0800")}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>'''

    with open("public/feed.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print(f"✅ feed.xml 已更新（{len(items)} 篇）")


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

    generate_html_pages()
    generate_sitemap()
    generate_rss()
    print("🎉 任務完成！")
