from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ChatMemberHandler,
    ContextTypes,
)
import threading
import time

BOT_TOKEN = "7210900351:AAEiUHn7Z_wB0REQFUj2npg9AmBPwb0gFNs"


# Function to delete messages after 1 minute
def delete_later(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    time.sleep(60)
    try:
        context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass


# Handle edited messages
async def edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.edited_message is None:
        return

    user = update.edited_message.from_user
    chat_id = update.edited_message.chat.id
    message_id = update.edited_message.message_id

    # Check if bot has delete permission
    bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
    if not bot_member.can_delete_messages:
        await context.bot.send_message(
            chat_id=chat_id,
            text="ʙᴀᴋᴀ...💢..ʏᴏᴜ ᴀᴅᴅᴇᴅ ᴍᴇ ɪɴ ɢʀᴏᴜᴘ ᴛᴏ ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ ᴡɪᴛʜᴏᴜᴛ ᴇᴠᴇɴ ɢɪᴠɪɴɢ ᴍᴇ ᴀᴅᴍɪɴ/ᴅᴇʟᴇᴛᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ... 🗑️...ᴘʀᴏᴍᴏᴛᴇ ᴍᴇ ᴛᴏ ᴀᴅᴍɪɴ ᴀɴᴅ ɢɪᴠᴇ ᴍᴇ ᴅᴇʟᴇᴛᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ꜱᴏ ɪ ᴄᴀɴ ᴍᴀᴋᴇ ʏᴏᴜʀ ᴄʜᴀᴛ ꜱᴀꜰᴇ ᴀɴᴅ ᴄʟᴇᴀɴ..."
        )
        return

    # Send warning message
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Senpai...I need to delete your message under 1 minute, <b>{user.first_name}</b>",
        parse_mode="HTML",
    )

    # Delete the edited message after 1 minute
    threading.Thread(target=delete_later, args=(context, chat_id, message_id)).start()


# Send welcome message when bot is added to a group
async def welcome_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result.new_chat_member.status in ["member", "administrator"]:
        chat_id = result.chat.id

        keyboard = [
            [
                InlineKeyboardButton(
                    "Add me to another group",
                    url=f"https://t.me/{context.bot.username}?startgroup=true",
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text="🌼 ɴʏᴀᴀ~ ɪ ᴀᴍ ʏᴜᴍᴇ, ᴀɴ ᴀɴɪᴍᴇ ᴇᴅɪᴛ ᴅᴇꜰᴇɴᴅᴇʀ ʙᴏᴛ ꜰᴏʀ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴛᴏ ᴍᴀᴋᴇ ᴄʜᴀᴛꜱ ᴄʟᴇᴀɴ ᴀɴᴅ ꜱᴀꜰᴇ.\n\nᴛʜᴀɴᴋꜱ ꜰᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ! ɪ'ʟʟ ꜱᴛᴀʀᴛ ᴡᴏʀᴋɪɴɢ ꜱᴏᴏɴ. ᴀɴʏ ᴇᴅɪᴛᴇᴅ ᴍᴇꜱꜱᴀɢᴇꜱ ᴡɪʟʟ ʙᴇ ʜᴀɴᴅʟᴇᴅ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.💕",
            reply_markup=reply_markup,
        )


# Handle /start in private chat
async def start_pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌸 ɴʏᴀᴀ~ ɪ ᴀᴍ ʏᴜᴍᴇ, ᴀɴ ᴀɴɪᴍᴇ ᴇᴅɪᴛ ᴅᴇꜰᴇɴᴅᴇʀ ʙᴏᴛ ꜰᴏʀ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴛᴏ ᴍᴀᴋᴇ ᴄʜᴀᴛꜱ ᴄʟᴇᴀɴ ᴀɴᴅ ꜱᴀꜰᴇ.🍃 "
        "ᴀᴅᴅ ᴍᴇ ᴛᴏ ᴀ ɢʀᴏᴜᴘ ᴀɴᴅ ɪ ᴡɪʟʟ ᴋᴇᴇᴘ ɪᴛ ᴄʟᴇᴀɴ ꜰʀᴏᴍ ᴇᴅɪᴛᴇᴅ ᴍᴇꜱꜱᴀɢᴇꜱ!"
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Welcome message when bot is added to group
    app.add_handler(ChatMemberHandler(welcome_bot, ChatMemberHandler.MY_CHAT_MEMBER))

    # Handle edited messages
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, edited_message))

    # Handle /start in PM
    app.add_handler(CommandHandler("start", start_pm))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()