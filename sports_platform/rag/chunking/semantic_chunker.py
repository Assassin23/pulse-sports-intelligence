"""
Semantic Chunking Module — Milestone 9.

Implements paragraph-aware chunking with target chunk size 400 tokens,
50-token context overlap, and header context preservation as specified in
docs/ai/09-ai-rag-architecture.md.
"""
from dataclasses import dataclass
from typing import List, Optional
import re
import logging

logger = logging.getLogger(__name__)

try:
    import tiktoken
except ImportError:
    tiktoken = None


@dataclass
class Chunk:
    text: str
    token_count: int


class TokenizerHelper:
    """
    Encapsulates token counting and encoding with tiktoken,
    falling back to a heuristic word-based tokenizer if tiktoken is unavailable.
    """

    def __init__(self, model: str = "text-embedding-3-small"):
        self._encoder = None
        if tiktoken is not None:
            try:
                self._encoder = tiktoken.encoding_for_model(model)
            except Exception:
                try:
                    self._encoder = tiktoken.get_encoding("cl100k_base")
                except Exception:
                    self._encoder = None

    def encode(self, text: str) -> List[int]:
        if self._encoder is not None:
            return self._encoder.encode(text)
        # Fallback: pseudo token IDs using words and punctuation
        words = re.findall(r"\w+|[^\w\s]", text)
        return list(range(len(words)))

    def decode(self, tokens: List[int], original_text: str = "") -> str:
        if self._encoder is not None:
            return self._encoder.decode(tokens)
        words = re.findall(r"\w+|[^\w\s]", original_text)
        return " ".join(words[: len(tokens)])

    def count_tokens(self, text: str) -> int:
        if self._encoder is not None:
            return len(self._encoder.encode(text))
        return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


class SemanticChunker:
    """
    Chunking strategy:
    - Target chunk size: 400 tokens
    - Overlap: 50 tokens (preserves context at chunk boundaries)
    - Split hierarchy: paragraphs first (\\n\\n), then sentences, then tokens
    - Context preservation: Prepends `[{document_type}] {title}\\n\\n` to every chunk
    """

    TARGET_TOKENS = 400
    OVERLAP_TOKENS = 50

    def __init__(self, model: str = "text-embedding-3-small", target_tokens: int = 400, overlap_tokens: int = 50):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self._tokenizer = TokenizerHelper(model=model)

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split a long paragraph into sentences."""
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _split_sentence_if_needed(self, sentence: str) -> List[str]:
        """Split single sentence into smaller segments if it exceeds target tokens."""
        tokens = self._tokenizer.count_tokens(sentence)
        if tokens <= self.target_tokens:
            return [sentence]
        
        words = sentence.split()
        segments = []
        cur_words = []
        for word in words:
            cur_words.append(word)
            if self._tokenizer.count_tokens(" ".join(cur_words)) >= self.target_tokens:
                segments.append(" ".join(cur_words))
                cur_words = []
        if cur_words:
            segments.append(" ".join(cur_words))
        return segments

    def chunk(self, document) -> List[Chunk]:
        """
        Splits a document (RawDocument or any object with title, content, document_type)
        into overlapping semantic chunks.
        """
        title = getattr(document, "title", "Untitled")
        doc_type = getattr(document, "document_type", "document")
        raw_content = getattr(document, "content", getattr(document, "raw_content", ""))

        if not raw_content or not raw_content.strip():
            return []

        header = f"[{doc_type}] {title}\n\n"
        header_tokens = self._tokenizer.count_tokens(header)
        effective_target = max(100, self.target_tokens - header_tokens)

        # 1. Break into paragraphs
        raw_paragraphs = [p.strip() for p in raw_content.split("\n\n") if p.strip()]
        
        # 2. Break oversize paragraphs into sentences/segments
        atoms: List[str] = []
        for para in raw_paragraphs:
            para_tokens = self._tokenizer.count_tokens(para)
            if para_tokens <= effective_target:
                atoms.append(para)
            else:
                sentences = self._split_into_sentences(para)
                for sentence in sentences:
                    sub_segments = self._split_sentence_if_needed(sentence)
                    atoms.extend(sub_segments)

        chunks: List[Chunk] = []
        current_atoms: List[str] = []
        current_token_count = 0

        for atom in atoms:
            atom_tokens = self._tokenizer.count_tokens(atom)
            if current_token_count + atom_tokens > effective_target and current_atoms:
                # Emit chunk
                body = "\n\n".join(current_atoms)
                full_text = f"{header}{body}"
                chunks.append(
                    Chunk(
                        text=full_text,
                        token_count=self._tokenizer.count_tokens(full_text),
                    )
                )

                # Prepare overlap from the trailing text of the current chunk
                trailing_words = body.split()
                overlap_words = trailing_words[-self.overlap_tokens :] if len(trailing_words) > self.overlap_tokens else trailing_words
                overlap_text = " ".join(overlap_words)
                
                current_atoms = [overlap_text, atom] if overlap_text else [atom]
                current_token_count = self._tokenizer.count_tokens("\n\n".join(current_atoms))
            else:
                current_atoms.append(atom)
                current_token_count += atom_tokens

        if current_atoms:
            body = "\n\n".join(current_atoms)
            full_text = f"{header}{body}"
            chunks.append(
                Chunk(
                    text=full_text,
                    token_count=self._tokenizer.count_tokens(full_text),
                )
            )

        return chunks
