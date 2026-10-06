import json
import unittest
from unittest.mock import patch

from app.embedder import EmbeddingProviderError, OllamaEmbeddingProvider, VECTOR_DIMENSION


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload, allow_nan=True).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self._body


class OllamaEmbeddingProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = OllamaEmbeddingProvider(
            base_url="http://ollama:11434",
            model_name="qwen3-embedding:0.6b",
        )

    def test_embed_returns_model_digest_and_configured_vectors(self):
        vectors = [[0.125] * VECTOR_DIMENSION, [0.25] * VECTOR_DIMENSION]
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                FakeResponse(
                    {
                        "models": [
                            {
                                "name": "qwen3-embedding:0.6b",
                                "digest": "sha256:test-digest",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "model": "qwen3-embedding:0.6b",
                        "embeddings": vectors,
                    }
                ),
            ],
        ) as urlopen:
            batch = self.provider.embed(["first chunk", "second chunk"])

        self.assertEqual(batch.model_digest, "sha256:test-digest")
        self.assertEqual(batch.dimension, VECTOR_DIMENSION)
        self.assertEqual(len(batch.vectors), 2)
        self.assertEqual(len(batch.vectors[0]), VECTOR_DIMENSION)
        request = urlopen.call_args_list[1].args[0]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request_payload["input"], ["first chunk", "second chunk"])
        self.assertEqual(request_payload["dimensions"], VECTOR_DIMENSION)
        self.assertFalse(request_payload["truncate"])

    def test_embed_rejects_dimension_mismatch(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                FakeResponse(
                    {
                        "models": [
                            {
                                "name": "qwen3-embedding:0.6b",
                                "digest": "sha256:test-digest",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "model": "qwen3-embedding:0.6b",
                        "embeddings": [[0.1, 0.2, 0.3]],
                    }
                ),
            ],
        ):
            with self.assertRaisesRegex(EmbeddingProviderError, "3 dimensions"):
                self.provider.embed(["short vector"])

    def test_embed_rejects_non_finite_values(self):
        vector = [0.0] * VECTOR_DIMENSION
        vector[7] = float("nan")
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                FakeResponse(
                    {
                        "models": [
                            {
                                "name": "qwen3-embedding:0.6b",
                                "digest": "sha256:test-digest",
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "model": "qwen3-embedding:0.6b",
                        "embeddings": [vector],
                    }
                ),
            ],
        ):
            with self.assertRaisesRegex(EmbeddingProviderError, "non-finite"):
                self.provider.embed(["non-finite vector"])


if __name__ == "__main__":
    unittest.main()
