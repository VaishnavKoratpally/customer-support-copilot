from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class EmbeddingPreview:
    embedding_dimension: int
    checksum_sha256: str


class StubEmbeddingProvider:
    def __init__(self, embedding_dimension: int = 1024) -> None:
        self._embedding_dimension = embedding_dimension

    def preview(self, text: str) -> EmbeddingPreview:
        checksum = sha256(text.encode("utf-8")).hexdigest()
        return EmbeddingPreview(
            embedding_dimension=self._embedding_dimension,
            checksum_sha256=checksum,
        )