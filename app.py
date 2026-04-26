from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from re import IGNORECASE, DOTALL, finditer, sub
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import feedparser
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    kind: str = "feed"


SOURCES = [
    FeedSource("OpenAI News", "https://openai.com/news/rss.xml"),
    FeedSource("Anthropic News", "https://www.anthropic.com/news/rss.xml"),
    FeedSource("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    FeedSource("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    FeedSource("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    FeedSource("NVIDIA AI Blog", "https://blogs.nvidia.com/blog/category/ai/feed/"),
    FeedSource("VentureBeat AI", "https://venturebeat.com/ai/feed/"),
    FeedSource("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    FeedSource("MIT News AI", "https://news.mit.edu/rss/topic/artificial-intelligence2"),
    FeedSource("arXiv cs.AI", "https://export.arxiv.org/rss/cs.AI"),
    FeedSource("arXiv cs.LG", "https://export.arxiv.org/rss/cs.LG"),
    FeedSource("Hacker News AI", "https://hnrss.org/newest?q=artificial+intelligence"),
    FeedSource("AIxploria AI News", "https://www.aixploria.com/en/ai-news-today/", "html"),
]

THEME_KEYWORDS = {
    "Model Releases": ["model", "release", "launch", "open source", "weights", "checkpoint"],
    "Agents & Automation": ["agent", "workflow", "automation", "tool use", "orchestration"],
    "Research Breakthroughs": ["paper", "research", "benchmark", "arxiv", "sota", "study"],
    "Product Updates": ["api", "feature", "update", "platform", "assistant", "integration"],
    "Policy & Safety": ["safety", "policy", "governance", "regulation", "risk", "security"],
    "Business & Funding": ["startup", "funding", "acquisition", "enterprise", "revenue", "market"],
}

STOPWORDS = {
    "the",
    "a",
    "an",
    "for",
    "to",
    "and",
    "of",
    "in",
    "on",
    "with",
    "at",
    "from",
    "by",
    "is",
    "are",
    "be",
    "as",
    "new",
    "ai",
}

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Clarity-Briefing/1.0",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


def _clean_text(value: str) -> str:
    plain = sub(r"<[^>]+>", "", value or "")
    plain = unescape(plain).strip()
    return sub(r"\s+", " ", plain)


def _parse_dt(entry: dict[str, Any]) -> datetime:
    date_fields = ("published", "updated", "created")
    for field in date_fields:
        raw = entry.get(field)
        if not raw:
            continue
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except (TypeError, ValueError):
            continue
    return datetime.now(UTC)


def _source_domain(link: str) -> str:
    try:
        return urlparse(link).netloc.replace("www.", "")
    except Exception:
        return "unknown"


def _load_feed(url: str) -> feedparser.FeedParserDict:
    req = Request(url, headers=REQUEST_HEADERS)
    with urlopen(req, timeout=18) as response:
        payload = response.read()
    return feedparser.parse(payload)


def _load_html(url: str) -> str:
    req = Request(url, headers=REQUEST_HEADERS)
    with urlopen(req, timeout=18) as response:
        payload = response.read()
    return payload.decode("utf-8", errors="ignore")


def _extract_aixploria_updates(source: FeedSource, html: str, limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for match in finditer(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, IGNORECASE | DOTALL):
        href = match.group(1).strip()
        raw_text = match.group(2)
        link = urljoin(source.url, href)
        title = _clean_text(raw_text)

        if not link.startswith("https://www.aixploria.com/en/"):
            continue
        if any(
            blocked in link
            for blocked in (
                "/en/free-ai/",
                "/en/category/",
                "/en/ai-news-today/",
                "/en/tag/",
                "/en/privacy",
                "/en/contact",
            )
        ):
            continue
        if link in seen_links:
            continue
        if len(title) < 12:
            continue

        seen_links.add(link)
        items.append(
            {
                "title": title,
                "summary": "AIxploria curated AI news update.",
                "link": link,
                "source": source.name,
                "source_domain": _source_domain(link),
                "published_at": datetime.now(UTC),
            }
        )

        if len(items) >= limit:
            break

    return items


def fetch_all_updates(limit_per_source: int = 12) -> tuple[list[dict[str, Any]], list[str]]:
    updates: list[dict[str, Any]] = []
    failures: list[str] = []

    for source in SOURCES:
        if source.kind == "html":
            try:
                html = _load_html(source.url)
                html_items = _extract_aixploria_updates(source, html, limit_per_source)
                if not html_items:
                    failures.append(source.name)
                    continue
                updates.extend(html_items)
            except (TimeoutError, URLError, OSError):
                failures.append(source.name)
                continue
            continue

        try:
            parsed = _load_feed(source.url)
        except (TimeoutError, URLError, OSError):
            failures.append(source.name)
            continue

        if getattr(parsed, "bozo", False) and not parsed.entries:
            failures.append(source.name)
            continue

        for entry in parsed.entries[:limit_per_source]:
            title = _clean_text(entry.get("title", "Untitled"))
            summary = _clean_text(entry.get("summary", entry.get("description", "")))
            link = entry.get("link", "")
            published_at = _parse_dt(entry)
            updates.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "source": source.name,
                    "source_domain": _source_domain(link),
                    "published_at": published_at,
                }
            )

    updates.sort(key=lambda x: x["published_at"], reverse=True)
    return updates, failures


def _classify_theme(text: str) -> str:
    lowered = text.lower()
    for theme, words in THEME_KEYWORDS.items():
        if any(w in lowered for w in words):
            return theme
    return "General AI Developments"


ACTION_SUGGESTIONS = {
    "Model Releases": [
        "Access the model weights or API",
        "Review documentation and capabilities",
        "Try with sample data or use case",
        "Integrate into your workflow",
    ],
    "Agents & Automation": [
        "Explore workflow automation patterns",
        "Review integration options",
        "Test with your data or use case",
        "Plan implementation steps",
    ],
    "Research Breakthroughs": [
        "Read the abstract and findings",
        "Review methodology and approach",
        "Check how it applies to your work",
        "Share with your team",
    ],
    "Product Updates": [
        "Review API changes and deprecations",
        "Check documentation updates",
        "Test integration with your code",
        "Plan migration if needed",
    ],
    "Policy & Safety": [
        "Review compliance implications",
        "Assess impact on your systems",
        "Check updated guidelines",
        "Update policies if needed",
    ],
    "Business & Funding": [
        "Review market implications",
        "Assess partnership opportunities",
        "Monitor competitor activity",
        "Share insights with stakeholders",
    ],
    "General AI Developments": [
        "Bookmark for later review",
        "Share with your team",
        "Add to relevant project",
        "Follow for updates",
    ],
}


def _top_terms(updates: list[dict[str, Any]], top_n: int = 5) -> list[str]:
    words = []
    for item in updates:
        for token in sub(r"[^a-zA-Z0-9 ]", " ", item["title"]).lower().split():
            if len(token) <= 3 or token in STOPWORDS:
                continue
            words.append(token)
    return [word for word, _ in Counter(words).most_common(top_n)]


def build_digest(updates: list[dict[str, Any]], failures: list[str]) -> dict[str, Any]:
    now = datetime.now(UTC)
    recent_cutoff = now - timedelta(hours=48)
    recent = [u for u in updates if u["published_at"] >= recent_cutoff]
    baseline = recent if recent else updates[:30]

    if not updates:
        return {
            "generated_at": now.isoformat(),
            "headline_bullets": [
                "No live entries were fetched in this refresh window.",
                "This usually means your network blocked one or more feed domains temporarily.",
                "Use Refresh Briefing in a minute; source health below shows exactly what failed.",
            ],
            "theme_bullets": ["No themes available until at least one source responds."],
            "source_bullets": [f"Configured sources: {len(SOURCES)} total."],
        }

    theme_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in baseline:
        theme_groups[_classify_theme(f"{item['title']} {item['summary']}")].append(item)

    theme_bullets = []
    for theme, items in sorted(theme_groups.items(), key=lambda x: len(x[1]), reverse=True)[:4]:
        exemplar = items[0]["title"]
        theme_bullets.append(f"{theme}: {len(items)} signals. Lead item - {exemplar}")

    source_snapshot: dict[str, dict[str, Any]] = {}
    for item in updates:
        if item["source"] not in source_snapshot:
            source_snapshot[item["source"]] = item

    source_bullets = [
        f"{src}: {item['title']}"
        for src, item in list(source_snapshot.items())[:6]
    ]

    high_signal_terms = _top_terms(baseline)
    market_line = (
        "Fast-moving themes right now: " + ", ".join(high_signal_terms)
        if high_signal_terms
        else "Fast-moving themes right now: AI products, model updates, and applied workflows."
    )

    headline_bullets = [
        f"{len(recent) if recent else len(baseline)} fresh items in the last 48 hours across {len(set(u['source'] for u in updates))} active sources.",
        market_line,
        f"Source health: {len(failures)} feed(s) unavailable during this refresh."
        if failures
        else "Source health: all configured feeds responded successfully.",
    ]

    return {
        "generated_at": now.isoformat(),
        "headline_bullets": headline_bullets,
        "theme_bullets": theme_bullets,
        "source_bullets": source_bullets,
    }


def _serialize_update(item: dict[str, Any]) -> dict[str, Any]:
    theme = _classify_theme(f"{item['title']} {item['summary']}")
    return {
        "title": item["title"],
        "summary": item["summary"],
        "link": item["link"],
        "source": item["source"],
        "source_domain": item["source_domain"],
        "published_at": item["published_at"].isoformat(),
        "theme": theme,
        "id": hash(item["title"] + item["source"]) & 0x7fffffff,
    }


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/briefing")
def briefing() -> Any:
    updates, failures = fetch_all_updates()
    digest = build_digest(updates, failures)
    return jsonify(
        {
            "digest": digest,
            "updates": [_serialize_update(item) for item in updates[:40]],
            "failures": failures,
            "sources": [s.name for s in SOURCES],
        }
    )


@app.post("/api/generate-actions")
def generate_actions() -> Any:
    data = request.get_json()
    theme = data.get("theme", "General AI Developments")
    title = data.get("title", "")
    
    actions = ACTION_SUGGESTIONS.get(theme, ACTION_SUGGESTIONS["General AI Developments"])
    
    return jsonify(
        {
            "theme": theme,
            "title": title,
            "actions": actions,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
