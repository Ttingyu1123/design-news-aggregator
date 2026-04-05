# 設計脈動日報 (design-news-aggregator)

> 共用規範見上層 [../CLAUDE.md](../CLAUDE.md)，本檔僅記錄此日報的差異。

## 專案概述
- **線上閱讀**：部署後填入 Vercel URL
- **Gemini 角色**：資深數位產品設計師與設計趨勢分析師
- **報告標題**：`# ✏️ 設計脈動日報 - 第 XXX 期`

## 訂閱源分類
- **UI_UX_Design_Tools**：Figma Blog, Adobe Blog, Sketch Blog, UX Planet, Nielsen Norman Group, UX Collective, Penpot Blog, Prototypr
- **Web_Design_and_NoCode**：Smashing Magazine, CSS-Tricks, A List Apart, Webflow Blog, Framer Blog, Codrops
- **AI_Design_and_Creative_Tech**：The Verge AI, It's Nice That, Creative Bloq, Digital Arts, Runway Blog, ComfyUI Releases, Krita News, GIMP News, Blender Releases
- **Design_Inspiration_and_Community**：Awwwards Blog, Dribbble Stories, Brand New, SiteInspire, Muzli Design Inspiration, Reddit r/web_design, Reddit r/comfyui, Reddit r/UI_Design, Reddit r/midjourney
- **Design_Systems_and_Typography**：Google Design, Typewolf, Fonts In Use, Abduzeedo

## 報告子分類
- 🛠️ 設計工具與 UI/UX（設計工具動態 / 使用者研究與方法論 / 互動與動態設計）
- 🌐 網頁設計與前端（網頁設計趨勢 / CSS 與前端技術 / 無程式碼工具）
- 🤖 AI 設計與創意科技（AI 設計工具 / 生成式藝術與視覺 AI / 創意科技應用）
- 🏆 設計靈感與社群（得獎作品與案例 / 品牌與識別設計 / 設計社群動態）
- 🔤 設計系統與字體排印（設計系統與 Design Tokens / 字體排印與字型設計）

## 排程
- **每日**：UTC 22:20（台灣 06:20）
- **每週精華**：週六 UTC 23:20（週日台灣 07:20）

## 專屬踩坑
- 部分設計類 feed（如 Awwwards、SiteInspire）更新頻率較低，有時整天無新文章是正常的
- Figma Blog 的 RSS 格式偶爾包含大量 HTML，已用 `[:500]` 截斷
- GitHub Releases Atom feed（ComfyUI、Blender）只含版本更新，非一般文章
- Reddit RSS 需要 feedparser 的 User-Agent，GitHub Actions 環境通常可抓；若被擋可加 `feedparser.parse(url, request_headers={'User-Agent': '...'})`
- 許多大廠（Canva、Affinity、Procreate、Miro）已關閉 RSS，僅能透過媒體源（Creative Bloq、It's Nice That）間接覆蓋
