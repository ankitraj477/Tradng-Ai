"""
Tradng-Ai REST API Blueprint Package
Registers institutional modular endpoints for Overview, Ops, Intraday, Swing, and F&O desks.
"""
from flask import Flask
from .overview import overview_bp
from .ops import ops_bp
from .intraday import intraday_bp
from .swing import swing_bp
from .fno import fno_bp


def register_blueprints(app: Flask) -> None:
    """Registers all modular desk and system blueprints with the Flask application."""
    app.register_blueprint(overview_bp)
    app.register_blueprint(ops_bp)
    app.register_blueprint(intraday_bp)
    app.register_blueprint(swing_bp)
    app.register_blueprint(fno_bp)

