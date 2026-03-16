from datetime import date
from flask import Flask
import config
from database import init_db, close_db
from routes import register_blueprints
from models import get_categories


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_globals():
        return dict(
            categories=get_categories(),
            now_date=date.today().isoformat(),
        )

    register_blueprints(app)
    return app


if __name__ == '__main__':
    init_db()
    app = create_app()
    print(f'KnowFlow [{config.INSTANCE_NAME}] running at http://localhost:{config.PORT}')
    app.run(debug=config.DEBUG, port=config.PORT)
