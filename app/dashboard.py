"""
Tradng-Ai PRO Dashboard
Institutional Flask web application factory using decoupled Jinja2 templates and modular API blueprints.
"""
import os
from pathlib import Path
from flask import Flask

from .api.overview import _enrich_trade
from .api import register_blueprints
from .learning import LearningEngine
from .news_archive import NewsArchive
from .execution import PaperExecution
from .ops.kill_switch import CentralKillSwitch

# Retain for backward compatibility with any legacy imports
HTML = "<!-- Tradng-Ai PRO v7.1: Modular Jinja2 frontend active in web/templates/base.html -->"


def create_app(db, cfg=None, provider=None, learning=None, news_archive=None):
    """
    Creates and configures the Flask application instance.
    Uses decoupled Jinja2 templates (web/templates) and static assets (web/static).
    """
    cfg = cfg or {}
    root_dir = Path(__file__).resolve().parent.parent
    template_dir = str(root_dir / "web" / "templates")
    static_dir = str(root_dir / "web" / "static")

    flask_app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
        static_url_path="/static"
    )

    # Core engine & risk singletons
    exec_engine = PaperExecution(db, cfg)
    kill_switch = CentralKillSwitch(db, exec_engine, provider, cfg)
    learning_engine = learning or LearningEngine(db, cfg)
    news_arc = news_archive or NewsArchive()

    # Application configuration container
    flask_app.config["DB"] = db
    flask_app.config["CFG"] = cfg
    flask_app.config["PROVIDER"] = provider
    flask_app.config["LEARNING"] = learning_engine
    flask_app.config["NEWS_ARCHIVE"] = news_arc
    flask_app.config["EXEC_ENGINE"] = exec_engine
    flask_app.config["KILL_SWITCH"] = kill_switch

    @flask_app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net data: blob:;"
        )
        return response

    @flask_app.context_processor
    def inject_version():
        from .version import __version__
        return dict(version=__version__, app_version=__version__)

    # Register all modular blueprints
    register_blueprints(flask_app)

    return flask_app


def _load_runtime():
    import json
    from .db import DB

    root = Path(__file__).resolve().parent.parent
    config_path = root / "config" / "default.json"
    with open(config_path, "r", encoding="utf-8") as file:
        cfg = json.load(file)

    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = DB(str(data_dir / "trader.db"))
    db.ensure_account(cfg["capital"]["starting"], cfg["capital"]["target"])
    return create_app(db=db, cfg=cfg)


def get_app():
    """BUG-032: Factory for lazy application loading without import-time side effects."""
    return _load_runtime()


def __getattr__(name):
    """BUG-032: Lazy attribute access so importing create_app does not open the database."""
    if name == "app":
        return _load_runtime()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    app = _load_runtime()
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
