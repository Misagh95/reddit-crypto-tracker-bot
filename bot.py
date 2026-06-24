"""
Reddit Crypto Tracker Bot
Tracks hot posts from crypto subreddits.
"""
import os
import asyncio
import logging
import html
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
SUBREDDITS = os.getenv("SUBREDDITS", "Bitcoin,CryptoCurrency,ethfinance").split(",")
LIMIT = int(os.getenv("LIMIT", "5"))

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

subscribers: set = set()
known: set = set()


def is_admin(chat_id: Any) -> bool:
    if not ADMIN_CHAT_ID:
        return True
    return str(chat_id) in ADMIN_CHAT_ID.split(",")


async def fetch_reddit(subreddit: str) -> list:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(url, headers=headers, params={"limit": LIMIT})
            if r.status_code == 200:
                return r.json().get("data", {}).get("children", [])
    except Exception as e:
        logger.warning(f"Reddit fetch failed {subreddit}: {e}")
    return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(
        "🔥 Reddit Crypto Tracker\n\n"
        "/subscribe - Subscribe\n"
        "/unsubscribe - Unsubscribe\n"
        "/hot - Show hot posts now\n"
        "/status - Status"
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    if not is_admin(update.effective_chat.id):
        return
    subscribers.add(update.effective_chat.id)
    await update.message.reply_text("✅ Subscribed.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    subscribers.discard(update.effective_chat.id)
    await update.message.reply_text("✅ Unsubscribed.")


async def cmd_hot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    lines = ["🔥 Hot Posts:\n"]
    for sub in SUBREDDITS:
        posts = await fetch_reddit(sub)
        if posts:
            lines.append(f"\n<b>r/{sub}</b>")
            for post in posts[:LIMIT]:
                p = post["data"]
                lines.append(f"• <a href='https://reddit.com{p['permalink']}'>{html.escape(p['title'][:80])}</a> ({p['ups']} upvotes)")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(f"📊 Subscribers: {len(subscribers)}\nSubreddits: {', '.join(SUBREDDITS)}")


async def monitor(app: Application) -> None:
    first_run = True
    while True:
        try:
            for sub in SUBREDDITS:
                posts = await fetch_reddit(sub)
                if first_run:
                    for post in posts:
                        known.add(post["data"]["id"])
                    continue
                for post in posts[:LIMIT]:
                    p = post["data"]
                    pid = p["id"]
                    if pid in known:
                        continue
                    known.add(pid)
                    text = (
                        f"🔥 <b>New Hot Post on r/{sub}</b>\n\n"
                        f"<a href='https://reddit.com{p['permalink']}'>{html.escape(p['title'][:200])}</a>\n\n"
                        f"👍 {p['ups']} | 💬 {p['num_comments']}"
                    )
                    for chat_id in list(subscribers):
                        try:
                            await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
                        except Exception as e:
                            logger.warning(f"Send failed: {e}")
                        await asyncio.sleep(0.3)
            first_run = False
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def post_init(application: Application) -> None:
    asyncio.create_task(monitor(application))
    commands = [BotCommand("start", "Start"), BotCommand("subscribe", "Subscribe"), BotCommand("unsubscribe", "Unsubscribe"), BotCommand("hot", "Hot posts"), BotCommand("status", "Status")]
    await application.bot.set_my_commands(commands)


def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing!")
        return
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", cmd_subscribe))
    application.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    application.add_handler(CommandHandler("hot", cmd_hot))
    application.add_handler(CommandHandler("status", cmd_status))
    application.run_polling()


if __name__ == "__main__":
    main()
