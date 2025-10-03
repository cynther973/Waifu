from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)
import asyncio

BOT_TOKEN = "7210900351:AAEiUHn7Z_wB0REQFUj2npg9AmBPwb0gFNs"


# handle edited messages
async def edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.edited_message:
        return

    user = update.edited_message.from_user
    chat_id = update.edited_message.chat.id
    message_id = update.edited_message.message_id

    # check if bot has delete permission
    bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
    if not bot_member.can_delete_messages:
        await context.bot.send_message(
            chat_id=chat_id,
            text="ʙᴀᴋᴀ...💢 ʏᴏᴜ ᴀᴅᴅᴇᴅ ᴍᴇ ʙᴜᴛ ᴅɪᴅɴ'ᴛ ɢɪᴠᴇ ᴅᴇʟᴇᴛᴇ ᴘᴇʀᴍɪꜱꜱɪᴏɴ. 🗑️ ᴘʀᴏᴍᴏᴛᴇ ᴍᴇ ᴛᴏ ᴀᴅᴍɪɴ!"
        )
        return

    # warn user
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"sᴇɴᴘᴀɪ... ɪ ɴᴇᴇᴅ ᴛᴏ ᴅᴇʟᴇᴛᴇ ʏᴏᴜʀ ᴇᴅɪᴛᴇᴅ ᴍᴇssᴀɢᴇ ᴜɴᴅᴇʀ 1 ᴍɪɴᴜᴛᴇ, <b>{user.first_name}</b> 💕",
        parse_mode="HTML",
    )

    # wait 1 min then delete
    await asyncio.sleep(60)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass


# welcome message when bot is added
async def welcome_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if result.new_chat_member.status in ["member", "administrator"]:
        chat_id = result.chat.id

        keyboard = [
            [InlineKeyboardButton("➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ᴀɴᴏᴛʜᴇʀ ɢʀᴏᴜᴘ", url=f"https://t.me/{context.bot.username}?startgroup=true")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text="🌼 ɴʏᴀᴀ~ ɪ ᴀᴍ ʏᴜᴍᴇ, ᴀɴ ᴀɴɪᴍᴇ ᴇᴅɪᴛ ᴅᴇꜰᴇɴᴅᴇʀ ʙᴏᴛ.\n\nᴛʜᴀɴᴋꜱ ꜰᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ! ɪ'ʟʟ ᴅᴇʟᴇᴛᴇ ᴇᴅɪᴛᴇᴅ ᴍᴇssᴀɢᴇs ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ 💕",
            reply_markup=reply_markup,
        )


# handle /start in pm
async def start_pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌸 ɴʏᴀᴀ~ ɪ ᴀᴍ ʏᴜᴍᴇ, ᴀɴ ᴀɴɪᴍᴇ ᴇᴅɪᴛ ᴅᴇꜰᴇɴᴅᴇʀ ʙᴏᴛ 🍃\n"
        "ᴀᴅᴅ ᴍᴇ ᴛᴏ ᴀ ɢʀᴏᴜᴘ ᴀɴᴅ ɪ ᴡɪʟʟ ᴅᴇʟᴇᴛᴇ ᴇᴅɪᴛᴇᴅ ᴍᴇssᴀɢᴇs!"
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # welcome when added
    app.add_handler(ChatMemberHandler(welcome_bot, ChatMemberHandler.MY_CHAT_MEMBER))

    # detect edited messages only
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, edited_message))

    # /start in pm
    app.add_handler(CommandHandler("start", start_pm))

    print("bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()