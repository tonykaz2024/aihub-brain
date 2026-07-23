-- Memoria incidentelor — baza de date a experienței
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_msg TEXT,
    timestamp_start TEXT NOT NULL,
    timestamp_resolved TEXT,
    last_ok_state TEXT,        -- starea containerului când funcționa ultima dată
    delta_events TEXT,         -- ce s-a schimbat între last_ok și incident
    fix_applied TEXT,          -- ce fix am aplicat
    fix_result TEXT,           -- success/failure
    escalated_to_human INTEGER DEFAULT 0,
    notes TEXT
);

-- Starea ultimului OK per serviciu
CREATE TABLE IF NOT EXISTS service_state (
    service TEXT PRIMARY KEY,
    last_ok_timestamp TEXT,
    last_ok_image TEXT,        -- imaginea Docker când mergea
    last_ok_restart_count INTEGER,
    last_ok_log_tail TEXT,     -- ultimele 20 linii de log când mergea
    last_ok_env_hash TEXT      -- hash env vars (fără secrete)
);

-- Log-uri de fix-uri cunoscute (experiența acumulată)
CREATE TABLE IF NOT EXISTS known_fixes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    error_pattern TEXT NOT NULL,  -- regex sau substring
    fix_command TEXT NOT NULL,    -- ce comandă rulăm
    success_rate REAL DEFAULT 0,  -- câte fix-uri au mers
    last_used TEXT,
    notes TEXT
);

-- Seed cu fix-uri cunoscute din experiența noastră
INSERT OR IGNORE INTO known_fixes (service, error_pattern, fix_command, notes) VALUES
('hermes-gateway', 'InvalidToken', 'CHECK_TOKEN', 'Token Telegram invalid — trebuie token nou de la BotFather'),
('hermes-gateway', 'Restarting', 'docker restart hermes-gateway', 'Restart simplu dacă nu e token'),
('omniroute', '429', 'CHECK_PROVIDERS', 'Provider epuizat — verifică quota în OmniRoute dashboard'),
('omniroute', 'connection refused', 'docker restart omniroute', 'OmniRoute picat — restart'),
('agent-zero', 'OOM', 'NOTIFY_ONLY', 'OOM pe A0 — nu restartăm autonom, notificăm Tony'),
('whisper', 'CUDA out of memory', 'docker restart whisper', 'GPU overflow — restart eliberează VRAM'),
('openwebui', 'unhealthy', 'docker restart openwebui', 'OpenWebUI unhealthy — restart');
