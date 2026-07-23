"""
aihub-brain — Orchestrator Central
Primește semnale de la watcheri, încarcă memoria, decide fix sau escaladează.
"""
import asyncio
import logging
import sqlite3

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
import yaml
import requests
from agents.docker_client import get_docker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/logs/orchestrator.log')
    ]
)
logger = logging.getLogger('orchestrator')

CONFIG_PATH = Path('/app/config/config.yml')
DB_PATH = Path('/app/memory/incidents.db')

# ── helpers ────────────────────────────────────────────────────────────────

def load_config():
    with open(CONFIG_PATH) as f:
        raw = f.read()
    # expandare env vars simple
    for k, v in os.environ.items():
        raw = raw.replace(f'${{{k}}}', v)
    return yaml.safe_load(raw)

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    # init schema
    schema = Path('/app/memory/schema.sql').read_text()
    db.executescript(schema)
    db.commit()
    return db

def docker_logs(container: str, lines: int = 50) -> str:
    try:
        return get_docker().logs(container, tail=lines)
    except Exception as e:
        return f"docker logs error: {e}"

def docker_inspect(container: str) -> dict:
    try:
        return get_docker().inspect(container)
    except Exception:
        return {}

def docker_restart(container: str) -> bool:
    try:
        return get_docker().restart(container)
    except Exception:
        return False

def health_check(url: str, timeout: int = 5) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False

def get_restart_count(inspect: dict) -> int:
    try:
        return inspect['RestartCount']
    except Exception:
        return 0

def send_telegram(token: str, chat_id: str, text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        logger.error("Telegram notify failed: %s", e)

# ── memoria incidentelor ────────────────────────────────────────────────────

def load_last_ok(db, service: str) -> dict:
    row = db.execute(
        "SELECT * FROM service_state WHERE service=?", (service,)
    ).fetchone()
    return dict(row) if row else {}

def save_ok_state(db, service: str, inspect: dict, log_tail: str):
    image = inspect.get('Config', {}).get('Image', '')
    restart_count = get_restart_count(inspect)
    db.execute("""
        INSERT OR REPLACE INTO service_state
        (service, last_ok_timestamp, last_ok_image, last_ok_restart_count, last_ok_log_tail)
        VALUES (?, ?, ?, ?, ?)
    """, (service, datetime.utcnow().isoformat(), image, restart_count, log_tail[-2000:]))
    db.commit()

def open_incident(db, service: str, error_type: str, error_msg: str,
                  last_ok: dict, delta: str) -> int:
    cur = db.execute("""
        INSERT INTO incidents
        (service, error_type, error_msg, timestamp_start, last_ok_state, delta_events)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (service, error_type, error_msg[:1000],
          datetime.utcnow().isoformat(),
          json.dumps(last_ok), delta))
    db.commit()
    return cur.lastrowid

def close_incident(db, incident_id: int, fix: str, result: str):
    db.execute("""
        UPDATE incidents SET
            timestamp_resolved=?, fix_applied=?, fix_result=?
        WHERE id=?
    """, (datetime.utcnow().isoformat(), fix, result, incident_id))
    db.commit()

def find_known_fix(db, service: str, error_msg: str) -> dict:
    rows = db.execute(
        "SELECT * FROM known_fixes WHERE service=? ORDER BY success_rate DESC",
        (service,)
    ).fetchall()
    for row in rows:
        if re.search(row['error_pattern'], error_msg, re.IGNORECASE):
            return dict(row)
    return {}

def compute_delta(last_ok: dict, current_inspect: dict) -> str:
    """Ce s-a schimbat față de ultima stare OK."""
    delta = []
    if not last_ok:
        return "Nu există stare anterioară OK."
    cur_image = current_inspect.get('Config', {}).get('Image', '')
    cur_restart = get_restart_count(current_inspect)
    if last_ok.get('last_ok_image') and last_ok['last_ok_image'] != cur_image:
        delta.append(f"Imaginea s-a schimbat: {last_ok['last_ok_image']} → {cur_image}")
    ok_restarts = last_ok.get('last_ok_restart_count', 0)
    if cur_restart > ok_restarts:
        delta.append(f"Restart-uri noi: {ok_restarts} → {cur_restart}")
    return "\n".join(delta) if delta else "Nicio schimbare detectată în imagine/restart."

# ── logica de incident ──────────────────────────────────────────────────────

async def handle_incident(cfg: dict, service_cfg: dict, error_type: str, error_msg: str):
    service = service_cfg['name']
    container = service_cfg['container']
    priority = service_cfg.get('priority', 'P1')
    restart_allowed = service_cfg.get('restart_allowed', False)

    db = get_db()
    tg_token = cfg['telegram']['bot_token']
    tg_chat = cfg['telegram']['admin_chat_id']

    logger.warning("[%s] INCIDENT %s: %s", service, error_type, error_msg[:200])

    # 1. Încarcă starea anterioară OK
    last_ok = load_last_ok(db, service)

    # 2. Inspectează containerul acum
    inspect = docker_inspect(container)
    logs = docker_logs(container, lines=30)

    # 3. Delta — ce s-a schimbat
    delta = compute_delta(last_ok, inspect)

    # 4. Deschide incident în DB
    incident_id = open_incident(db, service, error_type, error_msg, last_ok, delta)

    # 5. Caută fix cunoscut
    known = find_known_fix(db, service, error_msg)

    # 6. Decide acțiunea
    fix_applied = "NONE"
    fix_result = "pending"

    if known and known['fix_command'] == 'NOTIFY_ONLY':
        # Nu intervenim — doar notificăm
        fix_applied = "NOTIFY_ONLY"
        fix_result = "escalated"

    elif known and known['fix_command'].startswith('docker restart') and restart_allowed:
        logger.info("[%s] Applying known fix: %s", service, known['fix_command'])
        success = docker_restart(container)
        fix_applied = known['fix_command']
        fix_result = "success" if success else "failed"
        # Update success rate
        db.execute("""
            UPDATE known_fixes SET success_rate = (success_rate * 0.8 + ? * 0.2), last_used=?
            WHERE id=?
        """, (1.0 if success else 0.0, datetime.utcnow().isoformat(), known['id']))
        db.commit()

    elif known and known['fix_command'] in ('CHECK_TOKEN', 'CHECK_PROVIDERS'):
        fix_applied = known['fix_command']
        fix_result = "needs_human"

    elif restart_allowed and priority == 'P0':
        # Fix generic: restart
        logger.info("[%s] No known fix — trying generic restart", service)
        success = docker_restart(container)
        fix_applied = f"docker restart {container}"
        fix_result = "success" if success else "failed"

    else:
        fix_result = "escalated"

    close_incident(db, incident_id, fix_applied, fix_result)

    # 7. Notifică Telegram
    icon = "🔴" if priority == 'P0' else "🟡"
    msg = (
        f"{icon} *{service}* — `{error_type}`\n"
        f"```\n{error_msg[:300]}\n```\n"
        f"*Delta față de ultima stare OK:*\n{delta}\n\n"
        f"*Fix aplicat:* `{fix_applied}` → `{fix_result}`\n"
        f"*Log recent:*\n```\n{logs[-500:]}\n```"
    )
    if tg_token and tg_chat:
        send_telegram(tg_token, tg_chat, msg)

    logger.info("[%s] incident_id=%d fix=%s result=%s", service, incident_id, fix_applied, fix_result)

# ── monitoring loop ─────────────────────────────────────────────────────────

async def check_service(cfg: dict, svc: dict):
    container = svc['container']
    service = svc['name']

    try:
        inspect = docker_inspect(container)
        if not inspect:
            await handle_incident(cfg, svc, 'container_missing', f'Container {container} not found')
            return

        state = inspect.get('State', {})
        status = state.get('Status', '')
        restarting = state.get('Restarting', False)
        restart_count = get_restart_count(inspect)

        # Restart loop detection
        if restarting:
            logs = docker_logs(container, 20)
            await handle_incident(cfg, svc, 'restart_loop',
                                  f'Container in restart loop. Log:\n{logs[-500:]}')
            return

        # Health check via URL
        if svc.get('health_url') and status == 'running':
            ok = health_check(svc['health_url'])
            if not ok:
                logs = docker_logs(container, 20)
                await handle_incident(cfg, svc, 'health_check_failed',
                                      f'Health URL {svc["health_url"]} unreachable.\n{logs[-300:]}')
                return

        # Totul OK — salvăm starea
        if status == 'running' and not restarting:
            db = get_db()
            log_tail = docker_logs(container, 20)
            save_ok_state(db, service, inspect, log_tail)

    except Exception as e:
        logger.error("[%s] check failed: %s", service, e)

async def monitor_loop(cfg: dict):
    interval = cfg['thresholds']['check_interval_sec']
    services = cfg['services']
    logger.info("Monitor loop started — %d services, interval=%ds", len(services), interval)
    while True:
        tasks = [check_service(cfg, svc) for svc in services]
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(interval)

async def main():
    logger.info("aihub-brain orchestrator starting...")
    cfg = load_config()
    # Init DB
    get_db()
    await monitor_loop(cfg)

if __name__ == '__main__':
    asyncio.run(main())
