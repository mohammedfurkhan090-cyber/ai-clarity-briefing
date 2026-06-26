from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from json import JSONDecodeError
from re import sub
from threading import Lock
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import feedparser
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from pydantic import BaseModel, Field, field_validator

try:
    from google import genai
except ImportError:  # pragma: no cover - exercised when dependencies are missing.
    genai = None

load_dotenv()

app = Flask(__name__)

CACHE_TTL_SECONDS = int(os.getenv("BRIEFING_CACHE_SECONDS", "900"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str


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
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Clarity-Briefing/2.0",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

CATEGORIES = [
    "Models",
    "Agents",
    "Research",
    "Policy",
    "Funding",
    "Products",
    "Infrastructure",
    "Safety",
]


class Citation(BaseModel):
    title: str = Field(description="Readable source or publisher name.")
    url: str = Field(description="Source URL supporting this card.")


class TrendCard(BaseModel):
    category: str = Field(description="One concise trend category.")
    title: str = Field(description="Short trend headline.")
    summary: str = Field(description="Two-sentence explanation of the movement.")
    signal_count: int = Field(ge=1, le=20, description="Number of stories supporting this trend.")
    priority: str = Field(description="One of High, Medium, or Low.")


class StoryCard(BaseModel):
    title: str = Field(description="Concise news headline.")
    source: str = Field(description="Publisher or source name.")
    url: str = Field(description="Best URL for the story.")
    published_at: str = Field(description="ISO date or readable publication date.")
    category: str = Field(description="Best category from the requested category list.")
    summary: str = Field(description="One or two sentences summarizing the story.")
    why_it_matters: str = Field(description="Practical importance for AI builders, buyers, or operators.")
    affected_groups: list[str] = Field(description="Who is likely affected by the story.")
    priority: str = Field(description="One of High, Medium, or Low.")
    confidence: str = Field(description="One of High, Medium, or Low.")
    citations: list[Citation] = Field(description="One or more supporting citations.")

    @field_validator("citations")
    @classmethod
    def require_citations(cls, value: list[Citation]) -> list[Citation]:
        if not value:
            raise ValueError("story cards must include at least one citation")
        return value


class GeminiBriefing(BaseModel):
    top_summary: str = Field(description="Executive summary for the full briefing.")
    trend_cards: list[TrendCard] = Field(min_length=3, max_length=6)
    story_cards: list[StoryCard] = Field(min_length=6, max_length=12)


class FeedItem(BaseModel):
    title: str
    summary: str
    url: str
    source: str
    source_domain: str
    published_at: str


_cache_lock = Lock()
_cached_payload: dict[str, Any] | None = None
_cached_at = 0.0


def _clean_text(value: str) -> str:
    plain = sub(r"<[^>]+>", "", value or "")
    plain = unescape(plain).strip()
    return sub(r"\s+", " ", plain)


def _parse_dt(entry: dict[str, Any]) -> datetime:
    for field in ("published", "updated", "created"):
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


def fetch_feed_updates(limit_per_source: int = 8) -> tuple[list[FeedItem], list[str]]:
    updates: list[FeedItem] = []
    failures: list[str] = []

    for source in SOURCES:
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
            url = entry.get("link", "")
            published_at = _parse_dt(entry)
            updates.append(
                FeedItem(
                    title=title,
                    summary=summary[:700],
                    url=url,
                    source=source.name,
                    source_domain=_source_domain(url),
                    published_at=published_at.isoformat(),
                )
            )

    updates.sort(key=lambda item: item.published_at, reverse=True)
    return updates, failures


def _seed_payload(updates: list[FeedItem], limit: int = 45) -> list[dict[str, str]]:
    return [
        {
            "title": item.title,
            "summary": item.summary,
            "url": item.url,
            "source": item.source,
            "published_at": item.published_at,
        }
        for item in updates[:limit]
    ]


def _briefing_prompt(feed_items: list[FeedItem]) -> str:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"""
You are the AI editor for AI Clarity Briefing. Build a current, source-backed AI news briefing for {today}.

Use these trusted feed items as seed signals, then use Google Search grounding to verify, update, and discover important current AI stories that may not be in the feeds yet.

Rules:
- Return only structured JSON matching the schema.
- Prefer news from the last 7 days. Include older items only if they are still materially relevant.
- Every story card must include at least one citation URL.
- Do not invent sources, dates, product names, funding numbers, or URLs.
- Categories must come from this list: {", ".join(CATEGORIES)}.
- Priority and confidence must be High, Medium, or Low.
- Write for founders, product leaders, engineers, analysts, and operators who need signal, not noise.

Seed feed items:
{_seed_payload(feed_items)}
""".strip()


def _gemini_client() -> Any:
    if genai is None:
        raise RuntimeError("google-genai is not installed")
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=API_KEY)


def _extract_grounding_citations(interaction: Any) -> list[dict[str, str]]:
    citations: dict[str, dict[str, str]] = {}
    for step in getattr(interaction, "steps", []) or []:
        if getattr(step, "type", None) != "model_output":
            continue
        for block in getattr(step, "content", []) or []:
            for annotation in getattr(block, "annotations", []) or []:
                if getattr(annotation, "type", None) != "url_citation":
                    continue
                url = getattr(annotation, "url", "")
                if not url:
                    continue
                citations[url] = {
                    "title": getattr(annotation, "title", "") or _source_domain(url),
                    "url": url,
                }
    return list(citations.values())


def generate_ai_briefing(feed_items: list[FeedItem]) -> tuple[GeminiBriefing, list[dict[str, str]]]:
    client = _gemini_client()
    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        input=_briefing_prompt(feed_items),
        tools=[{"type": "google_search"}],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": GeminiBriefing.model_json_schema(),
        },
    )
    briefing = GeminiBriefing.model_validate_json(interaction.output_text)
    return briefing, _extract_grounding_citations(interaction)


def _fallback_briefing(feed_items: list[FeedItem], error: str) -> dict[str, Any]:
    story_cards = []
    for item in feed_items[:10]:
        story_cards.append(
            {
                "title": item.title,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at,
                "category": _fallback_category(f"{item.title} {item.summary}"),
                "summary": item.summary or "No summary available from the source feed.",
                "why_it_matters": "AI synthesis is unavailable, so this card is showing the source feed summary directly.",
                "affected_groups": ["AI teams", "Product leaders"],
                "priority": "Medium",
                "confidence": "Medium",
                "citations": [{"title": item.source, "url": item.url}],
            }
        )

    return {
        "top_summary": "AI synthesis is unavailable. Showing the latest trusted feed items until Gemini is configured or reachable.",
        "trend_cards": [
            {
                "category": "Source Health",
                "title": "Gemini synthesis unavailable",
                "summary": error,
                "signal_count": max(1, len(feed_items)),
                "priority": "High",
            },
            {
                "category": "Feed Snapshot",
                "title": "Trusted feeds are still active",
                "summary": f"{len(feed_items)} source items were collected from configured feeds.",
                "signal_count": max(1, len(feed_items)),
                "priority": "Medium",
            },
            {
                "category": "Next Step",
                "title": "Add GEMINI_API_KEY for full AI organization",
                "summary": "Once the key is present, refresh with force mode to generate grounded briefing cards.",
                "signal_count": 1,
                "priority": "Medium",
            },
        ],
        "story_cards": story_cards,
    }


def _fallback_category(text: str) -> str:
    lowered = text.lower()
    keyword_map = {
        "Models": ("model", "release", "weights", "llm", "checkpoint"),
        "Agents": ("agent", "workflow", "automation", "tool use"),
        "Research": ("paper", "research", "benchmark", "arxiv", "study"),
        "Policy": ("policy", "regulation", "law", "governance"),
        "Funding": ("funding", "startup", "acquisition", "revenue"),
        "Products": ("api", "feature", "product", "platform"),
        "Infrastructure": ("chip", "gpu", "datacenter", "inference"),
        "Safety": ("safety", "security", "risk", "eval"),
    }
    for category, terms in keyword_map.items():
        if any(term in lowered for term in terms):
            return category
    return "Products"


def build_payload(force_refresh: bool = False) -> dict[str, Any]:
    global _cached_at, _cached_payload

    with _cache_lock:
        cache_age = monotonic() - _cached_at
        if not force_refresh and _cached_payload and cache_age < CACHE_TTL_SECONDS:
            payload = dict(_cached_payload)
            payload["cache"] = {
                "status": "hit",
                "age_seconds": int(cache_age),
                "ttl_seconds": CACHE_TTL_SECONDS,
            }
            return payload

    feed_items, failures = fetch_feed_updates()
    ai_status = "ok"
    search_status = "grounded"
    grounding_citations: list[dict[str, str]] = []

    try:
        briefing, grounding_citations = generate_ai_briefing(feed_items)
        briefing_data = briefing.model_dump()
    except Exception as exc:
        ai_status = "fallback"
        search_status = "unavailable"
        briefing_data = _fallback_briefing(feed_items, str(exc))

    payload = {
        **briefing_data,
        "generated_at": datetime.now(UTC).isoformat(),
        "model": GEMINI_MODEL,
        "source_health": {
            "configured_sources": len(SOURCES),
            "active_sources": len({item.source for item in feed_items}),
            "feed_items": len(feed_items),
            "failed_sources": failures,
            "ai_status": ai_status,
            "search_status": search_status,
        },
        "grounding_citations": grounding_citations,
        "categories": CATEGORIES,
        "cache": {
            "status": "refresh",
            "age_seconds": 0,
            "ttl_seconds": CACHE_TTL_SECONDS,
        },
    }

    with _cache_lock:
        _cached_payload = payload
        _cached_at = monotonic()

    return payload


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/briefing")
def briefing() -> Any:
    force_refresh = request.args.get("force") in {"1", "true", "yes"}
    return jsonify(build_payload(force_refresh=force_refresh))


if __name__ == "__main__":
    app.run(debug=True)


