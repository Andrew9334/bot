import asyncio
import logging
import os
import re

from dotenv import load_dotenv
from telegram import Bot
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, SessionPasswordNeededError
from telethon.network import ConnectionTcpFull
from telethon.tl.types import MessageEntityTextUrl

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

# Словарь для хранения соответствия ID исходных и пересланных сообщений
message_mapping = {}

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
        logger.error(f"Бот не может отправить сообщение в чат {DESTINATION_CHAT_ID}: {e}")
        exit(1)

# Инициализация клиента Telethon
client = TelegramClient(
    'session',
    API_ID,
    API_HASH,
    connection=ConnectionTcpFull,
)

# Функция для очистки текста от ссылок и лишних строк
def clean_referral_links(text):
    """
    Очищает текст от всех ссылок и лишних строк.
    Извлекает чистый Trading Pair (например, GORKUSDT), удаляя домены, параметры, круглые и квадратные скобки.
    """
    if not text:
        logger.debug("Пустой текст, пропускаем обработку")
        return text

    try:
        # Разбиваем текст на строки
        lines = text.split('\n')
        filtered_lines = []

        # Оставляем только строки с Token, Exchange, Trading Pair
        for line in lines:
            if 'Token:' in line or 'Exchange:' in line or 'Trading Pair:' in line:
                # Удаляем содержимое в круглых и квадратных скобках для Trading Pair
                if 'Trading Pair:' in line:
                    line = re.sub(r'\s*(\([^()]*\)|[[^\[\]]*])', '', line)  # Удаляем всё в круглых и квадратных скобках
                filtered_lines.append(line)

        text = '\n'.join(filtered_lines)

        # Извлекаем Trading Pair
        trading_pair_match = re.search(r'Trading Pair:\s*([A-Z0-9_-]+)', text, re.IGNORECASE)
        trading_pair = trading_pair_match.group(1) if trading_pair_match else None

        # Удаляем ссылки, сохраняя только монету в Trading Pair
        def replace_urls(match):
            url = match.group(0)
            if trading_pair:
                logger.info(f"Сохранена монета в Trading Pair: {trading_pair}")
                return f'Trading Pair: {trading_pair}'
            logger.info(f"Удалена ссылка: {url}")
            return ''

        # Шаблон для удаления ссылок, охватывающий все указанные случаи
        url_pattern = r'(https?://[^\s]+|\w+\.[^\s]+/(?:trade|exchange|spot)/[A-Z0-9_-]+(?:\?[^/]+)?|\w+\.[^\s]+/\w+-\w+\?[^/]+|\w+\.[^\s]+/\w+-\w+|\w+\.[^\s]+/\w+_\w+\?[^/]+|\w+\.[^\s]+/\w+_\w+|\w+\.[^\s]+/\w+\?[^/]+|\w+\.[^\s]+/\w+|\?ref=\w+|\?affiliate_id=\w+|\?inviteCode=\w+|\?rcode=\w+|\?from=referral&clacCode=\w+|\?channelId=\w+)'
        text = re.sub(url_pattern, replace_urls, text, flags=re.IGNORECASE)

        # Удаляем пустые строки
        text = '\n'.join(line for line in text.split('\n') if line.strip())

        # Логирование результата
        if text == text:
            logger.debug("Ссылки и лишние строки не найдены в тексте")
        else:
            logger.info("Ссылки и/или лишние строки удалены")

    except Exception as e:
        logger.error(f"Ошибка в clean_referral_links: {e}")

    return text

# Функция для проверки и замены ссылок в entities
def remove_entities_links(message):
    """
    Проверяет ссылки, встроенные в сообщение через entities, и заменяет их на текст.
    """
    text = message.text
    if not text or not message.entities:
        logger.debug("Сообщение без entities или текста")
        return text

    try:
        new_text = text
        entities = sorted(message.entities, key=lambda e: e.offset, reverse=True)
        for entity in entities:
            if isinstance(entity, MessageEntityTextUrl):
                entity_text = text[entity.offset:entity.offset + entity.length]
                logger.info(f"Найдена ссылка в entities: {entity_text} → {entity.url}")
                trading_pair_match = re.search(r'Trading Pair:\s*([A-Z0-9_-]+)', text, re.IGNORECASE)
                if trading_pair_match and entity_text == trading_pair_match.group(1):
                    logger.info(f"Замена ссылки в Trading Pair на текст: {entity_text}")
                    new_text = new_text[:entity.offset] + entity_text + new_text[entity.offset + entity.length:]
                else:
                    new_text = new_text[:entity.offset] + entity_text + new_text[entity.offset + entity.length:]
        return new_text

    except Exception as e:
        logger.error(f"Ошибка при обработке entities: {e}")
        return text

# Обработчик новых сообщений
@client.on(events.NewMessage(chats=CHANNEL_ID))
async def handler(event):
    logger.info(
        f"Новое сообщение в канале, ID: {event.message.id}, Тип: {type(event.message.media).__name__ if event.message.media else 'Text'}")
    logger.debug(f"Сырой текст сообщения: {event.message.text}")
    for attempt in range(3):
        try:
            if event.message.text:
                # Проверяем и заменяем ссылки в entities
                text_without_entities = remove_entities_links(event.message)
                # Очищаем текст от ссылок и лишних строк
                cleaned_text = clean_referral_links(text_without_entities)
                # Пересылаем только если есть Trading Pair
                if 'Trading Pair:' in cleaned_text:
                    if cleaned_text:
                        logger.info(f"Пересылаем очищенное сообщение: {cleaned_text}")
                        # Пересылаем очищенное сообщение
                        sent_message = await bot.send_message(chat_id=DESTINATION_CHAT_ID, text=cleaned_text, parse_mode=None)
                        logger.info(f"Сообщение отправлено в чат {DESTINATION_CHAT_ID}, ID: {sent_message.message_id}")
                        # Сохраняем соответствие ID исходного и пересланного сообщения
                        message_mapping[event.message.id] = sent_message.message_id
                else:
                    logger.info(f"Сообщение не содержит Trading Pair, пропускаем: {cleaned_text}")
            else:
                logger.debug("Сообщение без текста, пропускаем")
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

# Обработчик редактирования сообщений
@client.on(events.MessageEdited(chats=CHANNEL_ID))
async def edit_handler(event):
    logger.info(f"Сообщение отредактировано в канале, ID: {event.message.id}")
    logger.debug(f"Сырой текст отредактированного сообщения: {event.message.text}")
    for attempt in range(3):
        try:
            if event.message.id in message_mapping:
                forwarded_message_id = message_mapping[event.message.id]
                text_without_entities = remove_entities_links(event.message)
                cleaned_text = clean_referral_links(text_without_entities)
                if 'Trading Pair:' in cleaned_text:
                    if cleaned_text:
                        logger.info(f"Обновляем сообщение в целевом чате: {cleaned_text}")
                        await bot.edit_message_text(
                            chat_id=DESTINATION_CHAT_ID,
                            message_id=forwarded_message_id,
                            text=cleaned_text,
                            parse_mode=None
                        )
                        logger.info(f"Сообщение в чате {DESTINATION_CHAT_ID} обновлено, ID: {forwarded_message_id}")
                    else:
                        logger.warning("После очистки текст пустой, удаляем сообщение")
                        await bot.delete_message(chat_id=DESTINATION_CHAT_ID, message_id=forwarded_message_id)
                        del message_mapping[event.message.id]
                else:
                    logger.info(f"Отредактированное сообщение не содержит Trading Pair, пропускаем")
            else:
                logger.debug(f"Сообщение {event.message.id} не было пересылано ранее")
            break
        except FloodWaitError as e:
            logger.error(f"Ограничение Telegram API, ждем {e.seconds} секунд")
            await asyncio.sleep(e.seconds + 5)
            continue
        except ChatWriteForbiddenError:
            logger.error(f"Бот не имеет прав писать в чат {DESTINATION_CHAT_ID}")
            break
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения на попытке {attempt + 1}: {e}")
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
            logger.info("Клиент не авторизован, запрашиваем код...")
            sent_code = await client.send_code_request(PHONE)
            code = input("Введите код авторизации: ").strip()
            await client.sign_in(PHONE, code)
            logger.info("Клиент успешно авторизован")
        except SessionPasswordNeededError:
            password = input("Введите пароль двухфакторной аутентификации: ").strip()
            await client.sign_in(password=password)
            logger.info("Клиент успешно авторизован с двухфакторной аутентификацией")
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return

    try:
        channel = await client.get_entity(CHANNEL_ID)
        logger.info(f"Канал {channel.title} успешно найден. ID: {CHANNEL_ID}")
    except Exception as e:
        logger.error(f"Не удалось получить доступ к каналу {CHANNEL_ID}: {e}")
        return

    logger.info("Бот запущен и ожидает сообщений...")
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