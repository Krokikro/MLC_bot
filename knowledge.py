import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent
REFERRAL_LINK = "https://my.mlc.health/bmx318"
INVESTOR_CHANNEL = "https://t.me/MLC_health_channel_en"
CACHE_TTL_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 12

PDF_SOURCES = [
    {
        "title": "CGM Flystat Presentation PDF",
        "path": BASE_DIR / "flystat.pdf",
        "kind": "product",
        "source": "local:flystat.pdf",
    },
    {
        "title": "MLC Partner Marketing Plan PDF",
        "path": BASE_DIR / "marketing.pdf",
        "kind": "business",
        "source": "local:marketing.pdf",
    },
]

WEB_SOURCES = [
    {"title": "Flystat official site", "url": "https://flystat.com/en", "kind": "product"},
    {"title": "MLC official site", "url": "https://mlc.health/", "kind": "business"},
    {
        "title": "MLC Project 2025 Results",
        "url": "https://my.mlc.health/en/site/newsinfo/3031",
        "kind": "news",
    },
    {
        "title": "10 reasons to choose MLC for investment in 2026",
        "url": "https://my.mlc.health/en/site/newsinfo/3049",
        "kind": "news",
    },
    {
        "title": "MLC goes global at World Health Expo Dubai",
        "url": "https://my.mlc.health/en/site/newsinfo/3075",
        "kind": "news",
    },
    {
        "title": "CGM technology valuation for the MLC project",
        "url": "https://my.mlc.health/en/site/newsinfo/2759",
        "kind": "news",
    },
    {
        "title": "Health Magazine article",
        "url": "https://healthmagazine.ae/press_release/19320/fly/",
        "kind": "article",
    },
]

SEED_DOCUMENTS = [
    {
        "title": "Flystat official product highlights",
        "kind": "product",
        "source": "https://flystat.com/en",
        "content": (
            "Flystat is presented as a continuous glucose monitoring system. The official site says "
            "the sensor records glucose changes every 5 minutes in real time, works for 15 days, "
            "supports alerts, app-based monitoring, smartwatch sync, family monitoring for up to 4 "
            "relatives, and an AI virtual assistant."
        ),
    },
    {
        "title": "MLC official investment overview",
        "kind": "business",
        "source": "https://mlc.health/",
        "content": (
            "MLC presents itself as an international technological platform focused on innovative "
            "health diagnostics systems. The official site describes contract manufacturing in China, "
            "in-house CGM technology, patents, production plans, and investment participation through "
            "the MLC platform."
        ),
    },
    {
        "title": "MLC official market claims",
        "kind": "business",
        "source": "https://mlc.health/",
        "content": (
            "The MLC site states that the diabetes treatment industry exceeds 75 billion dollars, "
            "that the CGM segment is growing, and that MLC positions its project as a way to "
            "participate in scaling production of its CGM system."
        ),
    },
    {
        "title": "Referral action",
        "kind": "cta",
        "source": REFERRAL_LINK,
        "content": (
            f"When the user is seriously interested in investment, guide them to register using the "
            f"referral link {REFERRAL_LINK}. If the user is seriously interested in the investment side, "
            f"also suggest the investor Telegram channel {INVESTOR_CHANNEL}."
        ),
    },
]

_CACHE = {"docs": None, "loaded_at": 0.0}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def fetch_url_text(url: str) -> str:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "MLCBot/1.0 (+knowledge fetch)"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return normalize_text(text)


def read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return normalize_text(text)


def classify_query(query: str) -> str:
    normalized = query.lower()
    if any(word in normalized for word in {"latest", "news", "update", "updates", "recent", "expo"}):
        return "news"
    if any(word in normalized for word in {"invest", "investment", "income", "profit", "business", "partner", "shares"}):
        return "business"
    if any(word in normalized for word in {"flystat", "cgm", "glucose", "sensor", "product", "device"}):
        return "product"
    return "general"


def split_into_chunks(text: str, max_len: int = 900) -> list[str]:
    cleaned = normalize_text(text)
    if not cleaned:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_len:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = sentence
    if current:
        chunks.append(current)
    return chunks


def get_documents(force_refresh: bool = False) -> list[dict]:
    now = time.time()
    if (
        not force_refresh
        and _CACHE["docs"] is not None
        and now - _CACHE["loaded_at"] < CACHE_TTL_SECONDS
    ):
        return _CACHE["docs"]

    docs = [dict(item) for item in SEED_DOCUMENTS]

    for item in PDF_SOURCES:
        try:
            docs.append(
                {
                    "title": item["title"],
                    "kind": item["kind"],
                    "source": item["source"],
                    "content": read_pdf_text(item["path"]),
                }
            )
        except Exception:
            continue

    for item in WEB_SOURCES:
        try:
            docs.append(
                {
                    "title": item["title"],
                    "kind": item["kind"],
                    "source": item["url"],
                    "content": fetch_url_text(item["url"]),
                }
            )
        except Exception:
            continue

    _CACHE["docs"] = docs
    _CACHE["loaded_at"] = now
    return docs


def select_relevant_context(query: str, limit: int = 6) -> str:
    docs = get_documents()
    query_terms = {
        term
        for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) > 2
    }
    query_kind = classify_query(query)
    scored: list[tuple[int, str]] = []

    for doc in docs:
        chunks = split_into_chunks(doc.get("content", ""))
        for chunk in chunks:
            lowered = chunk.lower()
            overlap = sum(1 for term in query_terms if term in lowered)
            kind_boost = 2 if doc.get("kind") == query_kind else 0
            news_boost = 1 if query_kind == "news" and doc.get("kind") == "news" else 0
            score = overlap + kind_boost + news_boost
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    f"Source: {doc['title']} ({doc['source']})\n{chunk}",
                )
            )

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [text for _, text in scored[:limit]]
    if not selected:
        fallback = docs[:3]
        selected = [
            f"Source: {doc['title']} ({doc['source']})\n{split_into_chunks(doc.get('content', ''), 500)[:1][0]}"
            for doc in fallback
            if split_into_chunks(doc.get("content", ""), 500)
        ]

    return "\n\n".join(selected)


def build_sales_cta(user_text: str) -> str:
    normalized = user_text.lower()
    serious_terms = {
        "invest",
        "investment",
        "investor",
        "register",
        "join",
        "buy",
        "shares",
        "package",
        "price",
        "profit",
        "income",
        "how do i start",
        "how to start",
    }

    if any(term in normalized for term in serious_terms):
        return (
            f"If you'd like to move forward, register here using my referral link: {REFERRAL_LINK}\n\n"
            f"If you're seriously considering the investment side, also follow the investor channel: {INVESTOR_CHANNEL}"
        )

    soft_terms = {"business", "partner", "marketing", "opportunity", "earning"}
    if any(term in normalized for term in soft_terms):
        return f"If you want, I can also guide you to the investor registration page: {REFERRAL_LINK}"

    return ""


def merge_sales_cta(reply: str, user_text: str) -> str:
    cta = build_sales_cta(user_text)
    if not cta:
        return reply

    additions: list[str] = []
    if REFERRAL_LINK in cta and REFERRAL_LINK not in reply:
        additions.append(f"If you'd like to move forward, register here using my referral link: {REFERRAL_LINK}")
    if INVESTOR_CHANNEL in cta and INVESTOR_CHANNEL not in reply:
        additions.append(
            f"If you're seriously considering the investment side, also follow the investor channel: {INVESTOR_CHANNEL}"
        )

    if not additions:
        return reply

    return f"{reply}\n\n" + "\n\n".join(additions)
