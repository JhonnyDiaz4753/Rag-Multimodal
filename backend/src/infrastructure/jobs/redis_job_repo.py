"""Repositorio de jobs sobre Redis con serialización JSON y TTL."""

import json
from dataclasses import asdict
from datetime import datetime

from redis.asyncio import Redis

from src.domain.jod import Job, JobStatus


class RedisJobRepo:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(job_id: str) -> str:
        return f"job:{job_id}"

    async def save(self, job: Job) -> None:
        data = asdict(job)
        data["status"] = job.status.value
        data["created_at"] = job.created_at.isoformat()
        await self._redis.set(self._key(job.id), json.dumps(data), ex=self._ttl)

    async def get(self, job_id: str) -> Job | None:
        raw = await self._redis.get(self._key(job_id))
        if raw is None:
            return None
        data = json.loads(raw)
        data["status"] = JobStatus(data["status"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return Job(**data)
