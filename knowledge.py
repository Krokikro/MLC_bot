import re
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent
REFERRAL_LINK = "https://my.mlc.health/bmx318"
INVESTOR_CHANNEL = "https://t.me/MLC_health_channel_en"
CACHE_TTL_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 12
SEARCH_RESULT_LIMIT = 5
PRIMARY_FACT_DOMAINS = (
    "idf.org",
    "who.int",
    "ncbi.nlm.nih.gov",
    "my.mlc.health",
    "mlc.health",
    "flystat.com",
)
LIVE_FALLBACK_SOURCES = [
    "https://idf.org/about-diabetes/diabetes-facts-figures/?locale=en",
    "https://www.who.int/diabetes/en/",
    "https://www.ncbi.nlm.nih.gov/books/NBK618744/",
]

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
        "title": "MLC project information",
        "url": "https://my.mlc.health/en/site/project-info?f=1",
        "kind": "business",
    },
    {
        "title": "Investing with MLC and CEO Ivan Saltanov",
        "url": "https://my.mlc.health/en/site/newsinfo/2704",
        "kind": "news",
    },
    {
        "title": "Global CGM market overview",
        "url": "https://my.mlc.health/en/site/newsinfo/2197",
        "kind": "market",
    },
    {
        "title": "CGM Fly competitive edge",
        "url": "https://my.mlc.health/en/site/newsinfo/2699",
        "kind": "product",
    },
    {
        "title": "CGM market growth prospects for investors",
        "url": "https://my.mlc.health/en/site/newsinfo/2692",
        "kind": "market",
    },
    {
        "title": "What MLC investors earn income from",
        "url": "https://my.mlc.health/en/site/newsinfo/2614",
        "kind": "business",
    },
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
        "title": "CGM Flystat official product highlights",
        "kind": "product",
        "source": "https://flystat.com/en",
        "content": (
            "CGM Flystat is presented as a continuous glucose monitoring system. The official site says "
            "the sensor records glucose changes every 5 minutes in real time, works for up to 15 days, "
            "supports alerts, app-based monitoring, smartwatch sync, family monitoring for up to 4 "
            "relatives, and an AI virtual assistant."
        ),
    },
    {
        "title": "MLC company and ownership positioning",
        "kind": "business",
        "source": "https://mlc.health/ and https://my.mlc.health/en/site/project-info?f=1",
        "content": (
            "MLC presents itself as an international technological company and engineering project focused on innovative "
            "health diagnostic systems. MLC says it is developing its own CGM technology, building manufacturing capacity, "
            "holding patents, and offering investors the opportunity to fund development and become co-owners of the technology project."
        ),
    },
    {
        "title": "Ivan Saltanov role",
        "kind": "business",
        "source": "https://my.mlc.health/en/site/project-info?f=1 and https://my.mlc.health/en/site/newsinfo/2704",
        "content": (
            "Ivan Saltanov is described in official MLC materials as Founder and CEO of MLC. "
            "He is presented as the founder of the project and a key spokesperson for the investment and product strategy."
        ),
    },
    {
        "title": "Global diabetes burden from IDF 2025",
        "kind": "market",
        "source": "https://idf.org/about-diabetes/diabetes-facts-figures/?locale=en",
        "content": (
            "The International Diabetes Federation says about 589 million adults aged 20 to 79 were living with diabetes in 2024, "
            "which is about 1 in 9 adults. The IDF projects about 853 million adults with diabetes by 2050. "
            "Over 4 in 5 adults with diabetes live in low- and middle-income countries."
        ),
    },
    {
        "title": "MLC and CGM market demand claims",
        "kind": "market",
        "source": "https://my.mlc.health/en/site/newsinfo/2197 and https://my.mlc.health/en/site/newsinfo/3049",
        "content": (
            "MLC news materials describe the global CGM market as growing and say one company advantage is participation in a structurally "
            "expanding market. One MLC market article states the CGM market was estimated at 3.6 billion dollars in 2020 with a projected "
            "12.1 percent compound annual growth rate from 2021 to 2028. MLC's 2026 investment article also says the project's intellectual "
            "property portfolio includes 17 patents valued at over 108 million dollars."
        ),
    },
    {
        "title": "Certification and commercialization status",
        "kind": "market",
        "source": "https://my.mlc.health/en/help/company and https://my.mlc.health/en/site/newsinfo/3031",
        "content": (
            "The MLC help section says that by spring 2026 the industrial sample was ready, internal testing and debugging were in their final stages, "
            "and the process of obtaining CE certification had already been initiated. The same help page says a limited first batch of 10,000 devices is planned "
            "for 2026 after successful testing, and that those first devices are intended for final industrial certification, field testing, and demonstration to partners and investors. "
            "MLC's 2025 results page says international memorandums were signed with partners in Saudi Arabia, the UAE, and other regions. "
            "If asked about 2027 commercialization timing, present it as a company target or expected next step after certification, not as a completed fact."
        ),
    },
    {
        "title": "Health Magazine article link",
        "kind": "article",
        "source": "https://healthmagazine.ae/press_release/19320/fly/",
        "content": (
            "There is a Health Magazine page related to Fly. If the user asks for outside media coverage or press references, "
            "you can share the Health Magazine article link directly."
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


def search_web(query: str) -> list[str]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "MLCBot/1.0 (+web search)"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    links: list[str] = []
    for tag in soup.select("a.result__a"):
        href = tag.get("href")
        if not href or not href.startswith("http"):
            continue
        if href not in links:
            links.append(href)
        if len(links) >= SEARCH_RESULT_LIMIT:
            break
    return links


def read_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return normalize_text(text)


def classify_query(query: str) -> str:
    normalized = query.lower()
    if any(word in normalized for word in {"latest", "news", "update", "updates", "recent", "expo", "article", "press", "media"}):
        return "news"
    if any(word in normalized for word in {"invest", "investment", "income", "profit", "business", "partner", "shares", "ceo", "founder", "company", "owner", "co-owner"}):
        return "business"
    if any(word in normalized for word in {"flystat", "cgm", "glucose", "sensor", "product", "device", "diabetes", "market"}):
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
            if doc.get("kind") == query_kind:
                kind_boost = 2
            elif query_kind == "business" and doc.get("kind") in {"business", "market", "news"}:
                kind_boost = 2
            elif query_kind == "product" and doc.get("kind") in {"product", "market"}:
                kind_boost = 1
            else:
                kind_boost = 0
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


def build_investment_facts_block() -> str:
    return (
        "Core investor facts to use when relevant:\n"
        "- IDF 2025 says about 589 million adults worldwide were living with diabetes in 2024, and about 853 million are projected by 2050.\n"
        "- IDF says diabetes affects about 1 in 9 adults and more than 4 in 5 adults with diabetes live in low- and middle-income countries.\n"
        "- WHO says about 830 million people worldwide have diabetes.\n"
        "- MLC materials say the CGM market was estimated at about $3.6 billion in 2020 with projected CAGR of about 12.1% from 2021 to 2028.\n"
        "- MLC materials say the project's intellectual property portfolio includes 17 patents valued at more than $108 million.\n"
        "- MLC materials say CE certification work had already been initiated by spring 2026 and that the project was moving from industrial sample readiness toward certification and commercialization."
    )


def needs_live_web_lookup(query: str) -> bool:
    normalized = query.lower()
    triggers = {
        "market size",
        "market volume",
        "market potential",
        "tam",
        "sam",
        "cagr",
        "how big is the market",
        "how many people",
        "global market",
        "diabetes numbers",
        "market forecast",
        "worldwide",
        "industry size",
    }
    return any(term in normalized for term in triggers)


def fetch_live_fact_block(query: str) -> str:
    try:
        links = search_web(query)
    except Exception:
        return ""

    blocks: list[str] = []
    for link in links:
        if not any(domain in link for domain in PRIMARY_FACT_DOMAINS):
            continue
        try:
            text = fetch_url_text(link)
        except Exception:
            continue
        chunks = split_into_chunks(text, 650)
        if not chunks:
            continue
        blocks.append(f"Live source: {link}\n{chunks[0]}")
        if len(blocks) >= 3:
            break

    if not blocks:
        for link in LIVE_FALLBACK_SOURCES:
            try:
                text = fetch_url_text(link)
            except Exception:
                continue
            chunks = split_into_chunks(text, 650)
            if not chunks:
                continue
            blocks.append(f"Live source: {link}\n{chunks[0]}")
            if len(blocks) >= 3:
                break

    return "\n\n".join(blocks)


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


def detect_resource_needs(user_text: str) -> dict:
    normalized = user_text.lower()
    return {
        "wants_presentation": any(term in normalized for term in {"presentation", "pdf", "brochure", "product pdf"}),
        "wants_marketing": any(term in normalized for term in {"marketing plan", "comp plan", "business plan", "partner plan"}),
        "wants_article": any(term in normalized for term in {"article", "press", "media", "magazine", "news link"}),
        "wants_distribution": any(term in normalized for term in {"distributor", "distribution", "dealer", "wholesale"}),
        "wants_preorder": any(term in normalized for term in {"preorder", "pre-order", "order device", "buy device", "contact form"}),
        "wants_technical_help": any(term in normalized for term in {"technical", "specification", "accuracy", "sensor", "app", "battery", "compatibility"}),
        "serious_investor": any(
            term in normalized
            for term in {
                "invest",
                "investment",
                "register",
                "join",
                "buy",
                "co-owner",
                "shares",
                "price",
                "how do i start",
                "how to start",
            }
        ),
    }


OBJECTION_HANDLERS = {
    "too risky": (
        "Address risk by emphasizing that this is not just an idea on paper: company materials describe in-house technology, patents, "
        "an assessed IP value above 108 million dollars for the Chinese market, production preparation in China, and an already built investor and partner network. "
        "Do not say risk is absent. Say the user is still evaluating execution risk, but the project shows more substance than a concept-only startup."
    ),
    "is it real": (
        "Address 'is it real' by pointing to specific proof points from company materials: industrial samples, patent portfolio, contract manufacturing preparation in China, "
        "project information pages, public news flow, official leadership identity, conferences, and product demonstrations. "
        "Also mention the Health Magazine article link if outside validation is relevant."
    ),
    "why now": (
        "Address 'why now' by combining market timing and company stage. Explain that diabetes prevalence is growing, the CGM market is expanding, "
        "and MLC positions itself at the stage between developed technology and scaling into production and certification."
    ),
    "why this company": (
        "Address 'why this company' by emphasizing that MLC presents itself as the company developing and owning the technology behind CGM Flystat, "
        "with patents, production preparation, Founder and CEO Ivan Saltanov, and a specific commercialization path rather than a generic reseller story."
    ),
    "what do investors actually own": (
        "Address ownership clearly. Company materials say investors buy investment shares tied to the project and can obtain certificates confirming ownership rights. "
        "Explain that MLC describes investors as participants in the technology project and co-owners of the development through the investment structure, "
        "with potential dividends after production launch and product sales according to company materials."
    ),
}


def detect_objection(user_text: str) -> str:
    normalized = user_text.lower()
    patterns = {
        "too risky": ["too risky", "risk", "unsafe investment", "not safe", "sounds risky"],
        "is it real": ["is it real", "real company", "real project", "scam", "fake", "proof"],
        "why now": ["why now", "why should i invest now", "why this moment", "why today"],
        "why this company": ["why mlc", "why this company", "why your company", "why not another company"],
        "what do investors actually own": [
            "what do investors actually own",
            "what do investors own",
            "what do i own",
            "what am i buying",
            "shares of what",
            "ownership",
        ],
    }
    for objection, terms in patterns.items():
        if any(term in normalized for term in terms):
            return objection
    return ""


def build_followup_memory(user: dict, user_text: str) -> str:
    sent = user.get("sent_items", {})
    needs = detect_resource_needs(user_text)
    messages: list[str] = []

    if needs["wants_presentation"] and sent.get("presentation"):
        messages.append("You already have the CGM Flystat presentation above, so let me build on that instead of resending it.")
    if needs["wants_marketing"] and sent.get("marketing"):
        messages.append("You already have the marketing plan, so I'll focus on the key investor points instead of sending the file again.")
    if needs["wants_article"] and sent.get("article"):
        messages.append("I already shared the Health Magazine article link, so I can connect it to your question directly.")
    if (needs["wants_distribution"] or needs["wants_preorder"]) and sent.get("partners_contact"):
        messages.append("I already shared the distributor and preorder contact details, so I can focus on the next practical step.")
    if needs["serious_investor"] and sent.get("referral_link"):
        messages.append("You already have the registration link, so the next step is simply to complete registration if the investment case makes sense to you.")
    if needs["serious_investor"] and sent.get("channel"):
        messages.append("You also already have the investor channel link for ongoing updates and context.")

    return " ".join(messages)


def build_sales_question(topic: str, user_text: str, user: dict) -> str:
    normalized = user_text.lower()

    if topic == "distribution":
        return "Would you like the quickest path to be the contact form or the partners email?"
    if topic == "register":
        return "What is the main thing you want to clarify before registering as an investor?"
    if topic == "business":
        if any(term in normalized for term in {"risk", "risky", "safe", "real", "scam", "fake"}):
            return "What would help you feel more confident about the investment case: proof of execution, market size, or ownership structure?"
        return "What part of the investment side would you like to evaluate next: market potential, ownership, or entry options?"
    if topic == "product":
        if any(term in normalized for term in {"technical", "specification", "sensor", "accuracy", "battery", "compatibility"}):
            return "What technical detail would you like me to clarify next?"
        return "What would you like to understand next about CGM Flystat: how it works, who it is for, or why it matters commercially?"
    if topic == "greeting":
        return "What would you like to assess first: the product, the market opportunity, or the investor model?"
    if user.get("sent_items", {}).get("referral_link"):
        return "What is still holding you back from making an investment decision?"
    return "What would you like to understand better to decide whether this investment opportunity fits you?"
