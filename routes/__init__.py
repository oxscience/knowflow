from flask import Flask
from .views import views_bp
from .tasks import tasks_bp
from .categories import categories_bp
from .api import api_bp
from .delegation import delegation_bp
from .notes import notes_bp
from .team import team_bp
from .extraction import extraction_bp


def register_blueprints(app: Flask):
    app.register_blueprint(views_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(delegation_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(team_bp)
    app.register_blueprint(extraction_bp)
