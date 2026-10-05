import json
import urllib.error
import urllib.request
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

        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
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
            raise RuntimeError(f"Ollama HTTP error: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama connection error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned non-JSON response.") from exc

        text = str(body.get("response", "")).strip()
        if text == "":
            thinking_text = str(body.get("thinking", "")).strip()
            if thinking_text != "":
                raise RuntimeError(
                    "Ollama returned empty response text while producing thinking output; "
                    "the model likely exhausted output budget before final answer."
                )
            raise RuntimeError("Ollama returned empty response text.")
        return text