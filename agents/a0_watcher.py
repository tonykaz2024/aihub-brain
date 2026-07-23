"""Specialist Agent Zero — crash, OOM, stall detection."""
import requests
import logging

logger = logging.getLogger('a0_watcher')

def check_a0_responsive(url: str = "http://192.168.10.50:50001/", timeout: int = 5) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False
