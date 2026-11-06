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

-- Один список для всех браузеров, привязанных к одному Telegram-чату.
CREATE TABLE IF NOT EXISTS daily_tasks (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL CHECK (length(btrim(title)) > 0),
    task_date DATE NOT NULL DEFAULT ((now() AT TIME ZONE 'Europe/Moscow')::date),
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    telegram_update_id BIGINT UNIQUE
);
CREATE INDEX IF NOT EXISTS daily_tasks_owner_day ON daily_tasks (chat_id, task_date, id);
