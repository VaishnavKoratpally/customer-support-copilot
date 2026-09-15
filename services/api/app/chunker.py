from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkDraft:
    section_path: str
    text: str
    token_estimate: int


class SimpleSectionChunker:
    def chunk(self, *, content: str, target_chunk_tokens: int, overlap_tokens: int) -> list[ChunkDraft]:
        target_words = max(int(target_chunk_tokens / 1.3), 1)
        overlap_words = max(int(overlap_tokens / 1.3), 0)

        sections = self._split_sections(content)
        chunks: list[ChunkDraft] = []

        for section_path, section_text in sections:
            words = section_text.split()
            if not words:
                continue

            start = 0
            while start < len(words):
                end = min(start + target_words, len(words))
                chunk_words = words[start:end]
                chunk_text = " ".join(chunk_words)
                token_estimate = max(int(len(chunk_words) * 1.3), 1)

                chunks.append(
                    ChunkDraft(
                        section_path=section_path,
                        text=chunk_text,
                        token_estimate=token_estimate,
                    )
                )

                if end >= len(words):
                    break

                next_start = end - overlap_words
                if next_start <= start:
                    next_start = end
                start = next_start

        return chunks

    def _split_sections(self, content: str) -> list[tuple[str, str]]:
        lines = content.splitlines()
        sections: list[tuple[str, str]] = []

        current_section = "root"
        buffer: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                if buffer:
                    sections.append((current_section, "\n".join(buffer).strip()))
                    buffer = []
                current_section = stripped.lstrip("#").strip() or "untitled-section"
            else:
                buffer.append(line)

        if buffer:
            sections.append((current_section, "\n".join(buffer).strip()))

        if not sections:
            sections.append(("root", content.strip()))

        return sections