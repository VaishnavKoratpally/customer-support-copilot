import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

VECTOR_DIMENSION = 1024


class EmbeddingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingModelInfo:
    model_name: str
    model_digest: str
    dimension: int


@dataclass(frozen=True)
class EmbeddingBatch:
    model_name: str
    model_digest: str
    dimension: int
    vectors: tuple[tuple[float, ...], ...]


class EmbeddingProvider(Protocol):
    def model_info(self) -> EmbeddingModelInfo:
        ...

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        ...


class OllamaEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 120.0,
        dimension: int = VECTOR_DIMENSION,
    ) -> None:
        if model_name.strip() == "":
            raise ValueError("model_name must not be empty")
        if dimension <= 0:
            raise ValueError("dimension must be greater than zero")

        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._dimension = dimension

    def model_info(self) -> EmbeddingModelInfo:
        request = urllib.request.Request(f"{self._base_url}/api/tags", method="GET")
        body = self._request_json(request)
        models = body.get("models")
        if not isinstance(models, list):
            raise EmbeddingProviderError("Ollama model list response has no models array.")

        model = next(
            (
                item
                for item in models
                if isinstance(item, dict)
                and self._model_name in (item.get("name"), item.get("model"))
            ),
            None,
        )
        if model is None:
            raise EmbeddingProviderError(
                f"Ollama embedding model '{self._model_name}' is not installed."
            )

        digest = model.get("digest")
        if not isinstance(digest, str) or digest.strip() == "":
            raise EmbeddingProviderError(
                f"Ollama did not return a digest for embedding model '{self._model_name}'."
            )

        return EmbeddingModelInfo(
            model_name=self._model_name,
            model_digest=digest,
            dimension=self._dimension,
        )

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            raise EmbeddingProviderError("At least one non-empty text is required for embedding.")
        if any(not isinstance(text, str) or text.strip() == "" for text in texts):
            raise EmbeddingProviderError("Embedding input texts must be non-empty strings.")

        model_info = self.model_info()
        request = urllib.request.Request(
            f"{self._base_url}/api/embed",
            data=json.dumps(
                {
                    "model": self._model_name,
                    "input": texts,
                    "dimensions": self._dimension,
                    "truncate": False,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        body = self._request_json(request)

        returned_model = body.get("model")
        if returned_model != self._model_name:
            raise EmbeddingProviderError(
                f"Ollama returned model '{returned_model}' instead of '{self._model_name}'."
            )

        raw_vectors = body.get("embeddings")
        if not isinstance(raw_vectors, list) or len(raw_vectors) != len(texts):
            received = len(raw_vectors) if isinstance(raw_vectors, list) else "no"
            raise EmbeddingProviderError(
                f"Ollama returned {received} vectors for {len(texts)} input texts."
            )

        vectors: list[tuple[float, ...]] = []
        for index, raw_vector in enumerate(raw_vectors, start=1):
            if not isinstance(raw_vector, list):
                raise EmbeddingProviderError(f"Ollama vector {index} is not an array.")
            if len(raw_vector) != self._dimension:
                raise EmbeddingProviderError(
                    f"Ollama vector {index} has {len(raw_vector)} dimensions; "
                    f"expected {self._dimension}."
                )

            vector: list[float] = []
            for value in raw_vector:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise EmbeddingProviderError(
                        f"Ollama vector {index} contains a non-numeric value."
                    )
                numeric_value = float(value)
                if not math.isfinite(numeric_value):
                    raise EmbeddingProviderError(
                        f"Ollama vector {index} contains a non-finite value."
                    )
                vector.append(numeric_value)
            vectors.append(tuple(vector))

        return EmbeddingBatch(
            model_name=model_info.model_name,
            model_digest=model_info.model_digest,
            dimension=model_info.dimension,
            vectors=tuple(vectors),
        )

    def _request_json(self, request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace").strip()
            detail = f"{exc.code} {exc.reason}"
            if raw_error != "":
                try:
                    parsed_error = json.loads(raw_error)
                except json.JSONDecodeError:
                    detail = f"{detail} - {raw_error}"
                else:
                    provider_error = (
                        parsed_error.get("error")
                        if isinstance(parsed_error, dict)
                        else None
                    )
                    detail = (
                        f"{detail} - {provider_error}"
                        if provider_error
                        else f"{detail} - {raw_error}"
                    )
            raise EmbeddingProviderError(f"Ollama HTTP error: {detail}") from exc
        except urllib.error.URLError as exc:
            raise EmbeddingProviderError(
                f"Ollama connection error: {exc.reason}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise EmbeddingProviderError(
                "Ollama returned a response that was not valid UTF-8."
            ) from exc

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise EmbeddingProviderError("Ollama returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise EmbeddingProviderError("Ollama returned a JSON response that was not an object.")
        return body
