"""Minimal client for OpenJev's /v1/systemone decision API.

Two ways to reach the model:
  * Direct to the helper (what the experiments in the post used): set
    OPENJEV_URL to the predictor Service (or a port-forward) and use the
    helper's own key, OPENJEV_TOKEN or the openjev-shim Secret mounted at
    /conn/shim (apiKey).
  * Through the Envoy AI Gateway: leave OPENJEV_URL unset. The Instance's
    connection Secret mounted at /conn/openjev carries the gateway base URL
    (uri, ending in /typesafe) and its API key (password). Set
    OPENJEV_INSECURE=1 for a self-signed gateway certificate.
"""
import os
import pathlib
import time

import httpx


def _file(path):
    p = pathlib.Path(path)
    return p.read_text().strip() if p.exists() else None


if os.environ.get("OPENJEV_URL"):
    URL = os.environ["OPENJEV_URL"]
    TOKEN = os.environ.get("OPENJEV_TOKEN") or _file("/conn/shim/apiKey")
else:
    URL = _file("/conn/openjev/uri") or "http://127.0.0.1:3000"
    TOKEN = os.environ.get("OPENJEV_TOKEN") or _file("/conn/openjev/password") or _file("/conn/shim/apiKey")
URL = URL.rstrip("/")

_client = httpx.Client(
    timeout=120,
    verify=os.environ.get("OPENJEV_INSECURE") != "1",
    headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {},
    limits=httpx.Limits(max_connections=64, max_keepalive_connections=64),
)


def decide(state, questions, model="openjev"):
    """POST one state and a map of questions. Returns (answers, elapsed_ms, usage)."""
    t0 = time.perf_counter()
    r = _client.post(f"{URL}/v1/systemone", json={"model": model, "state": state, "questions": questions})
    r.raise_for_status()
    body = r.json()
    return body["answers"], (time.perf_counter() - t0) * 1000, body.get("usage", {})


def version():
    """The helper's /v1/version (direct access only; the gateway routes /v1/systemone)."""
    return _client.get(f"{URL}/v1/version").json()
