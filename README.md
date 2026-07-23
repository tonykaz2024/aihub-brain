# aihub-brain

Self-healing infrastructure monitor pentru aihub.
Un singur container care monitorizează toate serviciile, detectează incidente,
aplică fix-uri cunoscute autonom și escaladează pe Telegram când nu poate rezolva.

## Arhitectură

```
aihub-brain container
├── orchestrator.py     — loop central, 30s interval
├── agents/
│   ├── omniroute_watcher.py  — specialist OmniRoute (429, stream-out)
│   ├── hermes_watcher.py     — specialist Hermes/Telegram (token, restart)
│   ├── a0_watcher.py         — specialist Agent Zero (crash, OOM)
│   └── general_watcher.py    — toate containerele (health, restart loop)
└── memory/incidents.db — SQLite cu istoricul incidentelor + fix-uri cunoscute
```

## Setup rapid

```bash
cp .env.example .env
# editează .env cu tokenul Telegram
docker compose up -d
docker logs -f aihub-brain
```

## Deploy pe aihub

```bash
# Pe tc — build + push
docker build -t aihub-brain:latest .
docker save aihub-brain:latest | gzip > aihub-brain.tar.gz
scp aihub-brain.tar.gz ai@192.168.10.50:/srv/aihub-data/home/ai/aihub-stack/aihub-brain/
# Pe aihub
ssh ai@192.168.10.50 "cd /srv/aihub-data/home/ai/aihub-stack/aihub-brain && docker load < aihub-brain.tar.gz && docker compose up -d"
```

## Adăugare fix cunoscut

```sql
INSERT INTO known_fixes (service, error_pattern, fix_command, notes)
VALUES ('omniroute', 'worker crash', 'docker restart omniroute', 'Worker OmniRoute picat');
```

## Adăugare serviciu monitorizat

Editează `config/config.yml` — adaugă entry în `services:`. Nu trebuie rebuild.
