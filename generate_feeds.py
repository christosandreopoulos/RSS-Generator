import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape
import os

def fetch_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text

def make_absolute(url, base=""):
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if base.endswith("/") and url.startswith("/"):
        return base[:-1] + url
    return base + url

def scrape_articles(source):
    html = fetch_html(source["url"])
    soup = BeautifulSoup(html, "html.parser")

    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not href or not title:
            continue

        if source["link_contains"] not in href:
            continue

        full_link = make_absolute(href, "https://www.capital.gr")

        if full_link in seen:
            continue

        if len(title) < 12:
            continue

        seen.add(full_link)
        articles.append({
            "title": title,
            "link": full_link,
            "description": title
        })

    return articles[:20]

def build_rss(source, articles):
    now = format_datetime(datetime.now(timezone.utc))

    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<rss version="2.0">')
    parts.append('<channel>')
    parts.append(f'<title>{escape(source["name"])}</title>')
    parts.append(f'<link>{escape(source["url"])}</link>')
    parts.append('<description>Generated RSS feed</description>')
    parts.append('<language>el-gr</language>')
    parts.append(f'<pubDate>{now}</pubDate>')
    parts.append(f'<lastBuildDate>{now}</lastBuildDate>')

    for a in articles:
        title = escape(a["title"])
        link = escape(a["link"])
        description = escape(a["description"])

        parts.append('<item>')
        parts.append(f'<title>{title}</title>')
        parts.append(f'<link>{link}</link>')
        parts.append(f'<guid>{link}</guid>')
        parts.append(f'<description>{description}</description>')
        parts.append(f'<pubDate>{now}</pubDate>')
        parts.append('</item>')

    parts.append('</channel>')
    parts.append('</rss>')
    return "\n".join(parts)

def main():
    with open("sources.json", "r", encoding="utf-8") as f:
        sources = json.load(f)

    os.makedirs("feeds", exist_ok=True)

    for source in sources:
        articles = scrape_articles(source)
        rss = build_rss(source, articles)

        output_path = f'feeds/{source["slug"]}.xml'
        with open(output_path, "w", encoding="utf-8") as out:
            out.write(rss)

        print(f"Generated {output_path} with {len(articles)} items")

if __name__ == "__main__":
    main()
