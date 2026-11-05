"""Создаёт локальный пароль PostgreSQL, не изменяя существующий файл."""
import os
import secrets
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description="Создать локальный секрет для PostgreSQL")
parser.add_argument("--remote", action="store_true", help="Создать отдельный пароль для сервера")
args = parser.parse_args()
directory = Path(__file__).resolve().parent / ".secrets"
target = directory / ("remote_postgres_password" if args.remote else "postgres_password")
directory.mkdir(mode=0o700, exist_ok=True)
try:
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
except FileExistsError:
    print("Файл пароля уже существует и не изменён.")
else:
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(secrets.token_urlsafe(32))
    print(f"Файл пароля создан: .secrets/{target.name}.")
