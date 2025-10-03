import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = "7568946434:AAELic_6DXzuB21htQjElRk2hNtF3VaSnM8"


# --- Job callback to delete media after 1 hour ---
async def delete_media_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    message_id = data["message_id"]
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Deleted message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.warning(f"Failed to delete message {message_id}: {e}")


# --- Handle media messages ---
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.chat:
        return

    # Groups only
    if message.chat.type not in ["group", "supergroup"]:
        return

    # Media types (ignore text)
    has_media = any(
        [message.photo, message.video, message.document, message.audio, message.voice, message.sticker]
    )
    if not has_media:
        return

    # Check bot permission
    try:
        bot_member = await context.bot.get_chat_member(message.chat.id, context.bot.id)
        can_delete = bot_member.can_delete_messages
    except Exception as e:
        logger.warning(f"Permission check failed: {e}")
        can_delete = False

    if not can_delete:
        try:
            await message.reply_text(
                "🎐📜 ʙᴀᴋᴀᴀᴀ! ɢɪᴠᴇ ᴍᴇ ᴅᴇʟᴇᴛᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ⚠️"
            )
        except:
            pass
        return

    # Schedule deletion after 1 hour
    context.job_queue.run_once(
        delete_media_job,
        when=3600,
        data={"chat_id": message.chat.id, "message_id": message.message_id},
    )


# --- Welcome message ---
async def new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            await update.message.reply_text(
                "🎐📜 ᴀʀɪɢᴀᴛᴏ ꜰᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ 💮\nɪ'ʟʟ ᴘʀᴏᴛᴇᴄᴛ ʏᴏᴜʀ ɢʀᴏᴜᴘ!"
            )
        else:
            await update.message.reply_text(
                f"🎐 ᴡᴇʟᴄᴏᴍᴇ {member.first_name} ᴛᴏ {update.effective_chat.title}!"
            )


# --- Start command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        keyboard = [
            [
                InlineKeyboardButton("➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ᴀ ɢʀᴏᴜᴘ", url=f"https://t.me/{context.bot.username}?startgroup=true"),
            ],
            [
                InlineKeyboardButton("🎋 ᴅᴇᴠᴇʟᴏᴘᴇʀ", url="tg://user?id=8150699034"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🎐📜 ᴋᴏɴɴɪᴄʜɪᴡᴀ! ɪ'ᴍ ᴀ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ʙᴏᴛ 🌸\n\n"
            "ᴀᴅᴅ ᴍᴇ ᴛᴏ ᴀ ɢʀᴏᴜᴘ ᴀɴᴅ ɢɪᴠᴇ ᴍᴇ ᴅᴇʟᴇᴛᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ 🔑 ᴀɴᴅ ᴛʜᴇɴ ɪ'ʟʟ ꜱᴛᴀʀᴛ ᴘʀᴏᴛᴇᴄᴛɪɴɢ ʏᴏᴜʀ ɢʀᴏᴜᴘꜱ ꜰʀᴏᴍ ᴄᴏᴘʏʀɪɢʜᴛ ᴀᴛᴛᴀᴄᴋꜱ 🎗️",
            reply_markup=reply_markup,
        )
    else:
        await update.message.reply_text("ᴅᴏɴ'ᴛ ᴡᴏʀʀʏ... ɪ ᴀᴍ ᴀʟɪᴠᴇ 🪭")


# --- Main ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members))

    # Media filter (no text)
    media_filter = (
        filters.PHOTO
        | filters.VIDEO
        | filters.Document.ALL
        | filters.AUDIO
        | filters.VOICE
        | filters.Sticker.ALL
    )

    app.add_handler(MessageHandler(media_filter & filters.ChatType.GROUPS, handle_media))

    print("✅ Media Remover Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()