from collections.abc import Sequence
from typing import Protocol

from pydantic import ValidationError

from app.evidence_assessment import (
    EvidenceAssessmentDecision,
    EvidenceAssessmentProposal,
    EvidenceAssessmentValidationError,
    validate_and_aggregate_assessment,
)
from app.llm_provider import OllamaProviderError
from app.prompts import (
    build_evidence_assessor_system_prompt,
    build_evidence_assessor_user_prompt,
)
from app.retrieval_repository import RetrievedChunk


class EvidenceAssessorError(RuntimeError):
    pass


class StructuredOutputGenerator(Protocol):
    def generate_structured(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        ...


class OllamaEvidenceAssessor:
    def __init__(
        self,
        *,
        generator: StructuredOutputGenerator,
        model_name: str,
    ) -> None:
        if model_name.strip() == "":
            raise ValueError("model_name must not be empty.")
        self._generator = generator
        self._model_name = model_name

    def assess(
        self,
        *,
        question: str,
        retrieved_chunks: Sequence[RetrievedChunk],
    ) -> EvidenceAssessmentDecision:
        if question.strip() == "":
            raise ValueError("question must not be blank.")

        try:
            raw_output = self._generator.generate_structured(
                model_name=self._model_name,
                system_prompt=build_evidence_assessor_system_prompt(),
                user_prompt=build_evidence_assessor_user_prompt(
                    question=question,
                    retrieved_chunks=retrieved_chunks,
                ),
                response_schema=EvidenceAssessmentProposal.model_json_schema(),
            )
        except OllamaProviderError as exc:
            raise EvidenceAssessorError(
                "Ollama evidence assessment generation failed."
            ) from exc

        try:
            proposal = EvidenceAssessmentProposal.model_validate_json(raw_output)
        except ValidationError as exc:
            validation_details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or '<proposal>'}: "
                f"{error['msg']}"
                for error in exc.errors(include_input=False)
            )
            raise EvidenceAssessorError(
                "Ollama returned an invalid evidence assessment proposal: "
                f"{validation_details}"
            ) from exc

        try:
            return validate_and_aggregate_assessment(
                proposal,
                retrieved_chunks=retrieved_chunks,
            )
        except EvidenceAssessmentValidationError as exc:
            raise EvidenceAssessorError(
                "Evidence assessment failed retrieved-chunk and quote validation."
            ) from exc
