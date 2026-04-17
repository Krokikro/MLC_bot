import asyncio
import json
import os
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
GREETING_WORDS = {
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "yo",
}

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = """
You are a friendly, human-like English-speaking assistant inside a Telegram bot for MLC and CGM Flystat.

Style:
- Sound natural, warm, and conversational
- Never sound robotic, scripted, or overly formal
- Keep answers clear and useful
- Use the user's name naturally when it helps
- Write in American English only

Behavior:
- Answer questions helpfully even if you do not know the exact answer
- If a detail is uncertain, say what you do know and be honest about the uncertainty
- Never invent exact dates, launch timelines, statistics, medical claims, or compensation details
- Do not say you are just a bot or refuse normal conversation unless absolutely necessary
- Softly guide interested users toward the presentation, marketing plan, or registration link when relevant

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


def update_history(user: dict, user_text: str, assistant_text: str) -> None:
    history = user.get("history", [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
    user["history"] = history[-(HISTORY_LIMIT * 2) :]


async def send_file(update: Update, path: Path, caption: str) -> None:
    if not path.exists():
        await update.message.reply_text(f"File not found: {path.name}")
        return

    with path.open("rb") as file:
        await update.message.reply_document(document=file, caption=caption)


def generate_ai_reply(user_name: str, history: list[dict], message_text: str) -> str:
    if not openai_client:
        return (
            "AI replies are not configured yet. Add OPENAI_API_KEY and try again."
        )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if user_name:
        messages.append(
            {
                "role": "system",
                "content": f"The user's name is {user_name}. Use it naturally when helpful.",
            }
        )

    messages.extend(history[-HISTORY_LIMIT:])
    messages.append({"role": "user", "content": message_text})

    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.9,
        max_tokens=300,
    )
    reply = response.choices[0].message.content or "I could not generate a reply."
    return reply.strip()


users = load_data()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user = ensure_user(user_id)
    name = user.get("name")
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

    if step == "ask_name":
        if looks_like_name(text):
            user["name"] = text
            user["step"] = "chat"
            save_data(users)
            await update.message.reply_text(
                f"Nice to meet you, {text}.\n\nWhat would you like to know about Flystat or the MLC project?"
            )
            return

        user["step"] = "chat"
        save_data(users)

    if has_trigger(text, PRESENTATION_TRIGGERS):
        await send_file(update, FLYSTAT_FILE, "Flystat presentation")
        await update.message.reply_text(
            "Here’s the presentation. If you want, I can also explain the product in simple words."
        )
        return

    if has_trigger(text, MARKETING_TRIGGERS):
        await send_file(update, MARKETING_FILE, "Marketing plan")
        await update.message.reply_text(
            "Here’s the marketing plan. If you want, I can also walk you through the business side in plain English."
        )
        return

    if has_trigger(text, REGISTER_TRIGGERS):
        await update.message.reply_text(
            "You can register here: https://mlc.health\n\nAnd if you want updates in English, here’s the channel: https://t.me/MLC_health_channel_en"
        )
        return

    user_name = user.get("name", "")
    history = user.get("history", [])

    try:
        reply = generate_ai_reply(user_name, history, text)
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
    app.run_polling()


if __name__ == "__main__":
    main()
