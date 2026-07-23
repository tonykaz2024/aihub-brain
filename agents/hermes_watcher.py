"""Specialist Hermes — detectează token invalid, restart loop."""
import re

ERROR_PATTERNS = {
    'InvalidToken': 'Token Telegram invalid — creează bot nou via @BotFather',
    'Unauthorized': 'Token Telegram expirat sau șters',
    'ConnectionError': 'Hermes nu poate ajunge la Telegram API',
    'Conflict': 'Alt bot cu același token rulează în paralel',
}

def classify_error(log_text: str) -> tuple:
    for pattern, explanation in ERROR_PATTERNS.items():
        if pattern in log_text:
            return pattern, explanation
    return 'UNKNOWN', log_text[-200:]
