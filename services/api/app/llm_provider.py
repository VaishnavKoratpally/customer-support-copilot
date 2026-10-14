import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class LLMProvider(Protocol):
    def draft_response(
        self,
        *,
        question: str,
        intent: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        ...


class StubLLMProvider:
    """
    Placeholder provider for deterministic behavior during offline or fallback modes.
    """

    def draft_response(
        self,
        *,
        question: str,
        intent: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        _ = (question, system_prompt, user_prompt, model_name)
        if intent == "billing_dispute":
            return (
                "Thanks for flagging this. I can see this may be a billing dispute. "
                "I have prepared the case for billing review and will prioritize it. "
                "You can expect an update within 2 business days."
            )

        return (
            "Thanks for reaching out. I have prepared a support draft based on our current guidance. "
            "If you share any additional details, I can refine next steps."
        )


class OllamaProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaGenerationMetrics:
    total_duration_ns: int | None
    load_duration_ns: int | None
    prompt_eval_count: int | None
    prompt_eval_duration_ns: int | None
    eval_count: int | None
    eval_duration_ns: int | None
    done_reason: str | None


@dataclass(frozen=True)
class OllamaGenerationResult:
    text: str
    metrics: OllamaGenerationMetrics


class OllamaLLMProvider:
    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def draft_response(
        self,
        *,
        question: str,
        intent: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        _ = (question, intent)
        payload = {
            "model": model_name,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "think": False,
            "options": {
                "num_predict": 64
            },
        }
        return self._generate_text(payload)

    def generate_structured(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        return self.generate_structured_with_metrics(
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=response_schema,
        ).text

    def generate_structured_with_metrics(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> OllamaGenerationResult:
        payload: dict[str, object] = {
            "model": model_name,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "think": False,
            "format": response_schema,
            "options": {
                "temperature": 0,
                "num_predict": 1024,
            },
        }
        return self._generate_text_with_metrics(payload)

    def _generate_text(self, payload: dict[str, object]) -> str:
        return self._generate_text_with_metrics(payload).text

    def _generate_text_with_metrics(
        self,
        payload: dict[str, object],
    ) -> OllamaGenerationResult:
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = f"{exc.code} {exc.reason}"
            raw_error = exc.read().decode("utf-8", errors="replace").strip()
            if raw_error != "":
                try:
                    parsed = json.loads(raw_error)
                except json.JSONDecodeError:
                    detail = f"{detail} - {raw_error}"
                else:
                    provider_error = parsed.get("error") if isinstance(parsed, dict) else None
                    detail = f"{detail} - {provider_error}" if provider_error else f"{detail} - {raw_error}"
            raise OllamaProviderError(f"Ollama HTTP error: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OllamaProviderError(
                f"Ollama connection error: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise OllamaProviderError("Ollama request timed out.") from exc
        except UnicodeDecodeError as exc:
            raise OllamaProviderError(
                "Ollama returned a response that was not valid UTF-8."
            ) from exc

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise OllamaProviderError("Ollama returned a non-JSON response.") from exc

        if not isinstance(body, dict):
            raise OllamaProviderError(
                "Ollama returned a JSON response that was not an object."
            )

        raw_text = body.get("response")
        if not isinstance(raw_text, str):
            raise OllamaProviderError(
                "Ollama response did not include a textual response field."
            )

        text = raw_text.strip()
        if text == "":
            raw_thinking_text = body.get("thinking")
            thinking_text = (
                raw_thinking_text.strip()
                if isinstance(raw_thinking_text, str)
                else ""
            )
            if thinking_text != "":
                raise OllamaProviderError(
                    "Ollama returned empty response text while producing thinking output; "
                    "the model likely exhausted output budget before final answer."
                )
            raise OllamaProviderError("Ollama returned empty response text.")

        done_reason = body.get("done_reason")
        if done_reason is not None and not isinstance(done_reason, str):
            raise OllamaProviderError(
                "Ollama response field 'done_reason' must be a string."
            )
        metrics = OllamaGenerationMetrics(
            total_duration_ns=_optional_nonnegative_integer(body, "total_duration"),
            load_duration_ns=_optional_nonnegative_integer(body, "load_duration"),
            prompt_eval_count=_optional_nonnegative_integer(body, "prompt_eval_count"),
            prompt_eval_duration_ns=_optional_nonnegative_integer(
                body,
                "prompt_eval_duration",
            ),
            eval_count=_optional_nonnegative_integer(body, "eval_count"),
            eval_duration_ns=_optional_nonnegative_integer(body, "eval_duration"),
            done_reason=done_reason,
        )
        return OllamaGenerationResult(text=text, metrics=metrics)


def _optional_nonnegative_integer(
    body: dict[str, object],
    field_name: str,
) -> int | None:
    value = body.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OllamaProviderError(
            f"Ollama response field {field_name!r} must be a non-negative integer."
        )
    return value