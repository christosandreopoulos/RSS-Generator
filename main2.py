from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse, Response
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape
from urllib.parse import urlencode, urljoin

app = FastAPI(title="RSS Feed Generator Tool")


# -----------------------------
# Helpers
# -----------------------------
def clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def fetch_html(page_url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    r = requests.get(page_url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


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


def keyword_match(text: str, keyword_filter: str) -> bool:
    if not keyword_filter.strip():
        return True

    haystack = clean_text(text).lower()
    needles = [clean_text(x).lower() for x in keyword_filter.split(",") if clean_text(x)]

    if not needles:
        return True

    return any(needle in haystack for needle in needles)


# -----------------------------
# Simple mode
# -----------------------------
def fetch_articles_simple(page_url: str, link_contains: str, keyword_filter: str):
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

        visible_text = title
        if not keyword_match(visible_text, keyword_filter):
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

    return items[:30]


# -----------------------------
# Advanced mode
# -----------------------------
def get_selected_element(container, selector: str):
    if not selector:
        return None

    if selector == "__self__":
        return container

    try:
        return container.select_one(selector)
    except Exception:
        return None


def get_selected_text(container, selector: str) -> str:
    el = get_selected_element(container, selector)
    if not el:
        return ""
    return clean_text(el.get_text(" ", strip=True))


def get_selected_link(container, selector: str, page_url: str) -> str:
    el = get_selected_element(container, selector)
    if not el:
        return ""

    href = clean_text(el.get("href", ""))
    if href:
        return href if href.startswith(("http://", "https://")) else urljoin(page_url, href)

    a = el.find("a", href=True)
    if not a:
        return ""

    href = clean_text(a.get("href", ""))
    if not href:
        return ""

    return href if href.startswith(("http://", "https://")) else urljoin(page_url, href)


def fetch_articles_advanced(
    page_url: str,
    article_selector: str,
    title_selector: str,
    link_selector: str,
    summary_selector: str,
    keyword_filter: str
):
    html = fetch_html(page_url)
    soup = BeautifulSoup(html, "lxml")

    try:
        containers = soup.select(article_selector) if article_selector else []
    except Exception:
        containers = []

    seen = set()
    items = []

    for container in containers:
        container_text = clean_text(container.get_text(" ", strip=True))
        if not keyword_match(container_text, keyword_filter):
            continue

        title = get_selected_text(container, title_selector)
        link = get_selected_link(container, link_selector, page_url)
        summary = get_selected_text(container, summary_selector) if summary_selector else ""

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

    return items[:30]


def detect_articles(
    page_url: str,
    link_contains: str,
    article_selector: str,
    title_selector: str,
    link_selector: str,
    summary_selector: str,
    keyword_filter: str
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
            summary_selector=summary_selector.strip(),
            keyword_filter=keyword_filter.strip()
        )

    return fetch_articles_simple(
        page_url=page_url,
        link_contains=link_contains.strip(),
        keyword_filter=keyword_filter.strip()
    )


# -----------------------------
# UI
# -----------------------------
def home_html(
    feed_name="",
    page_url="",
    link_contains="",
    article_selector="",
    title_selector="",
    link_selector="",
    summary_selector="",
    keyword_filter=""
):
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>RSS Feed Generator Tool</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 40px;
            max-width: 1100px;
        }}
        input {{
            width: 100%;
            padding: 10px;
            margin: 8px 0 16px;
            box-sizing: border-box;
        }}
        button {{
            padding: 10px 16px;
            cursor: pointer;
        }}
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .actions {{
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
        }}
        .box {{
            border: 1px solid #ccc;
            padding: 16px;
            border-radius: 8px;
            margin-top: 24px;
        }}
        code {{
            background: #f3f3f3;
            padding: 2px 6px;
        }}
    </style>
</head>
<body>
    <h1>RSS Feed Generator Tool</h1>
    <p>Βάλε URL, selectors και προαιρετικά keyword filter πάνω στο ορατό κείμενο του article card.</p>

    <form method="post" action="/preview">
        <label><strong>Feed Name</strong></label>
        <input name="feed_name" value="{escape(feed_name)}" required>

        <label><strong>Page URL</strong></label>
        <input id="page_url" name="page_url" value="{escape(page_url)}" required>

        <label><strong>Link contains (simple mode)</strong></label>
        <input name="link_contains" value="{escape(link_contains)}" placeholder="/agora-akiniton/">

        <label><strong>Keyword filter (visible text)</strong></label>
        <input name="keyword_filter" value="{escape(keyword_filter)}" placeholder="Ακίνητα">

        <div class="grid">
            <div>
                <label><strong>Article container selector</strong></label>
                <input name="article_selector" value="{escape(article_selector)}" placeholder="div.item, article, li.post">
            </div>
            <div>
                <label><strong>Title selector</strong></label>
                <input name="title_selector" value="{escape(title_selector)}" placeholder="h2 a, h3 a, __self__">
            </div>
            <div>
                <label><strong>Link selector</strong></label>
                <input name="link_selector" value="{escape(link_selector)}" placeholder="h2 a, h3 a, a, __self__">
            </div>
            <div>
                <label><strong>Summary selector</strong></label>
                <input name="summary_selector" value="{escape(summary_selector)}" placeholder="p, .excerpt, .summary">
            </div>
        </div>

        <div class="actions">
            <button type="submit">Preview Feed</button>
        </div>
    </form>

    <div class="box">
        <p><strong>Keyword filter:</strong> ψάχνει μέσα στο ορατό κείμενο κάθε article card, όχι στο URL.</p>
        <p>Μπορείς να βάλεις και πολλές λέξεις χωρισμένες με κόμμα, π.χ. <code>Ακίνητα, κατοικίες</code>.</p>
    </div>
</body>
</html>
"""


# -----------------------------
# Routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def home(
    feed_name: str = Query(""),
    page_url: str = Query(""),
    link_contains: str = Query(""),
    article_selector: str = Query(""),
    title_selector: str = Query(""),
    link_selector: str = Query(""),
    summary_selector: str = Query(""),
    keyword_filter: str = Query("")
):
    return home_html(
        feed_name=feed_name,
        page_url=page_url,
        link_contains=link_contains,
        article_selector=article_selector,
        title_selector=title_selector,
        link_selector=link_selector,
        summary_selector=summary_selector,
        keyword_filter=keyword_filter
    )


@app.post("/preview", response_class=HTMLResponse)
def preview(
    feed_name: str = Form(...),
    page_url: str = Form(...),
    link_contains: str = Form(""),
    article_selector: str = Form(""),
    title_selector: str = Form(""),
    link_selector: str = Form(""),
    summary_selector: str = Form(""),
    keyword_filter: str = Form("")
):
    try:
        items = detect_articles(
            page_url=page_url,
            link_contains=link_contains,
            article_selector=article_selector,
            title_selector=title_selector,
            link_selector=link_selector,
            summary_selector=summary_selector,
            keyword_filter=keyword_filter
        )

        query = urlencode({
            "feed_name": feed_name,
            "page_url": page_url,
            "link_contains": link_contains,
            "article_selector": article_selector,
            "title_selector": title_selector,
            "link_selector": link_selector,
            "summary_selector": summary_selector,
            "keyword_filter": keyword_filter
        })

        feed_url = f"/feed.xml?{query}"
        back_url = f"/?{query}"

        preview_items = "".join(
            f"<li><a href='{escape(item['link'])}' target='_blank'>{escape(item['title'])}</a><br>"
            f"<small>{escape(item['description'])}</small></li>"
            for item in items
        )

        return f"""
        <html>
        <head>
            <meta charset="utf-8">
            <title>Preview Feed</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 40px;
                    max-width: 1100px;
                }}
                .box {{
                    border: 1px solid #ccc;
                    padding: 16px;
                    border-radius: 8px;
                    margin-top: 24px;
                }}
            </style>
        </head>
        <body>
            <h1>Preview</h1>
            <p><strong>Detected {len(items)} items</strong></p>

            <div class="box">
                <h3>Generated RSS URL</h3>
                <p><a href="{feed_url}" target="_blank">{feed_url}</a></p>
            </div>

            <div class="box">
                <h3>Detected Articles</h3>
                <ol>{preview_items}</ol>
            </div>

            <p><a href="{back_url}">Back</a></p>
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
    summary_selector: str = Query(""),
    keyword_filter: str = Query("")
):
    try:
        items = detect_articles(
            page_url=page_url,
            link_contains=link_contains,
            article_selector=article_selector,
            title_selector=title_selector,
            link_selector=link_selector,
            summary_selector=summary_selector,
            keyword_filter=keyword_filter
        )
        rss_xml = build_rss(feed_name, page_url, items)
        return Response(content=rss_xml, media_type="application/rss+xml")
    except Exception as e:
        return Response(content=f"Feed error: {str(e)}", status_code=500)
