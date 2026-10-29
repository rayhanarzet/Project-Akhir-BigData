"""Pemeriksaan terukur: keterjangkauan port NiFi dan isi HDFS melalui WebHDFS."""
import os
import socket
import threading
import time
from urllib.parse import quote, urlparse
import requests
from backend.config import HDFS_BASE_PATH
from data.storage import delivery_status

_cache = None
_checked = 0.0
_lock = threading.Lock()


def _probe_infrastructure():
    nifi_url = os.getenv("ARKADANTA_NIFI_URL", "https://127.0.0.1:8443")
    address = urlparse(nifi_url)
    try:
        with socket.create_connection((address.hostname, address.port or 8443), timeout=1):
            nifi = {"status": "PORT_REACHABLE", "detail": "Port merespons; status processor dan delivery perlu diperiksa di NiFi."}
    except (OSError, ValueError):
        nifi = {"status": "UNREACHABLE", "detail": "Port NiFi tidak dapat dijangkau dari backend."}
    endpoint = os.getenv("ARKADANTA_WEBHDFS_URL", "http://127.0.0.1:9870").rstrip("/")
    try:
        response = requests.get(f"{endpoint}/webhdfs/v1{quote(HDFS_BASE_PATH, safe='/')}",
                                params={"op": "GETCONTENTSUMMARY"}, timeout=2)
        response.raise_for_status()
        summary = response.json()["ContentSummary"]
        hdfs = {"status": "READABLE", "file_count": int(summary["fileCount"]), "bytes": int(summary["length"]),
                "detail": "Direktori dapat dibaca; belum membuktikan semua candle lokal telah tersalin."}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        hdfs = {"status": "UNAVAILABLE", "file_count": None, "bytes": None,
                "detail": "WebHDFS/path belum dapat dibaca. Periksa NameNode, izin, dan ARKADANTA_WEBHDFS_URL."}
    return {"nifi": nifi, "hdfs": hdfs}


def get_integration_status():
    global _cache, _checked
    with _lock:
        if _cache is None or time.monotonic() - _checked >= 10:
            _cache = _probe_infrastructure()
            _checked = time.monotonic()
        infrastructure = dict(_cache)
    from backend.market_stream import market_stream
    return {"backend": "UP", "stream": "CONNECTED" if market_stream.status["connected"] else "DISCONNECTED",
            **infrastructure, "outbox": delivery_status()}
