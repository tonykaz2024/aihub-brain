"""
Webhook receiver pentru Plane → Multica.
Cand Plane creeaza bug nou → webhook lovește :4041 → creeaza issue in Multica + assign Freddy.
Rulează ca container separat langa aihub-brain.
"""
import json
import os
import logging
import psycopg2
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s [webhook] %(message)s')
logger = logging.getLogger('webhook')

WEBHOOK_PORT = 4041
FREDDY_AGENT_ID = "ab33caa7-52f3-4c2b-bda1-5d521327273e"
MULTICA_WS = "62fb6cd8-c8b9-4305-9692-cf7290d523bf"
MULTICA_USER = "f1d82b09-3912-4ff3-b22e-6116a4a9f926"

def create_multica_issue(title, description, priority):
    pri_map = {"urgent":"urgent","high":"high","medium":"medium","none":"none","low":"low","1":"high","2":"medium","3":"low","4":"urgent"}
    pri = pri_map.get(str(priority).lower(), "none")
    try:
        conn = psycopg2.connect(
            host=os.environ.get("MULTICA_DB_HOST", "192.168.224.2"),
            port=5432, dbname="multica", user="multica",
            password=os.environ.get("MULTICA_DB_PASS", "multica_habibula_2026")
        )
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO issue (workspace_id, title, description, status, priority, creator_type, creator_id, assignee_type, assignee_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (MULTICA_WS, title[:500], description[:5000], "backlog", pri, "member", MULTICA_USER, "agent", FREDDY_AGENT_ID)
        )
        issue_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        logger.info("Issue creat in Multica: %s, asignat Freddy, pri=%s", issue_id, pri)

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
        if token and chat:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": f"🐞 Bug nou → Freddy\n*{title}*\nPrioritate: {pri}", "parse_mode": "Markdown"},
                    timeout=10
                )
            except Exception:
                pass
        return issue_id
    except Exception as e:
        logger.error("Multica insert failed: %s", e)
        return None

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
            event = payload.get('event', '')
            data = payload.get('data', payload)
            logger.info("Event primit: %s", event)

            if 'issue' in event.lower() and 'create' in event.lower():
                title = data.get('name', data.get('title', 'Bug nou'))
                desc = data.get('description_html', data.get('description', ''))
                priority = data.get('priority', 'none')
                create_multica_issue(title, desc, priority)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        except Exception as e:
            logger.error("Eroare: %s", e)
            self.send_response(500)
            self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'aihub-brain webhook receiver — OK')

    def log_message(self, *args):
        pass

if __name__ == '__main__':
    server = HTTPServer(("0.0.0.0", WEBHOOK_PORT), Handler)
    logger.info("Webhook receiver pe :%d", WEBHOOK_PORT)
    server.serve_forever()
