-- Идемпотентная миграция: данные цитат и существующие привязки сохраняются.
CREATE TABLE IF NOT EXISTS telegram_sessions (
    session_hash TEXT PRIMARY KEY,
    chat_id BIGINT,
    link_hash TEXT UNIQUE,
    link_expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS telegram_bot_state (
    name TEXT PRIMARY KEY,
    next_update_id BIGINT NOT NULL
);
