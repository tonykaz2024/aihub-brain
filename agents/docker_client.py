"""
Docker client via curl + Unix socket.
Simplu, reliable, fara dependinte externe.
"""
import json
import subprocess
import logging

logger = logging.getLogger('docker_client')
DOCKER_SOCKET = '/var/run/docker.sock'

def _curl(path: str, method: str = 'GET', data: dict = None) -> any:
    cmd = ['curl', '-s', '--unix-socket', DOCKER_SOCKET, f'http://localhost{path}']
    if method == 'POST':
        cmd += ['-X', 'POST']
        if data:
            cmd += ['-H', 'Content-Type: application/json', '-d', json.dumps(data)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.stdout.strip():
            return json.loads(r.stdout)
        return {}
    except Exception as e:
        logger.error("docker curl %s failed: %s", path, e)
        return {}

class DockerClient:
    def list_containers(self, all: bool = False) -> list:
        path = '/containers/json' + ('?all=1' if all else '')
        result = _curl(path)
        return result if isinstance(result, list) else []

    def inspect(self, container: str) -> dict:
        result = _curl(f'/containers/{container}/json')
        return result if isinstance(result, dict) else {}

    def logs(self, container: str, tail: int = 50) -> str:
        """Logs via curl — strip Docker multiplexing headers."""
        cmd = [
            'curl', '-s', '--unix-socket', DOCKER_SOCKET,
            f'http://localhost/containers/{container}/logs?stdout=1&stderr=1&tail={tail}'
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=10)
            raw = r.stdout
            # Strip Docker log multiplexing (8-byte frame header per line)
            text = ""
            i = 0
            while i + 8 <= len(raw):
                frame_size = int.from_bytes(raw[i+4:i+8], 'big')
                if frame_size == 0:
                    i += 8
                    continue
                text += raw[i+8:i+8+frame_size].decode('utf-8', errors='replace')
                i += 8 + frame_size
            return text[-3000:] if text else ""
        except Exception as e:
            return f"logs error: {e}"

    def restart(self, container: str) -> bool:
        try:
            cmd = ['curl', '-s', '-X', 'POST', '--unix-socket', DOCKER_SOCKET,
                   f'http://localhost/containers/{container}/restart?t=10',
                   '-w', '%{http_code}', '-o', '/dev/null']
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return r.stdout.strip() in ('204', '200')
        except Exception as e:
            logger.error("restart %s failed: %s", container, e)
            return False

_client = None

def get_docker() -> DockerClient:
    global _client
    if _client is None:
        _client = DockerClient()
    return _client
