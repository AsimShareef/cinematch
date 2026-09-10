import os
from flask import Flask
from config import config, BASE_DIR

from app.extensions import db, jwt, cache, migrate

def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'default')

    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'),
    )
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'})

    # Import blueprints locally to avoid circular imports
    from app.blueprints.auth import auth_bp
    from app.blueprints.movies import movies_bp
    from app.blueprints.recommendations import recommendations_bp
    from app.blueprints.reviews import reviews_bp
    from app.blueprints.profile import profile_bp
    from app.blueprints.pages import pages_bp

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(movies_bp, url_prefix='/movies')
    app.register_blueprint(recommendations_bp, url_prefix='/recommendations')
    app.register_blueprint(reviews_bp, url_prefix='/reviews')
    app.register_blueprint(profile_bp, url_prefix='/profile')
    app.register_blueprint(pages_bp)

    # A simple health check route
    @app.route('/health')
    def health_check():
        return {'status': 'ok', 'environment': config_name}, 200

    return app