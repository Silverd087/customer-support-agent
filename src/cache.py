import redis
from config import settings

redis_cache = redis.from_url(settings.redis_url)