import json
from datetime import timedelta

import redis
from jesse.config import config


class Redis:
    def __init__(self):
        self.expire_seconds = config['env']['databases'].get('redis_expiration_seconds', 60 * 5)
        self.db = redis.Redis(
            host=config['env']['databases'].get('redis_host', 'localhost'),
            port=config['env']['databases'].get('redis_port', 6379),
            db=0
        )

    def set_cache(self, key, value):
        self.db.setex(key, timedelta(seconds=self.expire_seconds), json.dumps(value))

    def get_cache(self, key):
        exists = self.db.exists(key)

        if exists:
            # renew cache expiration time
            self.db.expire(key, timedelta(seconds=self.expire_seconds))
            return json.loads(self.db.get(key))

        return None

    def flush_cache(self):
        self.db.flushdb()


cache = Redis()
