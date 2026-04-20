import asyncio
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError
from openai import OpenAI
from openai import AuthenticationError
from openai import OpenAIError
from openai import RateLimitError
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from knowledge import INVESTOR_CHANNEL
from knowledge import REFERRAL_LINK
from knowledge import build_followup_memory
from knowledge import build_investment_facts_block
from knowledge import build_sales_question
from knowledge import detect_objection
from knowledge import detect_resource_needs
from knowledge import fetch_live_fact_block
from knowledge import merge_sales_cta
from knowledge import needs_live_web_lookup
from knowledge import OBJECTION_HANDLERS
from knowledge import select_relevant_context

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"
FLYSTAT_FILE = BASE_DIR / "flystat.pdf"
MARKETING_FILE = BASE_DIR / "marketing.pdf"
VIDEO_LINK = "https://www.youtube.com/watch?v=mYzSyPbhhlU"
TECH_EMAIL = "company@mlc.health"
PARTNERS_EMAIL = "partners@mlc.health"
CONTACT_FORM = "https://flystat.com/ru/contacts"
HISTORY_LIMIT = 12
PRESENTATION_TRIGGERS = {
    "presentation",
    "presentations",
    "product pdf",
    "flystat pdf",
    "cgm flystat pdf",
    "send presentation",
    "send me presentation",
    "brochure",
    "catalog",
}
MARKETING_TRIGGERS = {
    "marketing plan",
    "plan pdf",
    "comp plan",
    "compensation plan",
    "marketing pdf",
    "investment file",
    "send marketing",
    "send me marketing",
    "business plan",
    "partner plan",
    "commercialization",
    "commercialisation",
    "monetization",
    "монетизация",
    "монетиз",
    "коммерциализация",
    "комерциализация",
    "комерцилизация",
    "маркетинг план",
    "маркетинг-план",
    "маркетинг",
    "маркетинг pdf",
    "маркетинг пдф",
    "план маркетинга",
    "партнерский план",
    "партнерская программа",
    "компенсационный план",
}
CONVERSATION_END_TRIGGERS = {
    "no",
    "nope",
    "nah",
    "not now",
    "maybe later",
    "no thanks",
    "no thank you",
    "nothing else",
    "nothing more",
    "no more questions",
    "no more question",
    "that is all",
    "that's all",
    "all clear",
    "clear now",
    "got it",
    "understood",
    "thanks that is all",
    "thank you that is all",
    "no questions",
    "bye",
    "goodbye",
    "see you",
    "talk later",
    "let's stop here",
    "lets stop here",
    "finish",
    "done",
}
REGISTER_TRIGGERS = {"register", "registration", "sign up", "signup", "join", "website", "link"}
DISTRIBUTOR_TRIGGERS = {"distributor", "distribution", "preorder", "pre-order", "wholesale", "dealer", "contacts form"}
GREETING_TRIGGERS = {
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "how are you",
}
PRODUCT_HINTS = {
    "flystat",
    "cgm",
    "glucose",
    "sensor",
    "monitor",
    "monitoring",
    "device",
    "product",
}
BUSINESS_HINTS = {
    "business",
    "partner",
    "income",
    "earn",
    "earning",
    "investment",
    "commission",
    "referral",
    "marketing",
    "monetization",
    "commercialization",
    "commercialisation",
    "investor",
    "business model",
    "partner program",
    "монетизация",
    "коммерциализация",
    "комерциализация",
    "комерцилизация",
    "инвестор",
    "инвестора",
    "инвесторов",
    "доход",
    "заработок",
    "прибыль",
    "партнерка",
    "партнерский",
    "реферальная программа",
    "привлечение инвесторов",
    "новых инвесторов",
}
GREETING_WORDS = {
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "yo",
}
NAME_BLOCKLIST_WORDS = {
    "send",
    "marketing",
    "plan",
    "investment",
    "investor",
    "business",
    "product",
    "register",
    "join",
    "presentation",
    "commercialization",
    "commercialisation",
    "monetization",
    "hello",
    "hi",
    "hey",
    "как",
    "что",
    "где",
    "нужен",
    "нужна",
    "маркетинг",
    "план",
    "инвестор",
    "инвестора",
    "инвесторов",
    "инвестиции",
    "монетизация",
    "коммерциализация",
    "комерциализация",
    "комерцилизация",
    "презентация",
    "регистрация",
    "партнер",
    "партнерский",
    "проект",
}
NAME_PREFIX_PATTERNS = [
    re.compile(r"(?:^|[,\s])i am\s+([a-zA-Z][a-zA-Z\-']{1,29})(?:$|[.!?])", re.IGNORECASE),
    re.compile(r"(?:^|[,\s])i'm\s+([a-zA-Z][a-zA-Z\-']{1,29})(?:$|[.!?])", re.IGNORECASE),
    re.compile(r"(?:^|[,\s])my name is\s+([a-zA-Z][a-zA-Z\-']{1,29})(?:$|[.!?])", re.IGNORECASE),
    re.compile(r"(?:^|[,\s])меня зовут\s+([a-zA-Zа-яА-ЯёЁ][a-zA-Zа-яА-ЯёЁ\-']{1,29})(?:$|[.!?])", re.IGNORECASE),
    re.compile(r"(?:^|[,\s])я\s+([a-zA-Zа-яА-ЯёЁ][a-zA-Zа-яА-ЯёЁ\-']{1,29})(?:$|[.!?])", re.IGNORECASE),
]

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
APP_VERSION = (os.getenv("RAILWAY_GIT_COMMIT_SHA") or "local")[:7]
FOLLOWUP_AFTER_SECONDS = 24 * 60 * 60
FOLLOWUP_CHECK_INTERVAL_SECONDS = 10 * 60
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = """
You are a persuasive but credible English-speaking sales assistant for MLC and CGM Flystat inside a Telegram bot.

Style:
- Sound natural, warm, and conversational
- Never sound robotic, scripted, sales-spammy, or overly formal
- Keep answers clear and useful
- Use the user's name naturally when it helps
- Write in American English only
- Answer first, then guide
- Prefer 2 to 4 sentences unless the user asks for more detail
- Keep replies compact and high-signal
- Avoid repetitive openings like "Certainly", "Of course", or "I'd be happy to"
- Do not end with a question unless a clarification or next step is genuinely useful

Behavior:
- Answer the actual question directly before anything else
- Rely on the provided source context from PDFs, official sites, and company news
- When the available source context contains numbers, use those numbers in your answer when relevant
- If a detail is uncertain, say what the available materials show and be honest about the uncertainty
- Never invent exact dates, launch timelines, statistics, medical claims, or compensation details
- Do not say you are just a bot or refuse normal conversation unless absolutely necessary
- Your commercial goal is to help the visitor see the advantages of becoming an investor in the project
- When appropriate, move the user toward registration through the referral link and, for serious investor interest, toward the investor Telegram channel
- Ask a follow-up question only if the user’s request is too vague to answer usefully
- If a resource would help, mention it naturally rather than forcing it into every answer
- When the user raises an objection, handle the objection directly and concretely before suggesting a next step
- Prefer objection handling over repeating the same links again and again
- End each substantive reply with one open-ended question that matches the user's topic
- Your goal is to answer questions so clearly that the user has fewer or no unresolved questions left
- Do not try to close the conversation yourself until the user clearly confirms they have no more questions
- Primary goal: convert relevant traffic into investor registration through the referral link
- Secondary goals: answer CGM Flystat product questions clearly, help with preorder/distributor requests, and route technical unknowns to the correct email
- Do not mention the technical email unless the user explicitly asks for technical escalation or the answer is genuinely unavailable from the provided materials

Project context:
- CGM Flystat is a continuous glucose monitoring system
- It works in real time and helps users monitor glucose changes
- It is designed to be convenient and easy to use

Business context:
- MLC includes a partner and referral model
- Users may be interested in product information, business opportunities, and registration

Useful resources:
- Presentation is available on request
- Marketing plan is available on request
- Referral registration link: https://my.mlc.health/bmx318
- Investor Telegram channel: https://t.me/MLC_health_channel_en
- Technical contact email: company@mlc.health
- Distributor and preorder contact email: partners@mlc.health
- Distributor and preorder contact form: https://flystat.com/ru/contacts
""".strip()


def load_data() -> dict:
    if not DATA_FILE.exists():
        return {}

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    return data if isinstance(data, dict) else {}


def save_data(data: dict) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def normalize_text(text: str) -> str:
    return text.strip().lower()


def normalize_branding(text: str) -> str:
    updated = re.sub(r"(?<!CGM\s)\bFlystat\b", "CGM Flystat", text)
    updated = re.sub(r"\bCGM CGM Flystat\b", "CGM Flystat", updated)
    return updated


def append_sales_question(reply: str, topic: str, user_text: str, user: dict) -> str:
    question = build_sales_question(topic, user_text, user)
    if not question:
        return reply

    stripped = reply.rstrip()
    if "?" in stripped[-180:]:
        return stripped
    return f"{stripped}\n\n{question}"


async def send_closing_resources(update: Update, user: dict) -> None:
    if not user.get("sent_items", {}).get("marketing"):
        await send_file(update, MARKETING_FILE, "Marketing plan")
        mark_sent(user, "marketing")

    resources = (
        "Thanks for the conversation. I’m always here if new questions come up.\n\n"
        "Useful links:\n"
        f"- Investor registration: {REFERRAL_LINK}\n"
        f"- Investor channel: {INVESTOR_CHANNEL}\n"
        f"- Distributor/preorder form: {CONTACT_FORM}"
    )
    remember_assistant_message(user, resources)
    await update.message.reply_text(resources)


def ensure_user(user_id: str) -> dict:
    if user_id not in users:
        users[user_id] = {"step": "ask_name", "history": [], "sent_items": {}}

    users[user_id].setdefault("history", [])
    users[user_id].setdefault("step", "ask_name")
    users[user_id].setdefault("sent_items", {})
    users[user_id].setdefault("chat_id", None)
    users[user_id].setdefault("last_user_message_at", None)
    users[user_id].setdefault("followup_sent_at", None)
    users[user_id].setdefault("last_assistant_message", "")
    return users[user_id]


def has_trigger(text: str, phrases: set[str]) -> bool:
    normalized = normalize_text(text)
    return any(phrase in normalized for phrase in phrases)


def remember_assistant_message(user: dict, text: str) -> None:
    user["last_assistant_message"] = text.strip()


def wants_marketing_plan(text: str) -> bool:
    normalized = normalize_text(text)
    if has_trigger(normalized, MARKETING_TRIGGERS):
        return True

    investor_terms = {
        "investor",
        "investors",
        "investment",
        "investments",
        "инвестор",
        "инвестора",
        "инвесторов",
        "инвестиции",
        "инвестиций",
    }
    monetization_terms = {
        "commercialization",
        "commercialisation",
        "monetization",
        "monetisation",
        "business model",
        "partner program",
        "partner plan",
        "compensation",
        "commission",
        "referral",
        "рефераль",
        "монетиз",
        "коммерциал",
        "комерциал",
        "комерци",
        "партнерск",
        "маркетинг",
        "доход",
        "заработ",
        "прибыл",
        "привлечен",
        "новых инвесторов",
    }

    has_investor_context = any(term in normalized for term in investor_terms)
    has_monetization_context = any(term in normalized for term in monetization_terms)
    direct_business_request = any(
        phrase in normalized
        for phrase in {
            "как зарабатывает инвестор",
            "как инвестору заработать",
            "инструмент монетизации",
            "быстрая монетизация",
            "быстрой монетизации",
            "привлечение инвесторов",
            "для инвестора",
        }
    )
    return direct_business_request or (has_investor_context and has_monetization_context)


def assistant_invited_next_step(user: dict) -> bool:
    last_message = normalize_text(user.get("last_assistant_message", ""))
    if not last_message:
        return False

    prompt_markers = {
        "would you like",
        "what would",
        "what do you want",
        "what would be more interesting",
        "what is the main thing",
        "what part",
        "what technical detail",
        "which option",
        "contact form or the partners email",
        "contact form or the partner email",
        "the product or the investment side",
        "what would you like to look at now",
        "what would you like to know first",
        "what would you like to assess first",
        "what would you like to understand",
        "what is still holding you back",
        "if you want, i can also",
        "if you'd like to move forward",
        "what decision are you leaning toward",
    }
    return "?" in last_message[-180:] or any(marker in last_message for marker in prompt_markers)


def is_conversation_end(text: str, user: dict) -> bool:
    normalized = normalize_text(text)
    contextual_negative_matches = {
        "no",
        "nope",
        "nah",
        "not now",
        "maybe later",
        "no thanks",
        "no thank you",
        "nothing else",
        "nothing more",
    }
    unconditional_endings = {
        "bye",
        "goodbye",
        "see you",
        "talk later",
        "finish",
        "done",
    }
    if normalized in unconditional_endings:
        return True
    if normalized in contextual_negative_matches:
        return assistant_invited_next_step(user)
    return any(phrase in normalized for phrase in CONVERSATION_END_TRIGGERS)


def detect_topic(text: str) -> str:
    normalized = normalize_text(text)

    if any(phrase in normalized for phrase in DISTRIBUTOR_TRIGGERS):
        return "distribution"
    if any(phrase in normalized for phrase in REGISTER_TRIGGERS):
        return "register"
    if any(phrase in normalized for phrase in MARKETING_TRIGGERS | BUSINESS_HINTS):
        return "business"
    if any(phrase in normalized for phrase in PRESENTATION_TRIGGERS | PRODUCT_HINTS):
        return "product"
    if any(phrase in normalized for phrase in GREETING_TRIGGERS):
        return "greeting"
    return "general"


def looks_like_name(text: str) -> bool:
    cleaned = text.strip()
    normalized = normalize_text(cleaned)

    if not cleaned or "?" in cleaned:
        return False

    if normalized in GREETING_WORDS:
        return False

    if (
        has_trigger(normalized, PRESENTATION_TRIGGERS | MARKETING_TRIGGERS | REGISTER_TRIGGERS | DISTRIBUTOR_TRIGGERS)
        or any(phrase in normalized for phrase in BUSINESS_HINTS)
        or normalized.startswith(("how ", "what ", "where ", "why ", "when ", "как ", "что ", "где ", "зачем "))
    ):
        return False

    words = [word for word in cleaned.replace(".", " ").split() if word]
    if len(words) == 0 or len(words) > 3:
        return False

    for word in words:
        if not word.replace("-", "").isalpha():
            return False
        if word.lower() in NAME_BLOCKLIST_WORDS:
            return False

    return True


def extract_name(text: str) -> str | None:
    cleaned = text.strip()

    for pattern in NAME_PREFIX_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            return match.group(1).strip().title()

    if looks_like_name(cleaned):
        return cleaned.strip().title()

    return None


def clean_stored_name(value: str | None) -> str | None:
    if not value:
        return None

    extracted = extract_name(value)
    if extracted:
        return extracted

    if not looks_like_name(value):
        return None

    return value.strip().title()


def update_history(user: dict, user_text: str, assistant_text: str) -> None:
    history = user.get("history", [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
    user["history"] = history[-(HISTORY_LIMIT * 2) :]


def build_system_messages(user_name: str, topic: str) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if user_name:
        messages.append(
            {
                "role": "system",
                "content": f"The user's name is {user_name}. Use it naturally only when it feels human and not on every reply.",
            }
        )

    topic_guidance = {
        "greeting": "The user is greeting you. Reply briefly and naturally, then move the conversation forward without sounding scripted.",
        "product": "The user is asking about the product side. Explain simply, concretely, and like a smart human consultant. If relevant, connect product traction to investor upside.",
        "business": "The user is asking about the business or earning side. Explain clearly and realistically, without hype or made-up specifics. Use numerical facts from the provided context whenever they strengthen the investment case.",
        "distribution": "The user is asking about becoming a distributor or making a preorder. Answer directly with the form URL and partner email, explain the next step clearly, and do not push the investment route in that reply.",
        "register": "The user is asking how to join or register. Give the registration link directly and add one short helpful line.",
        "general": "The user is having a normal conversation or asking a general question. Answer naturally and keep momentum. If the user is exploring investment logic, use concrete numbers from the provided context where relevant.",
    }
    messages.append(
        {"role": "system", "content": topic_guidance.get(topic, topic_guidance["general"])}
    )
    messages.append(
        {
            "role": "system",
            "content": (
                "Always refer to the product as CGM Flystat, not just Flystat. "
                "When describing MLC, make it clear that MLC is the company developing and owning the technology, "
                "and that the investment proposition is participation in that technology project as a co-owner according to company materials. "
                "If the user mentions Ivan Saltanov, identify him as Founder and CEO of MLC according to official MLC materials. "
                "If the user mentions Sergey Melenkov, identify him as co-founder of MLC and Technical Director responsible for all stages of CGM Flystat development and production. "
                "If the user mentions Elena Saltanova, identify her as co-founder of MLC responsible for Public Relations and International Development. "
                f"If a technical question cannot be answered confidently from the available materials, direct the user to {TECH_EMAIL}. "
                f"If the user wants preorder or distributor information, direct them to {CONTACT_FORM} or {PARTNERS_EMAIL}."
            ),
        }
    )
    return messages


def build_direct_reply(topic: str) -> str | None:
    if topic == "greeting":
        return "Hey. MLC is a health-tech company developing its own CGM Flystat continuous glucose monitoring system and inviting investors to participate in the growth of that technology project. What would you like to know first?"
    if topic == "distribution":
        return (
            f"For a distributor request or preorder, the fastest option is the contact form: {CONTACT_FORM}\n\n"
            f"If you prefer email, use {PARTNERS_EMAIL}."
        )
    if topic == "register":
        return (
            f"You can register here using my referral link: {REFERRAL_LINK}\n\n"
            f"If you're looking at the investment side seriously, you can also follow the investor channel: {INVESTOR_CHANNEL}"
        )
    return None


async def send_file(update: Update, path: Path, caption: str) -> None:
    if not path.exists():
        await update.message.reply_text(f"File not found: {path.name}")
        return

    with path.open("rb") as file:
        await update.message.reply_document(document=file, caption=caption)


def mark_sent(user: dict, item: str) -> None:
    sent = user.setdefault("sent_items", {})
    sent[item] = True


def generate_ai_reply(user: dict, user_name: str, history: list[dict], message_text: str, topic: str) -> str:
    if not openai_client:
        return (
            "AI replies are not configured yet. Add OPENAI_API_KEY and try again."
        )

    messages = build_system_messages(user_name, topic)
    knowledge_context = select_relevant_context(message_text)
    investment_facts_block = build_investment_facts_block() if topic in {"business", "general"} else ""
    live_fact_block = fetch_live_fact_block(message_text) if needs_live_web_lookup(message_text) else ""
    followup_memory = build_followup_memory(user, message_text)
    objection = detect_objection(message_text)
    messages.append(
        {
            "role": "system",
            "content": (
                "Use this source context when answering. Prefer these materials over generic assumptions.\n\n"
                f"{knowledge_context}"
            ),
        }
    )
    if investment_facts_block:
        messages.append(
            {
                "role": "system",
                "content": f"Always-consider investor facts block:\n{investment_facts_block}",
            }
        )
    if live_fact_block:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Additional live web facts for this question from primary or trusted sources. "
                    "Use them when relevant and mention uncertainty if figures differ across sources.\n\n"
                    f"{live_fact_block}"
                ),
            }
        )
    if followup_memory:
        messages.append(
            {
                "role": "system",
                "content": f"Conversation memory about already shared materials: {followup_memory}",
            }
        )
    if objection:
        messages.append(
            {
                "role": "system",
                "content": f"Detected objection: {objection}. Handling guidance: {OBJECTION_HANDLERS[objection]}",
            }
        )
    messages.extend(history[-HISTORY_LIMIT:])
    messages.append({"role": "user", "content": message_text})

    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=220,
    )
    reply = response.choices[0].message.content or "I could not generate a reply."
    return reply.strip()


users = load_data()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user = ensure_user(user_id)
    name = clean_stored_name(user.get("name"))
    user["name"] = name
    if not name:
        user["step"] = "ask_name"
    else:
        user["step"] = "chat"
    user["history"] = []
    user["chat_id"] = update.effective_chat.id
    save_data(users)

    if name:
        welcome_text = (
            f"Welcome back, {name}.\nMLC is a health-tech company developing its own CGM Flystat continuous glucose monitoring system, and investors can participate in the growth of that technology project.\n\nWhat would you like to look at now: the product side or the investment side?"
        )
        remember_assistant_message(user, welcome_text)
        await update.message.reply_text(welcome_text)
        return

    start_text = (
        "Hey. MLC is a health-tech company developing its own CGM Flystat continuous glucose monitoring system, and investors can participate in the growth of that technology project.\n\nWhat’s your name?"
    )
    remember_assistant_message(user, start_text)
    await update.message.reply_text(start_text)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    users[user_id] = {"step": "ask_name", "history": [], "sent_items": {}, "chat_id": update.effective_chat.id, "last_user_message_at": None, "followup_sent_at": None, "last_assistant_message": ""}
    save_data(users)
    reset_text = "State cleared. What’s your name?"
    remember_assistant_message(users[user_id], reset_text)
    await update.message.reply_text(reset_text)


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    version_text = f"Bot version: {APP_VERSION}"
    user = ensure_user(str(update.effective_user.id))
    remember_assistant_message(user, version_text)
    await update.message.reply_text(version_text)


async def followup_loop(application) -> None:
    while True:
        now = int(time.time())
        dirty = False
        for user in users.values():
            chat_id = user.get("chat_id")
            last_user_message_at = user.get("last_user_message_at")
            followup_sent_at = user.get("followup_sent_at")
            name = clean_stored_name(user.get("name")) or "there"

            if not chat_id or not last_user_message_at:
                continue
            if user.get("step") == "ask_name":
                continue
            if followup_sent_at and followup_sent_at >= last_user_message_at:
                continue
            if now - int(last_user_message_at) < FOLLOWUP_AFTER_SECONDS:
                continue

            text = (
                f"Hi {name}, I just wanted to check in. What decision are you leaning toward on the investment side, "
                "or what is still making you hesitate?"
            )
            try:
                await application.bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                continue

            remember_assistant_message(user, text)
            user["followup_sent_at"] = now
            dirty = True

        if dirty:
            save_data(users)

        await asyncio.sleep(FOLLOWUP_CHECK_INTERVAL_SECONDS)


async def post_init(application) -> None:
    application.create_task(followup_loop(application))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    user = ensure_user(user_id)
    user["name"] = clean_stored_name(user.get("name"))
    user["chat_id"] = update.effective_chat.id
    user["last_user_message_at"] = int(time.time())
    user["followup_sent_at"] = None
    step = user.get("step", "ask_name")
    topic = detect_topic(text)

    if is_conversation_end(text, user):
        closing_text = "Understood. Thanks for the conversation. If you want to come back to the product or investment side later, I’ll be here."
        remember_assistant_message(user, closing_text)
        await update.message.reply_text(closing_text)
        await send_closing_resources(update, user)
        save_data(users)
        return

    if step == "ask_name":
        extracted_name = extract_name(text)
        if extracted_name:
            user["name"] = extracted_name
            user["step"] = "chat"
            save_data(users)
            greeting_text = f"Nice to meet you, {extracted_name}."
            video_text = f"Take a quick look at this short video about the MLC project:\n{VIDEO_LINK}"
            next_step_text = "What would be more interesting to you right now: the product or the investment side of the project?"
            await update.message.reply_text(greeting_text)
            await update.message.reply_text(video_text)
            remember_assistant_message(user, next_step_text)
            await update.message.reply_text(next_step_text)
            return

        user["step"] = "chat"
        save_data(users)

    direct_reply = build_direct_reply(topic)
    if direct_reply:
        if topic == "distribution":
            mark_sent(user, "partners_contact")
        if topic == "register":
            mark_sent(user, "referral_link")
            mark_sent(user, "channel")
        direct_reply = append_sales_question(normalize_branding(direct_reply), topic, text, user)
        remember_assistant_message(user, direct_reply)
        await update.message.reply_text(direct_reply)
        save_data(users)
        return

    if has_trigger(text, PRESENTATION_TRIGGERS):
        if user.get("sent_items", {}).get("presentation"):
            presentation_text = append_sales_question(normalize_branding(
                "You already have the CGM Flystat presentation above, so let me build on it instead of sending the same PDF again."
            ), topic, text, user)
            remember_assistant_message(user, presentation_text)
            await update.message.reply_text(presentation_text)
        else:
            await send_file(update, FLYSTAT_FILE, "CGM Flystat presentation")
            mark_sent(user, "presentation")
            presentation_text = append_sales_question(normalize_branding(
                "Here’s the CGM Flystat presentation. If you want, I can also break down what the product does and why the project may be attractive from an investor perspective."
            ), topic, text, user)
            remember_assistant_message(user, presentation_text)
            await update.message.reply_text(presentation_text)
        save_data(users)
        return

    if wants_marketing_plan(text):
        if user.get("sent_items", {}).get("marketing"):
            marketing_text = append_sales_question(normalize_branding(
                "You already have the marketing plan, so let me focus on the investor logic and key numbers instead of sending the same file again."
            ), topic, text, user)
            remember_assistant_message(user, marketing_text)
            await update.message.reply_text(marketing_text)
        else:
            await send_file(update, MARKETING_FILE, "Marketing plan")
            mark_sent(user, "marketing")
            marketing_text = append_sales_question(normalize_branding(
                "Here’s the marketing plan. It is the most relevant file if you want to understand how the investor side is positioned, how the model is intended to monetize, and how partner-driven growth is presented in the project materials. If you want, I can also break down the key investor logic in plain English."
            ), topic, text, user)
            remember_assistant_message(user, marketing_text)
            await update.message.reply_text(marketing_text)
        save_data(users)
        return

    user_name = user.get("name", "")
    history = user.get("history", [])

    try:
        reply = generate_ai_reply(user, user_name, history, text, topic)
    except AuthenticationError:
        await update.message.reply_text(
            "OpenAI authentication failed. Check OPENAI_API_KEY in Railway Variables."
        )
        return
    except RateLimitError:
        await update.message.reply_text(
            "OpenAI is unavailable for this bot right now because the API quota is exhausted or billing is not active."
        )
        return
    except APIConnectionError:
        await update.message.reply_text(
            "I could not connect to OpenAI right now. Try again in a moment."
        )
        return
    except OpenAIError:
        await update.message.reply_text(
            "OpenAI returned an error. Check the model name and account status."
        )
        return

    if topic not in {"distribution"}:
        reply = merge_sales_cta(reply, text)
    reply = normalize_branding(reply)
    needs = detect_resource_needs(text)
    if (needs["wants_distribution"] or needs["wants_preorder"]) and not user.get("sent_items", {}).get("partners_contact"):
        reply = (
            f"{reply}\n\nFor a distributor request or preorder, use the contact form: {CONTACT_FORM}\n"
            f"Or email: {PARTNERS_EMAIL}"
        )
        mark_sent(user, "partners_contact")
    if ("tech email" in normalize_text(text) or "technical email" in normalize_text(text) or "who can answer" in normalize_text(text)) and TECH_EMAIL not in reply:
        reply = (
            f"{reply}\n\nIf you want a deeper technical review or a point that is not fully covered in the public materials, "
            f"you can send the request to {TECH_EMAIL}."
        )
    if needs["wants_article"] and not user.get("sent_items", {}).get("article"):
        reply = (
            f"{reply}\n\nHere is the Health Magazine article link as an outside media reference: "
            "https://healthmagazine.ae/press_release/19320/fly/"
        )
        mark_sent(user, "article")
    if REFERRAL_LINK in reply:
        mark_sent(user, "referral_link")
    if INVESTOR_CHANNEL in reply:
        mark_sent(user, "channel")
    reply = append_sales_question(reply, topic, text, user)

    update_history(user, text, reply)
    user["step"] = "chat"
    save_data(users)

    remember_assistant_message(user, reply)
    await update.message.reply_text(reply)


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Put it in .env before starting the bot.")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Python 3.14+ may not create a default event loop automatically.
    asyncio.set_event_loop(asyncio.new_event_loop())
    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
