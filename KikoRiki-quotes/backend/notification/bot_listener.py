"""Получает /start из Telegram и привязывает чат к сессии браузера."""
import hashlib
import json
import logging
import os
import re
import time
from urllib import error, parse, request

import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram-bot")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://quotes:quotes@db:5432/quotes")
START = re.compile(r"^/start(?:@\w+)? ([A-Za-z0-9_-]{32})$")


def process_update(connection, update):
    update_id = update["update_id"]
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    match = START.fullmatch(message.get("text", "")) if chat.get("type") == "private" else None
    with connection.cursor() as cursor:
        if match and isinstance(chat.get("id"), int):
            digest = hashlib.sha256(match.group(1).encode()).hexdigest()
            cursor.execute(
                """UPDATE telegram_sessions SET chat_id = %s, link_hash = NULL, link_expires_at = NULL
                   WHERE link_hash = %s AND link_expires_at > now() RETURNING session_hash""",
                (chat["id"], digest),
            )
            if cursor.fetchone():
                log.info("Telegram успешно привязан к браузеру")
        cursor.execute(
            """INSERT INTO telegram_bot_state(name, next_update_id) VALUES ('poller', %s)
               ON CONFLICT(name) DO UPDATE SET next_update_id = GREATEST(telegram_bot_state.next_update_id, EXCLUDED.next_update_id)""",
            (update_id + 1,),
        )
    connection.commit()


def main():
    if not TOKEN:
        log.error("Укажи TELEGRAM_BOT_TOKEN в .env")
        return 1
    log.info("Ожидаем команды привязки от Telegram")
    while True:
        try:
            with psycopg.connect(DATABASE_URL, connect_timeout=5) as connection:
                row = connection.execute("SELECT next_update_id FROM telegram_bot_state WHERE name = 'poller'").fetchone()
                offset = row[0] if row else 0
                connection.commit()
                params = parse.urlencode({"offset": offset, "timeout": 20, "allowed_updates": '["message"]'})
                with request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getUpdates?{params}", timeout=30) as response:
                    result = json.load(response)
                if not result.get("ok"):
                    raise ValueError("Telegram rejected request")
                for update in result.get("result", []):
                    process_update(connection, update)
        except (error.URLError, TimeoutError, OSError, ValueError, psycopg.Error, KeyError, TypeError):
            # Ошибки HTTP не печатаем: URL содержит токен бота.
            log.warning("Не удалось получить или обработать обновления Telegram; повторяем")
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
