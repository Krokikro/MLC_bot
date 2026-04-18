import asyncio
import json
import os
import re
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
from knowledge import detect_objection
from knowledge import detect_resource_needs
from knowledge import merge_sales_cta
from knowledge import OBJECTION_HANDLERS
from knowledge import select_relevant_context

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"
FLYSTAT_FILE = BASE_DIR / "flystat.pdf"
MARKETING_FILE = BASE_DIR / "marketing.pdf"
HISTORY_LIMIT = 12
PRESENTATION_TRIGGERS = {"presentation", "product pdf", "flystat pdf", "brochure", "catalog"}
MARKETING_TRIGGERS = {"marketing plan", "plan pdf", "comp plan", "compensation plan"}
REGISTER_TRIGGERS = {"register", "registration", "sign up", "signup", "join", "website", "link"}
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
NAME_PREFIX_PATTERNS = [
    re.compile(r"(?:^|[,\s])i am\s+([a-zA-Z][a-zA-Z\-']{1,29})(?:$|[.!?])", re.IGNORECASE),
    re.compile(r"(?:^|[,\s])i'm\s+([a-zA-Z][a-zA-Z\-']{1,29})(?:$|[.!?])", re.IGNORECASE),
    re.compile(r"(?:^|[,\s])my name is\s+([a-zA-Z][a-zA-Z\-']{1,29})(?:$|[.!?])", re.IGNORECASE),
]

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
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
- Prefer 2 to 6 sentences unless the user asks for more detail
- Avoid repetitive openings like "Certainly", "Of course", or "I'd be happy to"
- Do not end with a question unless a clarification or next step is genuinely useful

Behavior:
- Answer the actual question directly before anything else
- Rely on the provided source context from PDFs, official sites, and company news
- If a detail is uncertain, say what the available materials show and be honest about the uncertainty
- Never invent exact dates, launch timelines, statistics, medical claims, or compensation details
- Do not say you are just a bot or refuse normal conversation unless absolutely necessary
- Your commercial goal is to help the visitor see the advantages of becoming an investor in the project
- When appropriate, move the user toward registration through the referral link and, for serious investor interest, toward the investor Telegram channel
- Ask a follow-up question only if the user’s request is too vague to answer usefully
- If a resource would help, mention it naturally rather than forcing it into every answer
- When the user raises an objection, handle the objection directly and concretely before suggesting a next step
- Prefer objection handling over repeating the same links again and again

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


def ensure_user(user_id: str) -> dict:
    if user_id not in users:
        users[user_id] = {"step": "ask_name", "history": [], "sent_items": {}}

    users[user_id].setdefault("history", [])
    users[user_id].setdefault("step", "ask_name")
    users[user_id].setdefault("sent_items", {})
    return users[user_id]


def has_trigger(text: str, phrases: set[str]) -> bool:
    normalized = normalize_text(text)
    return any(phrase in normalized for phrase in phrases)


def detect_topic(text: str) -> str:
    normalized = normalize_text(text)

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

    words = [word for word in cleaned.replace(".", " ").split() if word]
    if len(words) == 0 or len(words) > 3:
        return False

    for word in words:
        if not word.replace("-", "").isalpha():
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

    normalized = normalize_text(value)
    if normalized in GREETING_WORDS or len(value.strip().split()) > 3:
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
        "product": "The user is asking about the product side. Explain simply, concretely, and like a smart human consultant.",
        "business": "The user is asking about the business or earning side. Explain clearly and realistically, without hype or made-up specifics.",
        "register": "The user is asking how to join or register. Give the registration link directly and add one short helpful line.",
        "general": "The user is having a normal conversation or asking a general question. Answer naturally and keep momentum.",
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
                "If the user mentions Ivan Saltanov, identify him as Founder and CEO of MLC according to official MLC materials."
            ),
        }
    )
    return messages


def build_direct_reply(topic: str) -> str | None:
    if topic == "greeting":
        return "Hey. MLC is a health-tech company developing its own CGM Flystat continuous glucose monitoring system and inviting investors to participate in the growth of that technology project. What would you like to know first?"
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
        max_tokens=320,
    )
    reply = response.choices[0].message.content or "I could not generate a reply."
    return reply.strip()


users = load_data()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user = ensure_user(user_id)
    name = clean_stored_name(user.get("name"))
    user["name"] = name
    user["step"] = "ask_name"
    user["history"] = []
    save_data(users)

    if name:
        await update.message.reply_text(
            f"Welcome back, {name}.\nMLC is a health-tech company developing its own CGM Flystat continuous glucose monitoring system, and investors can participate in the growth of that technology project.\n\nWhat’s your name?"
        )
        return

    await update.message.reply_text(
        "Hey. MLC is a health-tech company developing its own CGM Flystat continuous glucose monitoring system, and investors can participate in the growth of that technology project.\n\nWhat’s your name?"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    users[user_id] = {"step": "ask_name", "history": []}
    save_data(users)
    await update.message.reply_text("State cleared. What’s your name?")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    user = ensure_user(user_id)
    step = user.get("step", "ask_name")
    topic = detect_topic(text)

    if step == "ask_name":
        extracted_name = extract_name(text)
        if extracted_name:
            user["name"] = extracted_name
            user["step"] = "chat"
            save_data(users)
            await update.message.reply_text(
                f"Nice to meet you, {extracted_name}.\n\nWhat would you like to know about Flystat or the MLC project?"
            )
            return

        user["step"] = "chat"
        save_data(users)

    direct_reply = build_direct_reply(topic)
    if direct_reply:
        if topic == "register":
            mark_sent(user, "referral_link")
            mark_sent(user, "channel")
        await update.message.reply_text(direct_reply)
        save_data(users)
        return

    if has_trigger(text, PRESENTATION_TRIGGERS):
        if user.get("sent_items", {}).get("presentation"):
            await update.message.reply_text(
                "You already have the CGM Flystat presentation above, so let me build on it instead of sending the same PDF again."
            )
        else:
            await send_file(update, FLYSTAT_FILE, "CGM Flystat presentation")
            mark_sent(user, "presentation")
            await update.message.reply_text(
                "Here’s the CGM Flystat presentation. If you want, I can also break down what the product does and why the project may be attractive from an investor perspective."
            )
        save_data(users)
        return

    if has_trigger(text, MARKETING_TRIGGERS):
        if user.get("sent_items", {}).get("marketing"):
            await update.message.reply_text(
                "You already have the marketing plan, so let me focus on the investor logic and key numbers instead of sending the same file again."
            )
        else:
            await send_file(update, MARKETING_FILE, "Marketing plan")
            mark_sent(user, "marketing")
            await update.message.reply_text(
                "Here’s the marketing plan. If you want, I can also walk you through the business side in plain English."
            )
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

    reply = merge_sales_cta(reply, text)
    needs = detect_resource_needs(text)
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

    update_history(user, text, reply)
    user["step"] = "chat"
    save_data(users)

    await update.message.reply_text(reply)


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Put it in .env before starting the bot.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Python 3.14+ may not create a default event loop automatically.
    asyncio.set_event_loop(asyncio.new_event_loop())
    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
