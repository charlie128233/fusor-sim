"""Retrieval BM25 puro-Python sui testi curati.

Scelta deliberata: niente embedding né vector DB per ora — il corpus è
piccolo e curato, BM25 è trasparente e senza dipendenze. L'interfaccia
(search -> list[Passage]) resta identica quando si passerà a un vector
DB vero.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path

_WORD_RE = re.compile(r"[a-zàèéìòù0-9_]+")
_K1 = 1.5
_B = 0.75


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


@dataclass(frozen=True)
class Passage:
    source: str  # nome del file di provenienza
    text: str
    score: float


class KnowledgeBase:
    def __init__(self, knowledge_dir: str | Path):
        self.dir = Path(knowledge_dir)
        self._passages: list[tuple[str, str, list[str]]] = []  # (source, text, tokens)
        for path in sorted(self.dir.glob("*.md")):
            for chunk in self._chunks(path.read_text(encoding="utf-8")):
                self._passages.append((path.stem, chunk, _tokens(chunk)))
        if not self._passages:
            raise ValueError(f"Nessun documento in {self.dir}")

        self._avg_len = sum(len(t) for *_, t in self._passages) / len(self._passages)
        self._df: dict[str, int] = {}
        for *_, toks in self._passages:
            for term in set(toks):
                self._df[term] = self._df.get(term, 0) + 1

    @staticmethod
    def _chunks(text: str, max_chars: int = 700) -> list[str]:
        """Spezza per paragrafi, accorpando fino a ~max_chars."""
        chunks: list[str] = []
        current = ""
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para:
                continue
            if current and len(current) + len(para) > max_chars:
                chunks.append(current)
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current:
            chunks.append(current)
        return chunks

    def search(self, query: str, k: int = 3) -> list[Passage]:
        q_terms = _tokens(query)
        n_docs = len(self._passages)
        scored: list[Passage] = []
        for source, text, toks in self._passages:
            score = 0.0
            length = len(toks)
            for term in q_terms:
                tf = toks.count(term)
                if tf == 0:
                    continue
                df = self._df.get(term, 0)
                idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
                score += idf * tf * (_K1 + 1) / (
                    tf + _K1 * (1 - _B + _B * length / self._avg_len)
                )
            if score > 0:
                scored.append(Passage(source=source, text=text, score=score))
        scored.sort(key=lambda p: p.score, reverse=True)
        return scored[:k]
