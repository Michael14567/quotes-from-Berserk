#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exports character-attributed quotes from a publicly available Wikiquote page.

The source is a curated selection, not a complete transcript of the TV series.
Use the result only where you have the necessary rights to the quoted content.

Install: python -m pip install requests beautifulsoup4
Run:     python smeshariki_to_sql.py -o smeshariki_quotes.sql
Local:   python smeshariki_to_sql.py --html smeshariki.html -o smeshariki_quotes.sql
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

SOURCE = "https://ru.wikiquote.org/wiki/Смешарики"

ALIASES = {
    "крош": "Крош",
    "ёжик": "Ёжик", "ежик": "Ёжик",
    "нюша": "Нюша",
    "бараш": "Бараш",
    "кар-карыч": "Кар-Карыч", "карыч": "Кар-Карыч",
    "копатыч": "Копатыч",
    "лосяш": "Лосяш",
    "пин": "Пин",
    "совунья": "Совунья",
    "рассказчик": "Рассказчик",
}
CHARACTER_RE = re.compile(
    r"(?<![\w-])(?P<who>Кар-Карыч|Карыч|Рассказчик|Копатыч|Совунья|Лосяш|Бараш|Ёжик|Ежик|Крош|Нюша|Пин)\s*:\s*",
    re.IGNORECASE,
)
EPISODE_RE = re.compile(
    r"\s+[—–-]\s*(?:серия\b|«Новые приключения»\s*,?\s*серия\b|«Пин-код»\s*,?\s*серия\b)",
    re.IGNORECASE,
)
STAGE_START_RE = re.compile(r"^(?:\([^()]{0,250}\)\s*)+")


def clean(value: str) -> str:
    value = value.replace("\xa0", " ").replace("\x00", "")
    value = re.sub(r"\s+", " ", value).strip(" \t\n\r–—|-•")
    return value


def actor(who: str) -> str | None:
    return ALIASES.get(who.strip().lower())


def strip_episode(text: str) -> str:
    match = EPISODE_RE.search(text)
    return clean(text[:match.start()] if match else text)


def strip_stage(text: str) -> str:
    return clean(STAGE_START_RE.sub("", text))


def main_content(soup: BeautifulSoup) -> Tag:
    main = soup.select_one("#mw-content-text .mw-parser-output")
    if main is None:
        main = soup.select_one(".mw-parser-output") or soup.select_one("main")
    if main is None:
        raise ValueError("Не найден основной HTML-блок статьи. Проверьте, не изменилась ли вёрстка.")
    return main


def extract(html: str, include_dialogues: bool = True) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    root = main_content(soup)
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    section = ""
    current_character: str | None = None

    def add(text: str, character: str | None) -> None:
        if not character:
            return
        text = strip_stage(strip_episode(text))
        text = clean(text)
        if not text or len(text) < 3:
            return
        row = (text, character)
        if row not in seen:
            seen.add(row)
            rows.append(row)

    # Document order gives us the active section and currently selected character.
    for node in root.find_all(["h2", "h3", "li"]):
        if node.name == "h2":
            heading = clean(node.get_text(" ", strip=True)).lower()
            if "повторяющиеся фразы" in heading:
                section = "catchphrases"
            elif heading == "цитаты":
                section = "quotes"
            elif heading == "диалоги":
                section = "dialogues"
            else:
                section = "other"
            current_character = None
            continue

        if node.name == "h3":
            current_character = actor(clean(node.get_text(" ", strip=True))) if section == "quotes" else None
            continue

        # Ignore nested <li> to avoid collecting the same text twice.
        if node.find_parent("li") is not None:
            continue
        if section not in {"catchphrases", "quotes", "dialogues"}:
            continue

        content = strip_episode(clean(node.get_text(" ", strip=True)))
        if not content:
            continue

        if section == "catchphrases":
            match = CHARACTER_RE.match(content)
            if match:
                character = actor(match.group("who"))
                phrase_list = content[match.end():]
                # Most catchphrases are enclosed in Russian quotation marks.
                for quoted in re.findall(r"«([^»]+)»", phrase_list):
                    if not re.search(r"\([^)]*\)", quoted):
                        add(quoted, character)
        elif section == "quotes":
            add(content, current_character)
        elif section == "dialogues" and include_dialogues:
            # Preserve speaker changes even when the whole dialogue is one HTML list item.
            markers = list(CHARACTER_RE.finditer(content))
            for i, match in enumerate(markers):
                end = markers[i + 1].start() if i + 1 < len(markers) else len(content)
                add(content[match.end():end], actor(match.group("who")))

    return rows


def to_sql(rows: list[tuple[str, str]], batch_size: int = 500) -> str:
    def q(s: str) -> str:
        # SQL standard: apostrophes inside string literals are doubled.
        return "'" + s.replace("'", "''") + "'"

    blocks = [
        "-- Цитаты из доступной подборки Викицитатника, НЕ полные субтитры сериала.\n"
        "-- Источник: https://ru.wikiquote.org/wiki/Смешарики\n"
        "-- Проверяйте права и условия использования перед публикацией."
    ]
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        values = ",\n".join(f"    ({q(quote)}, {q(character)})" for quote, character in batch)
        blocks.append("INSERT INTO smeshariki_quotes (text, character) VALUES\n" + values + ";")
    return "\n\n".join(blocks) + "\n"


def get_html() -> str:
    response = requests.get(
        SOURCE,
        timeout=30,
        headers={
            "User-Agent": "SmesharikiQuoteExporter/1.0 (personal, non-commercial research)",
            "Accept-Language": "ru-RU,ru;q=0.9",
        },
    )
    response.raise_for_status()
    return response.text


def main() -> int:
    parser = argparse.ArgumentParser(description="Переводит подборку цитат Смешариков в SQL INSERT.")
    parser.add_argument("-o", "--output", type=Path, default=Path("smeshariki_quotes.sql"))
    parser.add_argument("--html", type=Path, help="Путь к предварительно скачанной HTML-странице")
    parser.add_argument("--no-dialogues", action="store_true", help="Не добавлять реплики из блока диалогов")
    args = parser.parse_args()

    try:
        html = args.html.read_text(encoding="utf-8") if args.html else get_html()
        rows = extract(html, include_dialogues=not args.no_dialogues)
        if not rows:
            print("Цитаты не найдены. Вероятно, изменилась разметка страницы.", file=sys.stderr)
            return 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(to_sql(rows), encoding="utf-8")
    except (OSError, requests.RequestException, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    print(f"Готово: {args.output} — {len(rows)} уникальных цитат")
    for name, count in sorted(Counter(person for _, person in rows).items()):
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
