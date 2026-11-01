"""Admin console for ContXpert (served at /console). Hook it up with:  admin_site.init_app(app)"""
import hashlib
import hmac
from datetime import timedelta

import config

from .routes import bp


def init_app(app):
    if not app.secret_key:
        # Session cookie signing key. Derived from ADMIN_KEY unless ADMIN_SESSION_SECRET is set.
        import os
        base = os.getenv("ADMIN_SESSION_SECRET") or config.ADMIN_KEY
        app.secret_key = hmac.new(base.encode(), b"contxpert-admin-session", hashlib.sha256).hexdigest()
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("SESSION_COOKIE_SECURE", config.BASE_URL.startswith("https://"))
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(hours=8))
    app.register_blueprint(bp)
