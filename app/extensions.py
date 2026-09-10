from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_caching import Cache
from flask_migrate import Migrate

db = SQLAlchemy()
jwt = JWTManager()
cache = Cache()
migrate = Migrate()
