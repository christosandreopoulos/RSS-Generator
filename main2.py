from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse, Response
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape
from urllib.parse import urlencode, urljoin

app = FastAPI(title="RSS Feed Generator Tool")

HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>RSS Feed Generator Tool</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; max-width: 950px; }
        h1 { margin-bottom: 10px; }
        p { color: #444; }
        input { width: 100%; padding: 10px; margin: 8px 0 16px; box-sizing: border-box; }
        button { padding: 10px 16px; cursor: pointer; }
        .box { border: 1px solid #ccc; padding: 16px; border-radius: 8px; margin-top: 24px; }
        .muted { color: #666; font-size: 14px; }
        code { background: #f3f3f3; padding: 2px 6px; }
    </style>
</head>
<body>
    <h1>RSS Feed Generator Tool</h1>
    <p>Paste a page URL, preview the detected articles, and get a public RSS URL.</p>

    <form method="post" action="/preview">
        <label><strong>Feed Name</strong></label>
        <input name="feed_name" placeholder="Capital Real Estate" required>

        <label><strong>Page URL</strong></label>
        <input name="page_url" placeholder="https://www.capital.gr/agora-akiniton" required>

        <label><strong>Link contains</strong></label>
        <input name="link_contains" placeholder="/agora-akiniton/" required>

        <button type="submit">Preview Feed</button>
    </form>

    <p class="muted">
        Tip: “Link contains” is the common pattern found inside article links on the page.
    </p>
</body>
</html>
"""

def fetch_articles(page_url: str, link_contains: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(page_url, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    seen = set()
    items = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        title = a.get_text(" ", strip=True)

        if not href or not title:
            continue
        if link_contains not in href:
            continue
        if len(title) < 12:
            continue

        full_link = href if href.startswith(("http://", "https://")) else urljoin(page_url, href)

        if full_link in seen:
            continue

        seen.add(full_link)
        items.append({
            "title": title,
            "link": full_link,
            "description": title
        })

    return items[:20]

def build_rss(feed_name: str, page_url: str, items: list[dict]) -> str:
    now = format_datetime(datetime.now(timezone.utc))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '<channel>',
        f'<title>{escape(feed_name)}</title>',
        f'<link>{escape(page_url)}</link>',
        '<description>Generated RSS feed</description>',
        f'<pubDate>{now}</pubDate>',
        f'<lastBuildDate>{now}</lastBuildDate>',
    ]

    for item in items:
        title = escape(item["title"])
        link = escape(item["link"])
        desc = escape(item["description"])
        parts.extend([
            '<item>',
            f'<title>{title}</title>',
            f'<link>{link}</link>',
            f'<guid>{link}</guid>',
            f'<description>{desc}</description>',
            f'<pubDate>{now}</pubDate>',
            '</item>'
        ])

    parts.extend(['</channel>', '</rss>'])
    return "\n".join(parts)

@app.get("/", response_class=HTMLResponse)
def home():
    return HOME_HTML

@app.post("/preview", response_class=HTMLResponse)
def preview(
    feed_name: str = Form(...),
    page_url: str = Form(...),
    link_contains: str = Form(...)
):
    try:
        items = fetch_articles(page_url, link_contains)

        query = urlencode({
            "feed_name": feed_name,
            "page_url": page_url,
            "link_contains": link_contains
        })

        feed_url = f"/feed.xml?{query}"

        preview_items = "".join(
            f"<li><a href='{escape(item['link'])}' target='_blank'>{escape(item['title'])}</a></li>"
            for item in items
        )

        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Preview Feed</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; max-width: 950px; }}
                .box {{ border: 1px solid #ccc; padding: 16px; border-radius: 8px; margin-top: 24px; }}
                input {{ width: 100%; padding: 10px; margin: 8px 0 16px; box-sizing: border-box; }}
                button {{ padding: 10px 16px; cursor: pointer; }}
                code {{ background: #f3f3f3; padding: 2px 6px; }}
            </style>
        </head>
        <body>
            <h1>Preview</h1>
            <p><strong>Detected {len(items)} items</strong></p>

            <div class="box">
                <h3>Generated RSS URL</h3>
                <p><a href="{feed_url}" target="_blank">{feed_url}</a></p>
                <p>When deployed online, copy the full URL from your browser and paste it into your platform.</p>
            </div>

            <div class="box">
                <h3>Detected Articles</h3>
                <ol>{preview_items}</ol>
            </div>

            <div class="box">
                <h3>Manual Adjustment</h3>
                <form method="post" action="/preview">
                    <label><strong>Feed Name</strong></label>
                    <input name="feed_name" value="{escape(feed_name)}" required>

                    <label><strong>Page URL</strong></label>
                    <input name="page_url" value="{escape(page_url)}" required>

                    <label><strong>Link contains</strong></label>
                    <input name="link_contains" value="{escape(link_contains)}" required>

                    <button type="submit">Try Again</button>
                </form>
            </div>

            <p><a href="/">Back</a></p>
        </body>
        </html>
        """
    except Exception as e:
        return f"""
        <html>
        <head><meta charset="utf-8"><title>Error</title></head>
        <body style="font-family: Arial, sans-serif; margin: 40px;">
            <h1>Error</h1>
            <p>{escape(str(e))}</p>
            <p><a href="/">Go back</a></p>
        </body>
        </html>
        """

@app.get("/feed.xml")
def feed_xml(
    feed_name: str = Query(...),
    page_url: str = Query(...),
    link_contains: str = Query(...)
):
    try:
        items = fetch_articles(page_url, link_contains)
        rss_xml = build_rss(feed_name, page_url, items)
        return Response(content=rss_xml, media_type="application/rss+xml")
    except Exception as e:
        return Response(content=f"Feed error: {str(e)}", status_code=500)