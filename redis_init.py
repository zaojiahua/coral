from redis import StrictRedis, ConnectionPool

from app.config.setting import REDIS_URL

redis_client = StrictRedis(connection_pool=ConnectionPool.from_url(REDIS_URL, decode_responses=True))
