import asyncio
import logging
import os
import re

from dotenv import load_dotenv
from telegram import Bot
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, SessionPasswordNeededError
from telethon.network import ConnectionTcpFull

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
file_handler = logging.FileHandler("bot.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Загрузка конфигурации
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DESTINATION_CHAT_ID = os.getenv("DESTINATION_CHAT_ID")
CHANNEL_ID = -1002437017518  # ID канала

# Проверка переменных окружения
required_vars = {
    "API_ID": API_ID,
    "API_HASH": API_HASH,
    "PHONE": PHONE,
    "BOT_TOKEN": BOT_TOKEN,
    "DESTINATION_CHAT_ID": DESTINATION_CHAT_ID
}
missing_vars = [key for key, value in required_vars.items() if not value]
if missing_vars:
    logger.error(f"Отсутствуют обязательные переменные окружения: {missing_vars}")
    exit(1)

try:
    API_ID = int(API_ID)
    DESTINATION_CHAT_ID = int(DESTINATION_CHAT_ID)
except ValueError as e:
    logger.error(f"API_ID и DESTINATION_CHAT_ID должны быть числами: {e}")
    exit(1)

if not PHONE.startswith("+"):
    logger.error("PHONE должен начинаться с '+' (например, +79851056076)")
    exit(1)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)


# Проверка валидности токена
async def validate_bot_token():
    try:
        bot_info = await bot.get_me()
        logger.info(f"Токен бота действителен. Имя бота: {bot_info.username}, ID: {bot_info.id}")
    except Exception as e:
        logger.error(f"Ошибка проверки BOT_TOKEN: {e}")
        exit(1)

# Проверка прав бота
async def check_bot_permissions():
    try:
        await bot.send_message(chat_id=DESTINATION_CHAT_ID, text="Бот запущен и проверяет права...")
        logger.info(f"Бот успешно отправил тестовое сообщение в чат {DESTINATION_CHAT_ID}")
    except Exception as e:
        logger.error(f"Бот не может отправить сообщение в чат {DESTINATION_CHAT_ID}:{e}")
        exit(1)


# Инициализация клиента Telethon
client = TelegramClient(
    'session',
    API_ID,
    API_HASH,
    connection=ConnectionTcpFull,
)

# Функция для очистки реферальных ссылок
def clean_referral_links(text):
    """
    Очищает текст от всех ссылок в различных форматах (Markdown, голые URL, HTML).
    Удаляет любые URL, включая те, что не содержат явных реферальных параметров.
    """
    if not text:
        logger.debug("Пустой текст, пропускаем обработку")
        return text

    try:
        # 1. Markdown-ссылки: [текст](URL) — удаляем любые URL
        markdown_pattern = r'\[([^\]]*)\]\((https?://[^\s\)]*?)[#\)]?'
        text = re.sub(markdown_pattern, r'\1', text, flags=re.IGNORECASE)

        # 2. Голые URL: https://example.com/... — удаляем любые URL
        raw_url_pattern = r'(https?://[^\s]*?)[#]?'
        text = re.sub(raw_url_pattern, '', text, flags=re.IGNORECASE)

        # 3. HTML-ссылки: <a href="URL">текст</a> — удаляем любые URL
        html_pattern = r'<a\s+href="(https?://[^\s"]*?)"[^>]*>([^<]*)</a>'
        text = re.sub(html_pattern, r'\2', text, flags=re.IGNORECASE)

        # Логирование результата
        if text == text:
            logger.debug("Ссылки не найдены")
        else:
            logger.info("Ссылки удалены")

        return text

    except Exception as e:
        logger.error(f"Ошибка при очистке ссылок: {e}")
        return text

# Обработчик новых сообщений
@client.on(events.NewMessage(chats=CHANNEL_ID))
async def handler(event):
    logger.info(
        f"Новое сообщение в канале, ID: {event.message.id}, Тип: {type(event.message.media).__name__ if event.message.media else 'Text'}")
    for attempt in range(3):
        try:
            if event.message.text:
                # Очищаем текст от реферальных ссылок
                cleaned_text = clean_referral_links(event.message.text)
                logger.info(f"Получено текстовое сообщение: {cleaned_text}")
                await bot.send_message(chat_id=DESTINATION_CHAT_ID, text=cleaned_text, parse_mode=None)
                logger.info(f"Сообщение отправлено в чат {DESTINATION_CHAT_ID}")
            # if event.message.media:
            #     if event.message.photo:
            #         logger.info("Получено фото")
            #         file_path = await event.message.download_media(file="photo.jpg")
            #         with open(file_path, "rb") as f:
            #             await bot.send_photo(chat_id=DESTINATION_CHAT_ID, photo=f)
            #         os.remove(file_path)
            #         logger.info(f"Фото отправлено в чат {DESTINATION_CHAT_ID}")
            #     elif event.message.video:
            #         logger.info("Получено видео")
            #         file_path = await event.message.download_media(file="video.mp4")
            #         with open(file_path, "rb") as f:
            #             await bot.send_video(chat_id=DESTINATION_CHAT_ID, video=f)
            #         os.remove(file_path)
            #         logger.info(f"Видео отправлено в чат {DESTINATION_CHAT_ID}")
            #     elif event.message.document:
            #         logger.info("Получен документ")
            #         file_path = await event.message.download_media(file="document")
            #         with open(file_path, "rb") as f:
            #             await bot.send_document(chat_id=DESTINATION_CHAT_ID, document=f)
            #         os.remove(file_path)
            #         logger.info(f"Документ отправлено в чат {DESTINATION_CHAT_ID}")
            break
        except FloodWaitError as e:
            logger.error(f"Ограничение Telegram API, ждем {e.seconds} секунд")
            await asyncio.sleep(e.seconds + 5)
            continue
        except ChatWriteForbiddenError:
            logger.error(f"Бот не имеет прав писать в чат {DESTINATION_CHAT_ID}")
            break
        except Exception as e:
            logger.error(f"Ошибка на попытке {attempt + 1}: {e}")
            if attempt == 2:
                await bot.send_message(chat_id=DESTINATION_CHAT_ID, text=f"Ошибка в боте: {e}")
            await asyncio.sleep(1)

# Основная функция
async def main():
    await validate_bot_token()
    await check_bot_permissions()

    await client.connect()
    if not client.is_connected():
        logger.error("Не удалось подключиться к Telegram.")
        return

    if not await client.is_user_authorized():
        try:
            sent_code = await client.send_code_request(PHONE)
            code = input("Введите код авторизации: ").strip()
            await client.sign_in(PHONE, code)
        except SessionPasswordNeededError:
            password = input("Введите пароль двухфакторной аутентификации: ").strip()
            await client.sign_in(password=password)
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return

    # Проверка доступа к каналу
    try:
        channel = await client.get_entity(CHANNEL_ID)
        logger.info(f"Канал {channel.title} успешно найден.")
    except Exception as e:
        logger.error(f"Не удалось получить доступ к каналу {CHANNEL_ID}: {e}")
        return

    await client.run_until_disconnected()

# Перезапуск при сбоях
async def run_bot():
    max_retries = 5
    retry_count = 0
    while retry_count < max_retries:
        try:
            await main()
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"Бот упал (попытка {retry_count}/{max_retries}): {e}")
            await bot.send_message(chat_id=DESTINATION_CHAT_ID, text=f"Бот упал: {e}. Перезапуск...")
            if retry_count == max_retries:
                await bot.send_message(chat_id=DESTINATION_CHAT_ID, text="Бот остановлен: исчерпаны попытки.")
                break
            await asyncio.sleep(10)

# Запуск программы
if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем")
        asyncio.run(bot.send_message(chat_id=DESTINATION_CHAT_ID, text="Бот остановлен пользователем."))
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")