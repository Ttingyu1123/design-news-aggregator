"""每週精華版生成腳本
讀取過去 7 天的日報，透過 Gemini 產出本週精華回顧。
"""
import json
import os
import datetime
import glob
from datetime import timezone, timedelta
TW = timezone(timedelta(hours=8))
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("請在 .env 檔案中設定 GEMINI_API_KEY")

genai.configure(api_key=API_KEY)

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

MODEL_NAME = config.get("summary", {}).get("model", "gemini-1.5-pro-latest")

def get_week_reports():
    """取得過去 7 天的日報內容"""
    vault_path = "public/reports"
    if not os.path.exists(vault_path):
        return []

    today = datetime.datetime.now(TW)
    week_ago = today - datetime.timedelta(days=7)
    reports = []

    for f in sorted(os.listdir(vault_path)):
        if not f.endswith("_Daily_Report.md"):
            continue
        date_str = f.split("_")[0]
        try:
            file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TW)
            if file_date >= week_ago:
                filepath = os.path.join(vault_path, f)
                with open(filepath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                reports.append({"date": date_str, "content": content})
        except ValueError:
            continue

    return reports

def generate_weekly_digest(reports):
    """用 Gemini 生成週報"""
    if not reports:
        print("⚠️ 本週沒有日報可供彙整")
        return None

    print(f"📚 找到 {len(reports)} 份日報，開始生成週報...")

    model = genai.GenerativeModel(
        MODEL_NAME,
        system_instruction="你是資深數位產品設計師與設計趨勢分析師。你必須全程使用「繁體中文」(Traditional Chinese, zh-TW) 回覆，絕對不可使用簡體中文。所有標點符號也必須使用全形標點。"
    )

    today = datetime.datetime.now(TW)
    year, week_num, _ = today.isocalendar()
    date_range = f"{reports[0]['date']} ~ {reports[-1]['date']}"

    prompt = f"以下是本週 ({date_range}) 的每日設計情報摘要共 {len(reports)} 篇。\n"
    prompt += "請根據這些內容，為我整理出一份「本週設計精華回顧」。\n\n"
    prompt += "要求：\n"
    prompt += "1. 【嚴格規定】全文必須使用「繁體中文」(zh-TW)。\n"
    prompt += "2. **本週最重要的 5-10 件設計大事**：從整週所有報告中提煉出最有影響力、最值得設計師關注的議題，做深度分析。\n"
    prompt += "3. **設計趨勢觀察**：指出本週反覆出現的設計趨勢或工具動態，分析其對設計師工作流程的影響。\n"
    prompt += "4. **值得追蹤的後續發展**：列出設計師應該持續關注的議題。\n"
    prompt += "5. 每一條都必須附上原文連結。\n"
    prompt += "6. 輸出格式必須是乾淨的 Markdown。\n"
    prompt += f"7. 文章大標題：`# ⭐ 本週設計精華回顧 - {year}年第{week_num}週 ({date_range})`\n"
    prompt += f"8. 文章開頭包含 YAML Frontmatter: date: {today.strftime('%Y-%m-%d')}, type: weekly\n\n"

    # 附上英文摘要要求
    prompt += "9. 在繁中報告最末尾，加上一段 `---` 分隔線後，附上 **English Weekly Highlights** (300-500 words)，精要回顧本週亮點。\n\n"

    prompt += "【本週日報內容如下】：\n\n"
    for r in reports:
        prompt += f"=== {r['date']} 日報 ===\n"
        # 限制每份報告長度避免超過 token 上限
        content = r['content'][:8000] if len(r['content']) > 8000 else r['content']
        prompt += content + "\n\n"

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"❌ Gemini API 呼叫失敗: {e}")
        return None

def save_weekly(content):
    if not content:
        return

    vault_path = "public/reports"
    os.makedirs(vault_path, exist_ok=True)

    today = datetime.datetime.now(TW)
    year, week_num, _ = today.isocalendar()
    filename = os.path.join(vault_path, f"{year}-W{week_num:02d}_Weekly_Digest.md")

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 週報已生成：{filename}")

    # 更新 index.json
    try:
        files = [f for f in os.listdir(vault_path) if f.endswith('.md')]
        files.sort(reverse=True)
        index_data = []
        for f in files:
            if "Weekly_Digest" in f:
                date_str = f.split("_")[0]  # e.g. 2026-W08
                index_data.append({"date": date_str, "filename": f, "type": "weekly"})
            else:
                date_str = f.split("_")[0]
                index_data.append({"date": date_str, "filename": f, "type": "daily"})

        with open("public/index.json", "w", encoding="utf-8") as f_idx:
            json.dump(index_data, f_idx, ensure_ascii=False, indent=2)
        print(f"✅ 索引檔已更新")
    except Exception as e:
        print(f"⚠️ 更新索引時發生錯誤: {e}")

if __name__ == "__main__":
    print(f"📰 開始生成每週設計精華版 ({datetime.datetime.now(TW).strftime('%Y-%m-%d %H:%M')})")
    reports = get_week_reports()
    digest = generate_weekly_digest(reports)
    save_weekly(digest)
    print("🎉 週報任務完成！")
