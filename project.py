"""Alias search transform server.

Run from this directory with:

    .venv/bin/python project.py

The seed URL is printed in the server log and is normally:

    https://127.0.0.1:3001/seed
"""

from __future__ import annotations

import os
from pathlib import Path

from maltego.server import MaltegoServerSettings, ServerHTTPSettings, run_server

# Importing the package executes the @register_transform decorators.
import transforms  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent


def _server_settings() -> MaltegoServerSettings:
    protocol = os.getenv("ALIAS_PROTOCOL", "https").strip().lower()
    cert_file = BASE_DIR / "certs" / "cert.pem"
    cert_key = BASE_DIR / "certs" / "key.pem"

    http_kwargs: dict[str, object] = {
        "protocol": protocol,
        "http_addr": os.getenv("ALIAS_HOST", "127.0.0.1"),
        "http_port": int(os.getenv("ALIAS_PORT", "3001")),
        "cors_allowed_origins": ["https://app.maltego.com"],
    }
    if protocol == "https":
        http_kwargs["cert_file"] = str(cert_file)
        http_kwargs["cert_key"] = str(cert_key)

    return MaltegoServerSettings(
        server_name="Alias Search Toolkit",
        ns="homosapiens.alias_search",
        author="homosapiens",
        version="1.0.0",
        transform_execution_timeout=int(
            os.getenv("ALIAS_TRANSFORM_TIMEOUT", "300")
        ),
        http_settings=ServerHTTPSettings(**http_kwargs),
    )


if __name__ == "__main__":
    run_server(settings=_server_settings())
