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

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"
FLYSTAT_FILE = BASE_DIR / "flystat.pdf"
MARKETING_FILE = BASE_DIR / "marketing.pdf"
HISTORY_LIMIT = 12
PRESENTATION_TRIGGERS = {"presentation", "flystat", "cgm", "product", "sensor"}
MARKETING_TRIGGERS = {"marketing", "earn", "earning", "income", "business", "investment"}
REGISTER_TRIGGERS = {"register", "registration", "sign up", "signup", "join", "website"}
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
You are a friendly, sharp, human-like English-speaking assistant inside a Telegram bot for MLC and CGM Flystat.

Style:
- Sound natural, warm, and conversational
- Never sound robotic, scripted, sales-spammy, or overly formal
- Keep answers clear and useful
- Use the user's name naturally when it helps
- Write in American English only
- Prefer 2 to 5 sentences unless the user asks for more detail
- Avoid repetitive openings like "Certainly", "Of course", or "I'd be happy to"

Behavior:
- Answer questions helpfully even if you do not know the exact answer
- If a detail is uncertain, say what you do know and be honest about the uncertainty
- Never invent exact dates, launch timelines, statistics, medical claims, or compensation details
- Do not say you are just a bot or refuse normal conversation unless absolutely necessary
- Softly guide interested users toward the presentation, marketing plan, or registration link when relevant
- If the user greets you, greet them back naturally and continue the conversation
- If the user asks a vague question, ask one short clarifying question instead of giving a generic speech
- If the user seems interested in the product, explain it in simple language first
- If the user seems interested in the business side, explain it plainly before suggesting the marketing plan
- If a resource would help, mention it naturally rather than forcing it into every answer

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
- Registration link: https://mlc.health
- English channel: https://t.me/MLC_health_channel_en
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
        users[user_id] = {"step": "ask_name", "history": []}

    users[user_id].setdefault("history", [])
    users[user_id].setdefault("step", "ask_name")
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
    return messages


def build_direct_reply(topic: str) -> str | None:
    if topic == "greeting":
        return "Hey. What would you like to know about Flystat or the MLC project?"
    if topic == "register":
        return (
            "You can register here: https://mlc.health\n\n"
            "If you want, I can also explain the product side or the business side before you sign up."
        )
    return None


async def send_file(update: Update, path: Path, caption: str) -> None:
    if not path.exists():
        await update.message.reply_text(f"File not found: {path.name}")
        return

    with path.open("rb") as file:
        await update.message.reply_document(document=file, caption=caption)


def generate_ai_reply(user_name: str, history: list[dict], message_text: str, topic: str) -> str:
    if not openai_client:
        return (
            "AI replies are not configured yet. Add OPENAI_API_KEY and try again."
        )

    messages = build_system_messages(user_name, topic)
    messages.extend(history[-HISTORY_LIMIT:])
    messages.append({"role": "user", "content": message_text})

    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.8,
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
    user["step"] = "ask_name"
    user["history"] = []
    save_data(users)

    if name:
        await update.message.reply_text(
            f"Welcome back, {name}.\nLet’s start fresh. What’s your name?"
        )
        return

    await update.message.reply_text("Hey. Welcome.\nWhat’s your name?")


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
        await update.message.reply_text(direct_reply)
        return

    if has_trigger(text, PRESENTATION_TRIGGERS):
        await send_file(update, FLYSTAT_FILE, "Flystat presentation")
        await update.message.reply_text(
            "Here’s the presentation. If you want, I can also break down what Flystat does in simple words."
        )
        return

    if has_trigger(text, MARKETING_TRIGGERS):
        await send_file(update, MARKETING_FILE, "Marketing plan")
        await update.message.reply_text(
            "Here’s the marketing plan. If you want, I can also walk you through the business side in plain English."
        )
        return

    user_name = user.get("name", "")
    history = user.get("history", [])

    try:
        reply = generate_ai_reply(user_name, history, text, topic)
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
