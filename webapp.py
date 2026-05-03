"""Backward-compatible ASGI entrypoint.

The real FastAPI application now lives in web.app.
"""

from web.app import app

