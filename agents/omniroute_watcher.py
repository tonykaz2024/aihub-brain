"""Specialist OmniRoute — detectează provider mort, 429, stream-timeout."""
import requests
import logging

logger = logging.getLogger('omniroute_watcher')

def check_providers(base_url: str = "http://192.168.10.50:20128") -> dict:
    """Returnează starea providerilor din OmniRoute."""
    try:
        r = requests.get(f"{base_url}/providers", timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error("OmniRoute provider check failed: %s", e)
    return {}
