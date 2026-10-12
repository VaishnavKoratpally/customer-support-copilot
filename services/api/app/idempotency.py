from hashlib import sha256
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.schemas import SupportReviewRequest


class IdempotencyUnavailableError(RuntimeError):
    pass


class IdempotencyStore(Protocol):
    def claim(self, *, key: str) -> bool:
        ...


class RedisIdempotencyStore:
    def __init__(self, *, client: Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    def claim(self, *, key: str) -> bool:
        try:
            created = self._client.set(name=key, value="1", nx=True, ex=self._ttl_seconds)
        except RedisError as exc:
            raise IdempotencyUnavailableError(f"Redis idempotency unavailable: {exc}") from exc
        return bool(created)


def review_idempotency_key(payload: SupportReviewRequest) -> str:
    raw = "|".join(
        [
            payload.trace_id,
            payload.reviewer_id,
            payload.status,
            payload.edited_draft or "",
            payload.rejection_reason_code or "",
        ]
    )
    return "support_review:" + sha256(raw.encode("utf-8")).hexdigest()