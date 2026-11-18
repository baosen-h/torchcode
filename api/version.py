"""Identify the API code loaded by a running local backend."""
import hashlib
from pathlib import Path

API_VERSION = 3


def backend_revision():
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]
