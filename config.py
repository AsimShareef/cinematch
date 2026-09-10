import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base configuration."""
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-dev-secret-key-replace-in-prod')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'default-jwt-secret-replace-in-prod')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL', 
        f"sqlite:///{os.path.join(BASE_DIR, 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # TMDb API
    TMDB_API_KEY = os.getenv('TMDB_API_KEY')
    
    # ML & Paths
    FAISS_INDEX_PATH = os.getenv(
        'FAISS_INDEX_PATH',
        os.path.join(BASE_DIR, 'ml', 'artifacts', 'faiss_index.bin')
    )
    SVD_MODEL_PATH = os.getenv(
        'SVD_MODEL_PATH',
        os.path.join(BASE_DIR, 'ml', 'artifacts', 'svd_model.joblib')
    )
    MOVIELENS_DATA_PATH = os.getenv(
        'MOVIELENS_DATA_PATH', 
        os.path.join(BASE_DIR, 'data', 'movielens')
    )
    MLFLOW_TRACKING_URI = os.getenv(
        'MLFLOW_TRACKING_URI', 
        f"sqlite:///{os.path.join(BASE_DIR, 'mlruns.db')}"
    )

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    # Can override specific settings for dev, e.g., local SQLite

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    # Ensure production uses actual environment variables, not defaults
    @classmethod
    def init_app(cls, app):
        assert os.getenv('SECRET_KEY'), "SECRET_KEY must be set in production"
        assert os.getenv('JWT_SECRET_KEY'), "JWT_SECRET_KEY must be set in production"

# Dictionary to help easily select the config
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}