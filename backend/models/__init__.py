"""Models package initialization"""

# Import all models to register them with SQLAlchemy Base
from backend.models.api_key import APIKey  # noqa: F401
from backend.models.user_api_key import UserAPIKey  # noqa: F401
