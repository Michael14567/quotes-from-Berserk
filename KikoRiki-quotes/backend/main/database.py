"""Подключение к PostgreSQL с паролем из файла секрета."""
import os
from pathlib import Path

import psycopg


def connect(**kwargs):
    password_file = os.environ.get("DB_PASSWORD_FILE", "/run/secrets/db_password")
    password = Path(password_file).read_text(encoding="utf-8").rstrip("\r\n")
    if not password:
        raise ValueError("Пароль базы данных пуст")
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "quotes"),
        user=os.environ.get("DB_USER", "quotes"),
        password=password,
        **kwargs,
    )
