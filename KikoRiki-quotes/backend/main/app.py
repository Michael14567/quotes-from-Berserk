import logging
import os
import json
import base64
import hashlib
import io
import secrets
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

import psycopg
from confluent_kafka import KafkaException, Producer
from fastapi import FastAPI, HTTPException, Request, Response
from psycopg.rows import dict_row
import qrcode
import qrcode.image.svg
import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("quotes")
app = FastAPI(title="Цитатник Смешариков")
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = "quote-clicks"
BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "KikoRiki_quotes_bot").lstrip("@")
COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
producer = Producer({
    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
    "enable.idempotence": True,
    "acks": "all",
    "transactional.id": "smeshariki-quote-producer",
    "transaction.timeout.ms": 15000,
})
producer_lock = Lock()
producer_initialized = False


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    try:
        with database.connect(connect_timeout=3, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
    except (psycopg.Error, OSError, ValueError):
        logger.exception("Ошибка обращения к базе данных")
        raise HTTPException(status_code=503, detail="База данных недоступна")


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def session_key(request: Request) -> str | None:
    token = request.cookies.get("quotes_session", "")
    if len(token) != 43 or not all(c.isascii() and (c.isalnum() or c in "_-") for c in token):
        return None
    return token_hash(token)


@app.post("/telegram/link")
def create_telegram_link(request: Request, response: Response):
    session = request.cookies.get("quotes_session") if session_key(request) else secrets.token_urlsafe(32)
    code = secrets.token_urlsafe(24)
    fetch_all(
        """INSERT INTO telegram_sessions (session_hash, link_hash, link_expires_at)
           VALUES (%s, %s, now() + interval '5 minutes')
           ON CONFLICT (session_hash) DO UPDATE
           SET link_hash = EXCLUDED.link_hash, link_expires_at = EXCLUDED.link_expires_at
           RETURNING session_hash""",
        (token_hash(session), token_hash(code)),
    )
    response.set_cookie("quotes_session", session, httponly=True, samesite="lax", secure=COOKIE_SECURE or request.url.scheme == "https", max_age=60 * 60 * 24 * 365)
    response.headers["Cache-Control"] = "no-store"
    url = f"https://t.me/{BOT_USERNAME}?start={code}"
    qr = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    qr.save(buffer)
    return {"url": url, "qr": "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"), "expires_in": 300}


@app.get("/telegram/status")
def telegram_status(request: Request, response: Response):
    session = session_key(request)
    if not session:
        return {"linked": False}
    rows = fetch_all("SELECT chat_id IS NOT NULL AS linked FROM telegram_sessions WHERE session_hash = %s", (session,))
    linked = rows[0]["linked"] if rows else False
    if linked and (COOKIE_SECURE or request.url.scheme == "https"):
        response.set_cookie("quotes_session", request.cookies["quotes_session"], httponly=True, samesite="lax", secure=True, max_age=60 * 60 * 24 * 365)
    return {"linked": linked}


@app.delete("/telegram/link")
def delete_telegram_link(request: Request, response: Response):
    session = session_key(request)
    if session:
        fetch_all("DELETE FROM telegram_sessions WHERE session_hash = %s RETURNING session_hash", (session,))
    response.delete_cookie("quotes_session")
    return {"linked": False}


@app.get("/smeshariki-quotes")
def list_smeshariki_quotes(character: str | None = None):
    if character is not None:
        return fetch_all(
            "SELECT id, text, character FROM smeshariki_quotes WHERE lower(character) = lower(%s) ORDER BY id",
            (character,),
        )
    return fetch_all("SELECT id, text, character FROM smeshariki_quotes ORDER BY id")


@app.post("/quote-click", status_code=202)
def quote_click(request: Request):
    global producer_initialized
    event = {"event_id": str(uuid4()), "type": "quote_button_clicked", "occurred_at": datetime.now(timezone.utc).isoformat()}
    session = session_key(request)
    if session:
        event["session_hash"] = session
    try:
        with producer_lock:
            if not producer_initialized:
                producer.init_transactions(15)
                producer_initialized = True
            producer.begin_transaction()
            try:
                producer.produce(KAFKA_TOPIC, value=json.dumps(event).encode("utf-8"))
                producer.commit_transaction(15)
            except (KafkaException, BufferError):
                try:
                    producer.abort_transaction(15)
                except KafkaException:
                    logger.error("Не удалось отменить транзакцию Kafka")
                raise
    except (KafkaException, BufferError):
        logger.exception("Не удалось отправить событие в Kafka")
        raise HTTPException(status_code=503, detail="Сервис событий недоступен")
    logger.info("Событие %s отправлено в Kafka", event["event_id"])
    return {"status": "accepted", "event_id": event["event_id"]}
