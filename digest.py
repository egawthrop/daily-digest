#!/usr/bin/env python3
"""Build a daily digest of the top story from each configured RSS feed.

Reads feeds.txt, fetches each feed, takes the first (top) entry, and writes:
  - index.html        the latest digest as a styled web page
  - latest.md         the latest digest as Markdown
  - archive/DATE.md   a dated copy for history

Designed to run headless on GitHub Actions, but works locally too:
    python digest.py
"""

import html
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import feedparser

ROOT = Path(__file__).resolve().parent
FEEDS_FILE = ROOT / "feeds.txt"
ARCHIVE_DIR = ROOT / "archive"

# Timezone used only for display (headers, filenames). Override with DIGEST_TZ.
DISPLAY_TZ = ZoneInfo(os.environ.get("DIGEST_TZ", "America/New_York"))

# Public base URL of your GitHub Pages site, no trailing slash. Used so the RSS
# feed can point back at itself and at your digest. Set SITE_URL in the workflow.
SITE_URL = os.environ.get("SITE_URL", "https://example.github.io/daily-digest").rstrip("/")

# How long a summary may run before we trim it.
SUMMARY_MAX_CHARS = 220


def load_feeds(path: Path):
    """Parse feeds.txt. Each line is 'Name | https://feed-url'.

    Blank lines and lines starting with # are ignored.
    """
    feeds = []
    if not path.exists():
        sys.exit(f"Missing {path.name}. Create it with lines like 'NYT | https://...'")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            print(f"  ! skipping malformed line (no '|'): {line}", file=sys.stderr)
            continue
        name, url = line.split("|", 1)
        name, url = name.strip(), url.strip()
        if name and url:
            feeds.append({"name": name, "url": url})
    if not feeds:
        sys.exit("No valid feeds found in feeds.txt.")
    return feeds


def clean_text(raw: str) -> str:
    """Strip HTML tags and collapse whitespace from a feed summary."""
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    unescaped = html.unescape(no_tags)
    collapsed = re.sub(r"\s+", " ", unescaped).strip()
    if len(collapsed) > SUMMARY_MAX_CHARS:
        collapsed = collapsed[:SUMMARY_MAX_CHARS].rstrip() + "\u2026"
    return collapsed


def format_when(entry) -> str:
    """Return a human-readable published time, or '' if unavailable."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return ""
    try:
        dt = datetime(*parsed[:6], tzinfo=ZoneInfo("UTC")).astimezone(DISPLAY_TZ)
        return dt.strftime("%b %-d, %-I:%M %p")
    except Exception:
        return ""


def fetch_top_story(feed):
    """Return a dict describing the top story, or an error marker."""
    try:
        parsed = feedparser.parse(feed["url"])
        if parsed.bozo and not parsed.entries:
            reason = getattr(parsed, "bozo_exception", "unknown parse error")
            return {"name": feed["name"], "error": str(reason)}
        if not parsed.entries:
            return {"name": feed["name"], "error": "feed had no entries"}
        top = parsed.entries[0]
        parsed_dt = top.get("published_parsed") or top.get("updated_parsed")
        published_dt = None
        if parsed_dt:
            try:
                published_dt = datetime(*parsed_dt[:6], tzinfo=ZoneInfo("UTC"))
            except Exception:
                published_dt = None
        return {
            "name": feed["name"],
            "title": clean_text(top.get("title", "Untitled")),
            "link": top.get("link", ""),
            "summary": clean_text(top.get("summary", top.get("description", ""))),
            "when": format_when(top),
            "published_dt": published_dt,
        }
    except Exception as exc:  # network hiccup, malformed feed, etc.
        return {"name": feed["name"], "error": str(exc)}


def build_rss(stories, now) -> str:
    """Emit a valid RSS 2.0 feed: one item per publication's top story.

    Point a reader (or Calibre) at this file's public URL to subscribe.
    """
    now_utc = now.astimezone(timezone.utc)
    build_date = format_datetime(now_utc)

    items = []
    for s in stories:
        if "error" in s:
            continue  # skip sources that failed today
        title = f"{s['name']}: {s['title']}"
        link = s.get("link", "")
        # A stable-ish unique id: the article URL if present, else a tag: URI.
        if link:
            guid = link
            guid_is_permalink = "true"
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            guid = f"tag:{SITE_URL},{now_utc.strftime('%Y-%m-%d')}:{slug}"
            guid_is_permalink = "false"
        pub_dt = s.get("published_dt") or now_utc
        pub_date = format_datetime(pub_dt.astimezone(timezone.utc))
        desc = s.get("summary", "")

        parts = [
            "    <item>",
            f"      <title>{xml_escape(title)}</title>",
        ]
        if link:
            parts.append(f"      <link>{xml_escape(link)}</link>")
        parts.append(f'      <guid isPermaLink="{guid_is_permalink}">{xml_escape(guid)}</guid>')
        parts.append(f"      <pubDate>{pub_date}</pubDate>")
        parts.append(f"      <source>{xml_escape(s['name'])}</source>")
        if desc:
            parts.append(f"      <description>{xml_escape(desc)}</description>")
        parts.append("    </item>")
        items.append("\n".join(parts))

    items_xml = "\n".join(items)
    feed_url = f"{SITE_URL}/feed.xml"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>The Daily Digest</title>
    <link>{xml_escape(SITE_URL)}</link>
    <atom:link href="{xml_escape(feed_url)}" rel="self" type="application/rss+xml" />
    <description>One top story from each of my chosen publications, updated daily.</description>
    <language>en</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <pubDate>{build_date}</pubDate>
    <ttl>720</ttl>
{items_xml}
  </channel>
</rss>
"""


def build_markdown(stories, now) -> str:
    lines = [
        f"# The Daily Digest",
        "",
        f"_{now.strftime('%A, %B %-d, %Y')} \u2014 generated {now.strftime('%-I:%M %p %Z')}_",
        "",
    ]
    for s in stories:
        lines.append(f"## {s['name']}")
        if "error" in s:
            lines.append(f"_Couldn't load this source: {s['error']}_")
            lines.append("")
            continue
        title = s["title"]
        lines.append(f"### [{title}]({s['link']})" if s["link"] else f"### {title}")
        if s["summary"]:
            lines.append(s["summary"])
        if s["when"]:
            lines.append(f"<sub>{s['when']}</sub>")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_html(stories, now, archive_links=None, back_link=None) -> str:
    """Render a digest page.

    archive_links: optional list of (label, href) for a "Past digests" section
                   (used on the main index page).
    back_link:     optional (label, href) shown at the top (used on archive
                   pages to get back to the latest digest).
    """
    cards = []
    for s in stories:
        name = html.escape(s["name"])
        if "error" in s:
            cards.append(
                f'<article class="card error"><p class="src">{name}</p>'
                f'<p class="err">Couldn\u2019t load this source: {html.escape(s["error"])}</p></article>'
            )
            continue
        title = html.escape(s["title"])
        link = html.escape(s["link"], quote=True)
        heading = f'<a href="{link}">{title}</a>' if s["link"] else title
        summary = f'<p class="sum">{html.escape(s["summary"])}</p>' if s["summary"] else ""
        when = f'<p class="when">{html.escape(s["when"])}</p>' if s["when"] else ""
        cards.append(
            f'<article class="card"><p class="src">{name}</p>'
            f'<h2>{heading}</h2>{summary}{when}</article>'
        )
    cards_html = "\n".join(cards)
    date_line = html.escape(now.strftime("%A, %B %-d, %Y"))
    time_line = html.escape(f"Updated {now.strftime('%-I:%M %p %Z')}")

    back_html = ""
    if back_link:
        label, href = back_link
        back_html = f'<p class="back"><a href="{html.escape(href, quote=True)}">{html.escape(label)}</a></p>'

    archive_html = ""
    if archive_links:
        items = "\n".join(
            f'<li><a href="{html.escape(href, quote=True)}">{html.escape(label)}</a></li>'
            for label, href in archive_links
        )
        archive_html = (
            '<section class="archive"><h3>Past digests</h3>'
            f'<ul>{items}</ul></section>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Daily Digest \u2014 {date_line}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root {{ --ink:#1c1917; --muted:#78716c; --line:#e7e5e4; --accent:#e1623d; --bg:#f5f5f4; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font-family:'Inter',system-ui,sans-serif; }}
  .wrap {{ max-width:44rem; margin:0 auto; padding:2rem 1.25rem 4rem; }}
  header {{ border-bottom:2px solid var(--ink); padding-bottom:1rem; margin-bottom:1.5rem; }}
  h1 {{ font-family:'Fraunces',Georgia,serif; font-weight:700; font-size:2.4rem; letter-spacing:-.02em; margin:0; }}
  .kicker {{ font-family:'IBM Plex Mono',monospace; text-transform:uppercase; letter-spacing:.15em; font-size:.7rem; color:var(--muted); margin-top:.4rem; }}
  .back {{ font-family:'IBM Plex Mono',monospace; font-size:.72rem; margin:0 0 1rem; }}
  .back a {{ color:var(--accent); text-decoration:none; }}
  .back a:hover {{ text-decoration:underline; }}
  .card {{ background:#fff; border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:.6rem; padding:1rem 1.1rem; margin-bottom:1rem; }}
  .card.error {{ border-left-color:var(--muted); }}
  .src {{ font-family:'IBM Plex Mono',monospace; text-transform:uppercase; letter-spacing:.14em; font-size:.68rem; color:var(--muted); margin:0 0 .4rem; }}
  h2 {{ font-family:'Fraunces',Georgia,serif; font-weight:600; font-size:1.2rem; line-height:1.3; margin:0; }}
  h2 a {{ color:var(--ink); text-decoration:none; }}
  h2 a:hover {{ text-decoration:underline; text-decoration-thickness:2px; text-underline-offset:2px; }}
  .sum {{ color:#44403c; font-size:.92rem; line-height:1.5; margin:.5rem 0 0; }}
  .when {{ font-family:'IBM Plex Mono',monospace; font-size:.68rem; color:var(--muted); margin:.6rem 0 0; }}
  .err {{ color:var(--muted); font-size:.88rem; margin:0; }}
  .archive {{ margin-top:2.5rem; padding-top:1.25rem; border-top:1px solid var(--line); }}
  .archive h3 {{ font-family:'IBM Plex Mono',monospace; text-transform:uppercase; letter-spacing:.14em; font-size:.7rem; color:var(--muted); margin:0 0 .75rem; }}
  .archive ul {{ list-style:none; padding:0; margin:0; display:flex; flex-wrap:wrap; gap:.5rem; }}
  .archive a {{ display:inline-block; font-size:.8rem; color:var(--ink); text-decoration:none; background:#fff; border:1px solid var(--line); border-radius:.4rem; padding:.35rem .6rem; }}
  .archive a:hover {{ border-color:var(--accent); color:var(--accent); }}
  footer {{ margin-top:2rem; font-family:'IBM Plex Mono',monospace; font-size:.68rem; color:var(--muted); text-align:center; }}
</style>
</head>
<body>
  <div class="wrap">
    {back_html}
    <header>
      <h1>The Daily Digest</h1>
      <p class="kicker">{date_line} &middot; {time_line}</p>
    </header>
    {cards_html}
    {archive_html}
    <footer>Built from RSS feeds &middot; one top story per source</footer>
  </div>
</body>
</html>
"""


def collect_archive_links(current_date_str):
    """Scan the archive folder for dated HTML pages, newest first.

    Returns a list of (label, href) where href is relative to the repo root,
    e.g. ("Jul 1", "archive/2026-07-01.html").
    """
    links = []
    for path in ARCHIVE_DIR.glob("*.html"):
        stem = path.stem  # e.g. "2026-07-01"
        try:
            d = datetime.strptime(stem, "%Y-%m-%d")
        except ValueError:
            continue
        label = d.strftime("%b %-d")
        # Distinguish years if the archive spans more than one.
        links.append((d, label, f"archive/{stem}.html"))
    links.sort(key=lambda t: t[0], reverse=True)
    # If multiple years are present, append the year to each label for clarity.
    years = {d.year for d, _, _ in links}
    if len(years) > 1:
        links = [(d, f"{lbl} {d.year}", href) for d, lbl, href in links]
    return [(lbl, href) for _, lbl, href in links]


def main():
    feeds = load_feeds(FEEDS_FILE)
    print(f"Loaded {len(feeds)} feeds.")
    stories = []
    for feed in feeds:
        print(f"  fetching {feed['name']}\u2026")
        stories.append(fetch_top_story(feed))

    now = datetime.now(DISPLAY_TZ)
    date_str = now.strftime("%Y-%m-%d")

    ARCHIVE_DIR.mkdir(exist_ok=True)

    # 1. Write today's Markdown (root + dated archive copy).
    md = build_markdown(stories, now)
    (ROOT / "latest.md").write_text(md, encoding="utf-8")
    (ARCHIVE_DIR / f"{date_str}.md").write_text(md, encoding="utf-8")

    # 1b. Write the RSS feed (one item per source) for readers / Calibre / Kobo.
    (ROOT / "feed.xml").write_text(build_rss(stories, now), encoding="utf-8")

    # 2. Write today's dated HTML archive page (with a link back to the latest).
    #    Written before we scan, so today is included in the "Past digests" list.
    archive_page = build_html(stories, now, back_link=("\u2190 Back to latest", "../index.html"))
    (ARCHIVE_DIR / f"{date_str}.html").write_text(archive_page, encoding="utf-8")

    # 3. Build the main index page with a "Past digests" list linking to archives.
    archive_links = collect_archive_links(date_str)
    (ROOT / "index.html").write_text(
        build_html(stories, now, archive_links=archive_links), encoding="utf-8"
    )

    ok = sum(1 for s in stories if "error" not in s)
    print(
        f"Done: {ok}/{len(stories)} sources loaded. "
        f"Wrote index.html, feed.xml, latest.md, and {len(archive_links)} archived day(s)."
    )


if __name__ == "__main__":
    main()
