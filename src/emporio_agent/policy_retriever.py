from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from rapidfuzz import fuzz

QUERY_EXPANSIONS = {
    "return": "devolucao arrependimento reembolso",
    "refund": "reembolso devolucao",
    "exchange": "troca trocar",
    "warranty": "garantia defeito",
    "defect": "defeito garantia",
    "shipping": "frete entrega envio",
    "delivery": "entrega prazo frete",
    "payment": "pagamento parcelamento pix boleto cartao",
    "installment": "parcelamento parcelas",
    "hours": "horario funcionamento",
    "address": "endereco",
    "phone": "telefone whatsapp",
    "contact": "contato telefone whatsapp email",
    "promotion": "promocao desconto",
    "discount": "desconto promocao",
    "privacy": "privacidade dados lgpd",
    "data": "dados privacidade lgpd",
    "complaint": "reclamacao atendimento",
    "accessories": "acessorios escopo",
    "cables": "cabos acessorios",
    "picks": "palhetas acessorios",
    "strings": "cordas acessorios",
    "cases": "cases acessorios",
    "pedals": "pedais acessorios",
    "amplifiers": "amplificadores acessorios",
    "scope": "escopo instrumentos musicais",
    "policy": "politica regras",
    "business": "funcionamento horario",
    "open": "horario funcionamento",
    "closed": "funcionamento horario",
}

INTENT_KEYWORDS = {
    "returns": ["return", "refund", "exchange", "devol", "arrepend", "troca", "trocas"],
    "warranty": ["warranty", "garantia", "defect", "defeito"],
    "hours": ["hours", "open", "closed", "funcionamento", "horario"],
    "payments": ["payment", "installment", "pix", "boleto", "credit", "debit", "parcela", "pagamento", "cartao"],
    "shipping": ["shipping", "delivery", "frete", "entrega", "prazo", "correios", "sedex", "jadlog"],
    "promotions": ["promotion", "discount", "promocao", "desconto", "black friday"],
    "privacy": ["privacy", "lgpd", "privacidade"],
    "scope": ["accessories", "scope", "acessorios", "cabos", "cables", "palhetas", "picks", "cordas", "pedais", "cases"],
    "contact": ["address", "phone", "whatsapp", "endereco", "telefone", "contato"],
}

INTENT_ANCHORS = {
    "returns": ["direito de arrependimento", "trocas e devolucoes", "7 (sete) dias", "reembolso", "embalagem original"],
    "warranty": ["garantia legal", "garantia do fabricante", "90 (noventa) dias", "defeitos de fabricacao"],
    "hours": ["horario de funcionamento", "segunda a sexta", "sabado", "domingo e feriados"],
    "payments": ["formas de pagamento", "parcelamento", "pix", "boleto bancario", "cartao de credito"],
    "shipping": ["politica de frete", "entregas", "correios", "sedex", "jadlog", "frete gratis"],
    "promotions": ["promocoes e descontos", "black friday", "aniversario da loja", "queima de estoque"],
    "privacy": ["privacidade e protecao de dados", "lgpd", "dados pessoais"],
    "scope": ["exclusivamente com instrumentos musicais", "nao comercializamos acessorios", "acessorios"],
    "contact": ["whatsapp", "telefone", "endereco", "rua 14 de maio"],
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _expand_query(query: str) -> str:
    normalized = _normalize(query)
    additions = [expanded for term, expanded in QUERY_EXPANSIONS.items() if term in normalized.split()]
    return " ".join([query, *additions])


def _detect_intents(query: str) -> list[str]:
    normalized = _normalize(query)
    return [intent for intent, keywords in INTENT_KEYWORDS.items() if any(keyword in normalized for keyword in keywords)]


@dataclass(frozen=True)
class PolicyChunk:
    text: str
    page: int


class PolicyRetriever:
    def __init__(self, pdf_path: str | Path, chunk_size: int = 800, overlap: int = 120):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"Policy PDF not found: {self.pdf_path}")
        self.chunks = self._load_chunks(chunk_size, overlap)
        if not self.chunks:
            raise ValueError("Could not extract text from the policy PDF.")

    def _load_chunks(self, chunk_size: int, overlap: int) -> list[PolicyChunk]:
        heading = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+[A-ZÀ-Ú][^\n]{2,80}$")
        skip = re.compile(r"^(Empório da Música Manual|Página \d+$)")
        sections: list[tuple[int, str]] = []
        current_page = 1
        current_text = ""
        with pymupdf.open(self.pdf_path) as document:
            for page_index, page in enumerate(document, start=1):
                for raw_line in page.get_text("text").splitlines():
                    line = raw_line.strip()
                    if not line or skip.match(line):
                        continue
                    if heading.match(line):
                        if current_text:
                            sections.append((current_page, current_text))
                        current_page = page_index
                        current_text = line
                    else:
                        current_text = f"{current_text} {line}".strip()
        if current_text:
            sections.append((current_page, current_text))

        chunks: list[PolicyChunk] = []
        for page_index, section in sections:
            text = re.sub(r"\s+", " ", section).strip()
            start = 0
            while start < len(text):
                end = min(len(text), start + chunk_size)
                if end < len(text):
                    boundary = text.rfind(". ", start + int(chunk_size * 0.55), end)
                    if boundary > start:
                        end = boundary + 1
                piece = text[start:end].strip()
                if piece:
                    chunks.append(PolicyChunk(piece, page_index))
                if end >= len(text):
                    break
                start = max(start + 1, end - overlap)
        if chunks:
            return chunks

        with pymupdf.open(self.pdf_path) as document:
            for page_index, page in enumerate(document, start=1):
                text = re.sub(r"\s+", " ", page.get_text("text")).strip()
                if text:
                    chunks.append(PolicyChunk(text[:chunk_size], page_index))
        return chunks

    def search(self, query: str, top_k: int = 3) -> dict:
        expanded = _normalize(_expand_query(query))
        query_terms = set(expanded.split())
        intents = _detect_intents(query)
        anchors = [_normalize(anchor) for intent in intents for anchor in INTENT_ANCHORS.get(intent, [])]
        ranked: list[tuple[float, PolicyChunk]] = []
        for chunk in self.chunks:
            candidate = _normalize(chunk.text)
            candidate_terms = set(candidate.split())
            overlap_score = len(query_terms & candidate_terms) / max(1, len(query_terms))
            fuzzy_score = fuzz.token_set_ratio(expanded, candidate) / 100
            anchor_score = sum(1 for anchor in anchors if anchor in candidate) / max(1, len(anchors))
            score = 0.55 * overlap_score + 0.20 * fuzzy_score + 0.25 * anchor_score
            if anchor_score > 0:
                score += 0.15
            score = min(1.0, score)
            if score > 0:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        results = [
            {"page": chunk.page, "score": round(score, 3), "text": chunk.text}
            for score, chunk in ranked[: max(1, min(top_k, 5))]
        ]
        return {"query": query, "results": results, "found": bool(results)}
