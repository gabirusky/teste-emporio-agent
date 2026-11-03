from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

CATEGORY_ALIASES = {
    1: ["guitarra", "guitarras", "electric guitar", "electric guitars"],
    2: ["baixo", "baixos", "contrabaixo", "bass", "basses"],
    3: ["bateria", "baterias", "drums", "drum kit"],
    4: ["teclado", "teclados", "piano", "pianos", "sintetizador", "synthesizer", "keyboard", "keyboards"],
    5: ["violao", "violoes", "acoustic guitar", "acoustic guitars", "classical guitar", "classical guitars"],
    6: ["sopro", "madeiras", "woodwind", "woodwinds", "flauta", "flute", "clarinete", "clarinet", "saxofone", "saxophone"],
    7: ["metais", "brass", "trompete", "trumpet", "trombone", "tuba", "trompa", "horn"],
    8: ["cordas orquestrais", "orchestral strings", "violino", "violin", "violoncelo", "cello"],
    9: ["ukulele", "ukuleles"],
}

STOP_WORDS = {
    "a", "an", "and", "are", "at", "available", "be", "below", "buy", "can", "cost",
    "could", "de", "da", "das", "do", "dos", "em", "for", "favor", "have", "has", "how",
    "i", "in", "is", "it", "less", "looking", "max", "maximum", "me", "menos", "my",
    "no", "of", "on", "option", "options", "or", "os", "as", "o", "um", "uma", "para",
    "please", "por", "preco", "precos", "price", "prices", "produto", "produtos", "quais",
    "qual", "quanto", "que", "reais", "store", "tem", "the", "to", "under", "up", "valor",
    "want", "which", "with", "you", "your", "custa", "custam", "disponivel", "disponiveis",
    "estoque", "instrumento", "instrumentos", "r", "rs", "ate", "mil",
    "one", "two", "three", "four", "five", "hundred", "thousand", "million",
    "dois", "tres", "quatro", "cinco", "cem",
}

NUMBER_WORDS = {
    "one thousand": 1000, "a thousand": 1000, "two thousand": 2000,
    "three thousand": 3000, "fifteen hundred": 1500, "ten thousand": 10000,
    "mil": 1000, "dois mil": 2000, "tres mil": 3000, "mil e quinhentos": 1500,
    "novecentos": 900, "oitocentos": 800, "setecentos": 700, "seiscentos": 600,
    "quinhentos": 500, "quatrocentos": 400, "trezentos": 300, "duzentos": 200, "cem": 100,
}


def normalize(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _parse_amount(raw: str) -> float | None:
    raw = raw.strip().replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        head, tail = raw.rsplit(",", 1)
        raw = head.replace(",", "") + ("." + tail if len(tail) <= 2 else tail)
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    elif "." in raw:
        head, tail = raw.rsplit(".", 1)
        if len(tail) == 3:
            raw = head + tail
    try:
        return float(raw)
    except ValueError:
        return None


def parse_price_limit(text: str) -> float | None:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = re.sub(r"\s+", " ", folded).strip()
    pattern = (
        r"(?:up to|under|below|less than|at most|max(?:imum)?(?: of)?|ate|menos de|"
        r"no maximo|maximo de|abaixo de)\s*(?:r\s*\$?\s*)?([\d][\d.,]*)"
    )
    match = re.search(pattern, folded)
    if match:
        return _parse_amount(match.group(1))
    for phrase, value in NUMBER_WORDS.items():
        if re.search(rf"(?:up to|under|below|less than|at most|ate|menos de|no maximo|abaixo de)\s+{re.escape(phrase)}\b", folded):
            return float(value)
    return None


def infer_category(text: str) -> int | None:
    normalized = normalize(text)
    if re.search(r"\b(guitarras?|guitars?)\b", normalized) and re.search(r"\b(acoustic|classical|nylon)\b", normalized):
        return 5
    for category_id, aliases in CATEGORY_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(normalize(alias))}\b", normalized):
                return category_id
    return None


class DataStore:
    def __init__(
        self,
        products_csv: str | Path,
        orders_csv: str | Path,
        categories_csv: str | Path | None = None,
        promotions_csv: str | Path | None = None,
        customers_csv: str | Path | None = None,
        order_items_csv: str | Path | None = None,
    ):
        self.products = self._load_csv(products_csv)
        self.orders = self._load_csv(orders_csv)
        self.categories = self._load_optional(categories_csv, {"category_id", "name"})
        self.promotions = self._load_optional(promotions_csv, {"promotion_id", "product_id", "discount_percent", "is_active"})
        self.customers = self._load_optional(customers_csv, {"customer_id", "name"})
        self.order_items = self._load_optional(order_items_csv, {"order_id", "quantity", "product_id"})
        self._validate_products()
        self._validate_orders()
        self.category_names = self._build_category_names()
        self.active_promotions = self._build_active_promotions()

    @staticmethod
    def _load_csv(path: str | Path) -> pd.DataFrame:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Data file not found: {file_path}")
        return pd.read_csv(file_path, encoding="utf-8-sig")

    @staticmethod
    def _load_optional(path: str | Path | None, required: set[str]) -> pd.DataFrame:
        if path is None or not Path(path).exists():
            return pd.DataFrame(columns=sorted(required))
        frame = pd.read_csv(path, encoding="utf-8-sig")
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Missing columns in {path}: {sorted(missing)}")
        return frame

    def _validate_products(self) -> None:
        required = {"product_id", "price_brl", "name", "category_id", "description", "stock_quantity", "status"}
        missing = required - set(self.products.columns)
        if missing:
            raise ValueError(f"Missing columns in products CSV: {sorted(missing)}")
        if self.products["product_id"].duplicated().any():
            raise ValueError("Duplicate product_id in products CSV")
        self.products["product_id"] = pd.to_numeric(self.products["product_id"], errors="coerce")
        self.products["price_brl"] = pd.to_numeric(self.products["price_brl"], errors="coerce").fillna(0.0)
        self.products["stock_quantity"] = pd.to_numeric(self.products["stock_quantity"], errors="coerce").fillna(0).astype(int)
        self.products["category_id"] = pd.to_numeric(self.products["category_id"], errors="coerce").fillna(0).astype(int)

    def _validate_orders(self) -> None:
        required = {"order_id", "customer_id", "order_date", "status", "total_brl", "payment_method"}
        missing = required - set(self.orders.columns)
        if missing:
            raise ValueError(f"Missing columns in orders CSV: {sorted(missing)}")
        if self.orders["order_id"].duplicated().any():
            raise ValueError("Duplicate order_id in orders CSV")
        self.orders["order_id"] = pd.to_numeric(self.orders["order_id"], errors="coerce")

    def _build_category_names(self) -> dict[int, str]:
        if self.categories.empty:
            return {category_id: aliases[0].title() for category_id, aliases in CATEGORY_ALIASES.items()}
        return {
            int(row.category_id): str(row.name)
            for row in self.categories.itertuples(index=False)
        }

    def _build_active_promotions(self) -> dict[int, dict[str, Any]]:
        if self.promotions.empty:
            return {}
        active = self.promotions.copy()
        active["is_active"] = active["is_active"].astype(str).str.lower().isin({"1", "true", "yes"})
        active["discount_percent"] = pd.to_numeric(active["discount_percent"], errors="coerce").fillna(0.0)
        active = active[active["is_active"] & active["discount_percent"].gt(0)]
        promotions: dict[int, dict[str, Any]] = {}
        for row in active.itertuples(index=False):
            product_id = int(row.product_id)
            current = promotions.get(product_id)
            if current is None or float(row.discount_percent) > current["discount_percent"]:
                promotions[product_id] = {
                    "promotion_id": int(row.promotion_id),
                    "discount_percent": float(row.discount_percent),
                    "description": str(row.description),
                }
        return promotions

    @staticmethod
    def _effective_price(price: float, promotion: dict[str, Any] | None) -> float:
        if not promotion:
            return round(float(price), 2)
        return round(float(price) * (1 - promotion["discount_percent"] / 100), 2)

    def _product_dict(self, row: pd.Series) -> dict[str, Any]:
        specs: Any = row.get("specs", {})
        if isinstance(specs, str):
            try:
                specs = json.loads(specs)
            except json.JSONDecodeError:
                specs = {}
        product_id = int(row["product_id"])
        promotion = self.active_promotions.get(product_id)
        price = float(row["price_brl"])
        return {
            "product_id": product_id,
            "name": str(row["name"]),
            "category": self.category_names.get(int(row["category_id"]), "Unmapped category"),
            "description": str(row.get("description", "")),
            "price_brl": price,
            "effective_price_brl": self._effective_price(price, promotion),
            "promotion": promotion,
            "stock_quantity": int(row["stock_quantity"]),
            "status": str(row["status"]),
            "available": str(row["status"]) == "active" and int(row["stock_quantity"]) > 0,
            "specs": specs,
        }

    def search_products(
        self,
        query: str = "",
        category: str | None = None,
        max_price: float | None = None,
        only_available: bool = True,
        limit: int = 10,
    ) -> dict[str, Any]:
        inferred_category = infer_category(category or query)
        if max_price is None:
            max_price = parse_price_limit(query)

        frame = self.products.copy()
        if only_available:
            frame = frame[(frame["status"] == "active") & (frame["stock_quantity"] > 0)]
        if inferred_category is not None:
            frame = frame[frame["category_id"] == inferred_category]
        frame = frame.assign(
            effective_price=frame.apply(
                lambda row: self._effective_price(float(row["price_brl"]), self.active_promotions.get(int(row["product_id"]))),
                axis=1,
            )
        )
        if max_price is not None:
            frame = frame[frame["effective_price"] <= max_price + 0.001]

        normalized_query = normalize(query)
        category_tokens = {
            token
            for aliases in CATEGORY_ALIASES.values()
            for alias in aliases
            for token in normalize(alias).split()
        }
        category_tokens |= {token for name in self.category_names.values() for token in normalize(name).split()}
        query_terms = [
            term for term in normalized_query.split()
            if term not in STOP_WORDS and term not in category_tokens and not term.isdigit()
        ]
        cleaned_query = " ".join(query_terms)

        ranked: list[tuple[float, pd.Series]] = []
        for _, row in frame.iterrows():
            candidate = normalize(f"{row['name']} {row.get('description', '')}")
            if cleaned_query:
                score_name = fuzz.token_set_ratio(cleaned_query, normalize(row["name"]))
                score_full = fuzz.token_set_ratio(cleaned_query, candidate)
                coverage = sum(1 for term in query_terms if term in candidate) / max(1, len(query_terms))
                score = max(score_name, score_full * 0.9, coverage * 100)
                if score < 32:
                    continue
            else:
                score = 0.0
            ranked.append((score, row))

        if cleaned_query:
            ranked.sort(key=lambda item: (item[0], -float(item[1]["effective_price"])), reverse=True)
        else:
            ranked.sort(key=lambda item: float(item[1]["effective_price"]))
        results = [self._product_dict(row) for _, row in ranked[: max(1, min(limit, 30))]]
        return {
            "count": len(results),
            "filters": {
                "category": self.category_names.get(inferred_category) if inferred_category else None,
                "max_price_brl": max_price,
                "only_available": only_available,
            },
            "products": results,
            "notice": None if results else "No products match these filters in the supplied catalog.",
        }

    def get_product_details(self, product_query: str) -> dict[str, Any]:
        query = normalize(product_query)
        if not query:
            return {"found": False, "message": "Please provide a product name or model."}
        best: tuple[float, pd.Series] | None = None
        for _, row in self.products.iterrows():
            name = normalize(row["name"])
            score = max(fuzz.WRatio(query, name), fuzz.token_set_ratio(query, name))
            if best is None or score > best[0]:
                best = (score, row)
        if best is None or best[0] < 55:
            return {"found": False, "message": "Product not found in the supplied catalog. Ask for the full model name."}
        product = self._product_dict(best[1])
        product["found"] = True
        return product

    def get_order_status(self, order_id: int) -> dict[str, Any]:
        rows = self.orders[self.orders["order_id"] == int(order_id)]
        if rows.empty:
            return {"found": False, "message": "Order not found in the supplied dataset."}
        row = rows.iloc[0]
        items: list[dict[str, Any]] = []
        if not self.order_items.empty:
            product_names = dict(zip(self.products["product_id"], self.products["name"]))
            item_rows = self.order_items[self.order_items["order_id"] == int(order_id)]
            items = [
                {
                    "product_id": int(item.product_id),
                    "name": str(product_names.get(int(item.product_id), "Unknown product")),
                    "quantity": int(item.quantity),
                }
                for item in item_rows.itertuples(index=False)
            ]
        tracking = row.get("tracking_code")
        estimated = row.get("estimated_delivery")
        notes = row.get("notes")
        return {
            "found": True,
            "order_id": int(row["order_id"]),
            "status": str(row["status"]),
            "order_date": str(row["order_date"]),
            "total_brl": float(row["total_brl"]),
            "payment_method": str(row["payment_method"]),
            "tracking_code": None if pd.isna(tracking) else str(tracking),
            "estimated_delivery": None if pd.isna(estimated) else str(estimated),
            "notes": None if pd.isna(notes) else str(notes),
            "items": items,
            "data_warning": (
                "Demo data only. The dataset has no authentication, so never expose real order "
                "details to an unverified caller in production."
            ),
        }
