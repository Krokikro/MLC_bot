import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
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
YES_ANSWERS = {"yes", "y", "yeah", "yep", "sure", "ok", "okay"}
NO_ANSWERS = {"no", "n", "nope", "not now"}

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


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


def normalize_answer(text: str) -> str:
    return text.strip().lower()


async def send_file(update: Update, path: Path, caption: str) -> None:
    if not path.exists():
        await update.message.reply_text(f"File not found: {path.name}")
        return

    with path.open("rb") as file:
        await update.message.reply_document(document=file, caption=caption)


def generate_ai_reply(user_name: str, message_text: str) -> str:
    if not openai_client:
        return (
            "AI replies are not configured yet. Add OPENAI_API_KEY and try again."
        )

    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        instructions=(
            "You are an assistant for MLC and CGM Flystat prospects. "
            "Answer clearly, briefly, and helpfully. "
            "If you are unsure about business-specific facts, say so instead of inventing details."
        ),
        input=[
            {
                "role": "user",
                "content": f"User name: {user_name or 'Unknown'}\nQuestion: {message_text}",
            }
        ],
        max_output_tokens=250,
    )
    return response.output_text.strip() or "I could not generate a reply."


users = load_data()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    name = users.get(user_id, {}).get("name")

    users[user_id] = {"step": "ask_name"}
    save_data(users)

    if name:
        await update.message.reply_text(
            f"Welcome back, {name}.\nLet’s continue from the start. What’s your name?"
        )
        return

    await update.message.reply_text("Hey. Welcome.\nWhat’s your name?")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    users[user_id] = {"step": "ask_name"}
    save_data(users)
    await update.message.reply_text("State cleared. What’s your name?")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    answer = normalize_answer(text)

    if user_id not in users:
        users[user_id] = {"step": "ask_name"}

    step = users[user_id].get("step", "ask_name")

    if step == "ask_name":
        users[user_id]["name"] = text
        users[user_id]["step"] = "offer"
        save_data(users)
        await update.message.reply_text(
            f"Nice to meet you, {text}.\n\nDo you want to learn about CGM Flystat? Reply yes or no."
        )
        return

    if step == "offer":
        if answer in YES_ANSWERS:
            users[user_id]["step"] = "investment"
            save_data(users)
            await send_file(update, FLYSTAT_FILE, "Flystat presentation")
            await update.message.reply_text(
                "Here is the presentation.\nDo you want to learn about earning opportunities? Reply yes or no."
            )
            return

        if answer in NO_ANSWERS:
            users[user_id]["step"] = "offer"
            save_data(users)
            await update.message.reply_text("No problem. If you change your mind, reply yes.")
            return

        await update.message.reply_text("Please reply with yes or no.")
        return

    if step == "investment":
        if answer in YES_ANSWERS:
            users[user_id]["step"] = "completed"
            save_data(users)
            await send_file(update, MARKETING_FILE, "Marketing plan")
            await update.message.reply_text(
                "Register here: https://mlc.health\n\nJoin channel: https://t.me/MLC_health_channel_en\n\nYou can now ask me questions about MLC and CGM Flystat."
            )
            return

        if answer in NO_ANSWERS:
            users[user_id]["step"] = "completed"
            save_data(users)
            await update.message.reply_text("Okay. You can ask me anytime.")
            return

        await update.message.reply_text("Please reply with yes or no.")
        return

    if step == "completed":
        user_name = users.get(user_id, {}).get("name", "")
        try:
            reply = generate_ai_reply(user_name, text)
        except Exception:
            await update.message.reply_text(
                "I could not reach OpenAI right now. Try again in a moment."
            )
            return

        await update.message.reply_text(reply)
        return

    await update.message.reply_text("Use /start to begin again or /reset to clear the current flow.")


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
