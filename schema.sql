-- ============================================================
--  KYRO AI — Schéma de base de données (PostgreSQL)
--  Généré depuis backend/models.py (référence ; `create_all`
--  crée automatiquement ces tables au premier démarrage).
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id            VARCHAR(32) PRIMARY KEY,
    email         VARCHAR(255) NOT NULL UNIQUE,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,          -- PBKDF2-SHA256, jamais en clair
    role          VARCHAR(16)  NOT NULL DEFAULT 'USER',   -- USER | ADMIN
    is_suspended  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);

CREATE TABLE IF NOT EXISTS user_credits (
    user_id      VARCHAR(32) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    balance      INTEGER     NOT NULL DEFAULT 0,
    period_start TIMESTAMPTZ NOT NULL DEFAULT now(),  -- base du renouvellement horaire
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credit_ledger (
    id            VARCHAR(32) PRIMARY KEY,
    user_id       VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    actor_id      VARCHAR(32) REFERENCES users(id) ON DELETE SET NULL,
    delta         INTEGER     NOT NULL,
    balance_after INTEGER     NOT NULL,
    kind          VARCHAR(24) NOT NULL,  -- CONSUME|REFUND|RENEWAL|ADMIN_ADD|ADMIN_REMOVE|ADMIN_SET|ADMIN_RESET|ADMIN_GRANT_ALL
    reason        VARCHAR(255) NOT NULL DEFAULT '',
    request_id    VARCHAR(64) UNIQUE,    -- idempotence : une seule déduction par demande
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_credit_ledger_user ON credit_ledger (user_id);
CREATE INDEX IF NOT EXISTS ix_credit_ledger_created ON credit_ledger (created_at);

CREATE TABLE IF NOT EXISTS conversations (
    id         VARCHAR(32) PRIMARY KEY,
    user_id    VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      VARCHAR(120) NOT NULL DEFAULT 'Nouvelle conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              VARCHAR(32) PRIMARY KEY,
    conversation_id VARCHAR(32) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL,      -- user | assistant
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS generations (
    id            VARCHAR(32) PRIMARY KEY,
    user_id       VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind          VARCHAR(16) NOT NULL,        -- IMAGE | VIDEO | CHAT | CODE
    status        VARCHAR(16) NOT NULL DEFAULT 'PENDING',  -- PENDING|RUNNING|SUCCESS|FAILED
    prompt        TEXT NOT NULL DEFAULT '',
    text          TEXT,                        -- réponse chat / code généré
    media_url     VARCHAR(512),                -- image / vidéo générée
    provider      VARCHAR(64),
    credits_cost  INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_generations_user ON generations (user_id);
CREATE INDEX IF NOT EXISTS ix_generations_kind ON generations (kind);
CREATE INDEX IF NOT EXISTS ix_generations_status ON generations (status);

CREATE TABLE IF NOT EXISTS settings (
    key        VARCHAR(64) PRIMARY KEY,
    value      TEXT NOT NULL,                   -- JSON encodé
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id         VARCHAR(32) PRIMARY KEY,
    email      VARCHAR(255) NOT NULL,
    ip         VARCHAR(64)  NOT NULL DEFAULT '',
    success    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_login_attempts_email ON login_attempts (email);

CREATE TABLE IF NOT EXISTS admin_logs (
    id             VARCHAR(32) PRIMARY KEY,
    actor_id       VARCHAR(32) REFERENCES users(id) ON DELETE SET NULL,
    action         VARCHAR(64) NOT NULL,
    target_user_id VARCHAR(32),
    details        JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id         VARCHAR(32) PRIMARY KEY,
    level      VARCHAR(16) NOT NULL DEFAULT 'INFO',
    message    TEXT NOT NULL,
    context    JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
