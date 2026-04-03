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
        body { font-family: Arial, sans-serif; margin: 40px; max-width: 1100px; }
        h1, h2, h3 { margin-bottom: 10px; }
        p { color: #444; }
        input, textarea { width: 100%; padding: 10px; margin: 8px 0 16px; box-sizing: border-box; }
        button { padding: 10px 16px; cursor: pointer; }
        .box { border: 1px solid #ccc; padding: 16px; border-radius: 8px; margin-top: 24px; }
        .muted { color: #666; font-size: 14px; }
        code { background: #f3f3f3; padding: 2px 6px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    </style>
</head>
<body>
    <h1>RSS Feed Generator Tool</h1>
    <p>Paste a page URL, preview detected articles, manually adjust selectors if needed, and get a public RSS URL.</p>

    <form method="post" action="/preview">
        <label><strong>Feed Name</strong></label>
        <input name="feed_name" placeholder="Capital Real Estate" required>

        <label><strong>Page URL</strong></label>
        <input name="page_url" placeholder="https://www.capital.gr/agora-akiniton" required>

        <label><strong>Link contains (simple mode)</strong></label>
        <input name="link_contains" placeholder="/agora-akiniton/">

        <div class="grid">
            <div>
                <label><strong>Article container selector (advanced)</strong></label>
                <input name="article_selector" placeholder="article, .post, .news-item">
            </div>
            <div>
                <label><strong>Title selector (advanced)</strong></label>
                <input name="title_selector" placeholder="h2 a, .title a">
            </div>
            <div>
                <label><strong>Link selector (advanced)</strong></label>
                <input name="link_selector" placeholder="h2 a, a.more">
            </div>
            <div>
                <label><strong>Summary selector (advanced)</strong></label>
                <input name="summary_selector" placeholder="p, .excerpt">
            </div>
        </div>

        <button type="submit">Preview Feed</button>
    </form>

    <div class="box">
        <h3>How to use</h3>
        <p><strong>Simple sites:</strong> fill only <code>Link contains</code>.</p>
        <p><strong>Harder sites:</strong> use the advanced selectors. Example:
        <code>article_selector=article</code>,
        <code>title_selector=h2 a</code>,
        <code>link_selector=h2 a</code>,
        <code>summary_selector=p</code>.</p>
    </div>
</body>
</html>
"""


def clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def fetch_html(page_url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(page_url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def fetch_articles_simple(page_url: str, link_contains: str):
    html = fetch_html(page_url)
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    items = []

    for a in soup.find_all("a", href=True):
        href = clean_text(a.get("href", ""))
        title = clean_text(a.get_text(" ", strip=True))

        if not href or not title:
            continue
        if link_contains and link_contains not in href:
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

    return items[:25]


def first_selected_text(container, selector: str) -> str:
    if not selector:
        return ""
    el = container.select_one(selector)
    if not el:
        return ""
    return clean_text(el.get_text(" ", strip=True))


def first_selected_link(container, selector: str, page_url: str) -> str:
    if not selector:
        return ""
    el = container.select_one(selector)
    if not el:
        return ""
    href = clean_text(el.get("href", ""))
    if not href:
        return ""
    return href if href.startswith(("http://", "https://")) else urljoin(page_url, href)


def fetch_articles_advanced(
    page_url: str,
    article_selector: str,
    title_selector: str,
    link_selector: str,
    summary_selector: str
):
    html = fetch_html(page_url)
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    items = []

    containers = soup.select(article_selector) if article_selector else []

    for container in containers:
        title = first_selected_text(container, title_selector)
        link = first_selected_link(container, link_selector, page_url)
        summary = first_selected_text(container, summary_selector)

        if not title or not link:
            continue
        if len(title) < 8:
            continue
        if link in seen:
            continue

        seen.add(link)
        items.append({
            "title": title,
            "link": link,
            "description": summary or title
        })

    return items[:25]


def detect_articles(
    page_url: str,
    link_contains: str,
    article_selector: str,
    title_selector: str,
    link_selector: str,
    summary_selector: str
):
    use_advanced = any([
        article_selector.strip(),
        title_selector.strip(),
        link_selector.strip(),
        summary_selector.strip()
    ])

    if use_advanced:
        return fetch_articles_advanced(
            page_url=page_url,
            article_selector=article_selector.strip(),
            title_selector=title_selector.strip(),
            link_selector=link_selector.strip(),
            summary_selector=summary_selector.strip()
        )

    return fetch_articles_simple(page_url, link_contains.strip())


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
    link_contains: str = Form(""),
    article_selector: str = Form(""),
    title_selector: str = Form(""),
    link_selector: str = Form(""),
    summary_selector: str = Form("")
):
    try:
        items = detect_articles(
            page_url=page_url,
            link_contains=link_contains,
            article_selector=article_selector,
            title_selector=title_selector,
            link_selector=link_selector,
            summary_selector=summary_selector
        )

        query = urlencode({
            "feed_name": feed_name,
            "page_url": page_url,
            "link_contains": link_contains,
            "article_selector": article_selector,
            "title_selector": title_selector,
            "link_selector": link_selector,
            "summary_selector": summary_selector
        })

        feed_url = f"/feed.xml?{query}"

        preview_items = "".join(
            f"<li><a href='{escape(item['link'])}' target='_blank'>{escape(item['title'])}</a>"
            f"<br><small>{escape(item['description'])}</small></li>"
            for item in items
        )

        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Preview Feed</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; max-width: 1100px; }}
                .box {{ border: 1px solid #ccc; padding: 16px; border-radius: 8px; margin-top: 24px; }}
                input {{ width: 100%; padding: 10px; margin: 8px 0 16px; box-sizing: border-box; }}
                button {{ padding: 10px 16px; cursor: pointer; }}
                code {{ background: #f3f3f3; padding: 2px 6px; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
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
                    <input name="link_contains" value="{escape(link_contains)}">

                    <div class="grid">
                        <div>
                            <label><strong>Article container selector</strong></label>
                            <input name="article_selector" value="{escape(article_selector)}">
                        </div>
                        <div>
                            <label><strong>Title selector</strong></label>
                            <input name="title_selector" value="{escape(title_selector)}">
                        </div>
                        <div>
                            <label><strong>Link selector</strong></label>
                            <input name="link_selector" value="{escape(link_selector)}">
                        </div>
                        <div>
                            <label><strong>Summary selector</strong></label>
                            <input name="summary_selector" value="{escape(summary_selector)}">
                        </div>
                    </div>

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
    link_contains: str = Query(""),
    article_selector: str = Query(""),
    title_selector: str = Query(""),
    link_selector: str = Query(""),
    summary_selector: str = Query("")
):
    try:
        items = detect_articles(
            page_url=page_url,
            link_contains=link_contains,
            article_selector=article_selector,
            title_selector=title_selector,
            link_selector=link_selector,
            summary_selector=summary_selector
        )
        rss_xml = build_rss(feed_name, page_url, items)
        return Response(content=rss_xml, media_type="application/rss+xml")
    except Exception as e:
        return Response(content=f"Feed error: {str(e)}", status_code=500)
