import redis
import logging
from app.core.config import settings

logger = logging.getLogger("zbanque.redis")

class RedisService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisService, cls).__new__(cls)
            try:
                # Default to localhost if REDIS_URL not in settings yet
                redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
                cls._instance.client = redis.from_url(redis_url, decode_responses=True)
                cls._instance.client.ping()
                logger.info("Connected to Redis at %s", redis_url)
            except Exception as e:
                logger.error("Failed to connect to Redis: %s", e)
                cls._instance.client = None
        return cls._instance

    def get_client(self):
        return self.client

redis_service = RedisService()
