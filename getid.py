from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    print(f"Chat ID: {chat_id}")
    await update.message.reply_text(f"Your chat ID: {chat_id}")

def main():
    application = Application.builder().token("7872245134:AAEfKQHYCE_lGDepGURQuewC2FWZ_rXE_G0").build()
    application.add_handler(MessageHandler(filters.TEXT, get_chat_id))
    application.run_polling()

if __name__ == "__main__":
    main()