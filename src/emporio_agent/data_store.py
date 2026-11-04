from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

# Categories present in the catalog (per products.csv). Categories not present
# in the catalog are listed separately so unsupported instrument queries can be
# recognized and return zero results instead of unrelated fuzzy matches.
CATALOG_CATEGORY_ALIASES = {
    1: ["guitarra", "guitarras", "electric guitar", "electric guitars"],
    2: ["baixo", "baixos", "contrabaixo", "bass", "basses"],
    3: ["bateria", "baterias", "drums", "drum kit"],
    4: ["teclado", "teclados", "piano", "pianos", "sintetizador", "synthesizer", "keyboard", "keyboards"],
    5: ["violao", "violoes", "acoustic guitar", "acoustic guitars", "classical guitar", "classical guitars"],
    9: ["ukulele", "ukuleles"],
}

# Instrument categories that exist in the store taxonomy but have no products
# in the current catalog. Queries for these should return zero results rather
# than unrelated products from other categories.
UNSUPPORTED_CATEGORY_ALIASES = {
    6: ["sopro", "madeiras", "woodwind", "woodwinds", "flauta", "flute", "clarinete", "clarinet", "saxofone", "saxophone"],
    7: ["metais", "brass", "trompete", "trumpet", "trombone", "tuba", "trompa", "horn"],
    8: ["cordas orquestrais", "orchestral strings", "violino", "violin", "violoncelo", "cello"],
}

CATEGORY_ALIASES = {**CATALOG_CATEGORY_ALIASES, **UNSUPPORTED_CATEGORY_ALIASES}

STOP_WORDS = {
    "a", "an", "and", "are", "at", "available", "be", "below", "buy", "can", "cost",
    "could", "de", "da", "das", "do", "dos", "em", "for", "favor", "have", "has", "how",
    "i", "in", "is", "it", "less", "looking", "max", "maximum", "me", "menos", "my",
    "no", "of", "on", "option", "options", "or", "os", "as", "o", "um", "uma", "para",
    "please", "por", "preco", "precos", "price", "prices", "produto", "produtos",
    "product", "products", "quais", "qual", "quanto", "que", "reais", "store", "tem", "the",
    "to", "under", "up", "valor", "want", "which", "with", "you", "your", "custa", "custam",
    "disponivel", "disponiveis", "estoque", "stock", "instrument", "instruments", "instrumento",
    "instrumentos", "r", "rs", "ate", "mil", "one", "two", "three", "four", "five", "hundred",
    "thousand", "million", "dois", "tres", "quatro", "cinco", "cem", "all", "any", "brand",
    "brands", "cheap", "cheapest", "expensive", "find", "from", "give", "highest", "least",
    "list", "lowest", "most", "order", "see", "show", "some", "sort", "sorted", "specific",
    "top", "barato", "baratos", "caro", "caros", "mais", "priciest", "priced", "seu",
    "sua", "ascending", "by", "descending", "high", "low",
}

# Brand names present in the supplied catalog. The CSV has no brand column, so
# brands are derived from product names against this explicit lexicon. Matching
# any token of a product name is not used as a shortcut: words such as
# "Bateria", "Teclado" and "Violão" are product types, not brands.
KNOWN_BRANDS = {
    "yamaha": "Yamaha",
    "tagima": "Tagima",
    "giannini": "Giannini",
    "rozini": "Rozini",
    "shelby": "Shelby",
    "crafter": "Crafter",
    "martin": "Martin",
    "taylor": "Taylor",
    "takamine": "Takamine",
    "kala": "Kala",
    "ohana": "Ohana",
    "kalani": "Kalani",
    "fender": "Fender",
    "gibson": "Gibson",
    "ibanez": "Ibanez",
    "prs": "PRS",
    "music man": "Music Man",
    "pearl": "Pearl",
    "korg": "Korg",
    "nord": "Nord",
    "roland": "Roland",
}

# Tokens that describe a product type or a specification. Used only as a
# fallback when deriving a brand from a name that is not covered by the
# lexicon above, so a product type is never mistaken for a brand.
PRODUCT_TYPE_TOKENS = {
    "aco", "acoustic", "acustica", "acustico", "baixo", "baixos", "bass", "basses",
    "bateria", "baterias", "classical", "concert", "dreadnought", "drum", "drums",
    "eletrica", "eletrico", "electric", "folk", "guitar", "guitarra", "guitarras",
    "guitars", "keyboard", "keyboards", "kit", "model", "nylon", "piano", "pianos",
    "pro", "series", "sintetizador", "soprano", "studio", "synth", "synthesizer",
    "teclado", "teclados", "tenor", "baritono", "ukulele", "ukuleles", "violao",
    "violoes",
}

AGGREGATION_METRICS = {"price", "stock", "average_price", "top_by_price"}

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


def extract_brand(name: Any, *, allow_fallback: bool = True) -> str:
    """Derive a brand from a product name without confusing product types.

    The supplied CSV has no brand column. Known brands are matched anywhere in
    the name (so "Bateria Acústica Yamaha Kit 1" still resolves to Yamaha). If
    the name has no known brand, the first meaningful non-product-type token is
    used as a conservative fallback. Query text uses ``allow_fallback=False`` so
    words such as "cheapest" are never treated as a brand.
    """
    normalized_name = normalize(name)
    if not normalized_name:
        return ""

    best: tuple[int, int, str] | None = None
    for brand_key, brand_display in KNOWN_BRANDS.items():
        match = re.search(rf"\b{re.escape(brand_key)}\b", normalized_name)
        if match:
            candidate = (match.start(), -len(brand_key), brand_display)
            if best is None or candidate < best:
                best = candidate
    if best is not None:
        return best[2]
    if not allow_fallback:
        return ""

    for token in normalized_name.split():
        if token in PRODUCT_TYPE_TOKENS or token.isdigit() or len(token) < 2:
            continue
        return token.replace("_", " ").title()
    return ""


def brand_display(brand_key: str, original: str | None = None) -> str:
    """Return a stable human-readable brand label for applied filters."""
    if brand_key in KNOWN_BRANDS:
        return KNOWN_BRANDS[brand_key]
    if original and str(original).strip():
        return str(original).strip()
    return brand_key.title()


def infer_sort_intent(text: str) -> tuple[str, str] | None:
    """Infer an explicit sort only for clear ranking language."""
    normalized = normalize(text)
    if not normalized:
        return None
    if re.search(r"\b(price|preco|priced)\b", normalized):
        if re.search(r"\b(ascending|low to high|menor para maior)\b", normalized):
            return ("price", "asc")
        if re.search(r"\b(descending|high to low|maior para menor)\b", normalized):
            return ("price", "desc")
    if re.search(r"\b(cheapest|lowest price|least expensive|mais barato|menor preco|preco mais baixo)\b", normalized):
        return ("price", "asc")
    if re.search(r"\b(most expensive|highest price|priciest|mais caro|maior preco|preco mais alto)\b", normalized):
        return ("price", "desc")
    if re.search(r"\b(top|most|highest)\b", normalized) and re.search(r"\b(price|preco|priced)\b", normalized):
        return ("price", "desc")
    if re.search(r"\b(stock|estoque)\b", normalized):
        if re.search(r"\b(highest|largest|most|maior|mais alto)\b", normalized):
            return ("stock", "desc")
        if re.search(r"\b(lowest|least|smallest|menor|mais baixo)\b", normalized):
            return ("stock", "asc")
    return None


def infer_catalog_aggregation_intent(text: str) -> dict[str, str] | None:
    """Classify explicit catalog-wide ranking/aggregation questions.

    Kept as an internal helper for backwards compatibility. The LLM-facing
    interface is search_products only.
    """
    normalized = normalize(text)
    if not normalized:
        return None
    if re.search(r"\b(average|mean|media|preco medio)\b", normalized):
        return {"metric": "average_price", "direction": "max"}
    if re.search(r"\btop\b", normalized) and re.search(r"\b(price|preco|expensive|caro)\b", normalized):
        return {"metric": "top_by_price", "direction": "max"}
    if re.search(r"\b(stock|estoque)\b", normalized):
        if re.search(r"\b(maior|mais alto|highest|largest|most)\b", normalized):
            return {"metric": "stock", "direction": "max"}
        if re.search(r"\b(menor|mais baixo|lowest|least|smallest)\b", normalized):
            return {"metric": "stock", "direction": "min"}
    if re.search(r"\b(most expensive|highest price|priciest|mais caro|maior preco|preco mais alto)\b", normalized):
        return {"metric": "price", "direction": "max"}
    if re.search(r"\b(cheapest|lowest price|least expensive|mais barato|menor preco|preco mais baixo)\b", normalized):
        return {"metric": "price", "direction": "min"}
    return None


def _coerce_optional_float(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parsed = _parse_amount(str(value))
    if parsed is None:
        raise ValueError(f"{field_name} must be a number")
    return parsed


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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


def infer_supported_category(text: str) -> int | None:
    """Return the category id only when it is represented in the catalog.

    Returns None for unsupported categories (e.g. flutes, brass, orchestral
    strings) so callers can decide to return zero results instead of falling
    back to unrelated fuzzy matches.
    """
    normalized = normalize(text)
    if re.search(r"\b(guitarras?|guitars?)\b", normalized) and re.search(r"\b(acoustic|classical|nylon)\b", normalized):
        return 5
    for category_id, aliases in CATALOG_CATEGORY_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(normalize(alias))}\b", normalized):
                return category_id
    return None


def infer_unsupported_category(text: str) -> int | None:
    """Return the category id when the query names an unsupported instrument
    category (present in the taxonomy but without products in the catalog)."""
    normalized = normalize(text)
    for category_id, aliases in UNSUPPORTED_CATEGORY_ALIASES.items():
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
        brand_column = next((column for column in self.products.columns if str(column).lower() == "brand"), None)
        if brand_column is None:
            self.products["brand"] = self.products["name"].map(extract_brand)
        else:
            self.products["brand"] = self.products[brand_column].fillna("").astype(str).str.strip()
        self.products["brand_normalized"] = self.products["brand"].map(normalize)

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
        effective_price = self._effective_price(price, promotion)
        stock = int(row["stock_quantity"])
        status = str(row["status"])
        return {
            "product_id": product_id,
            "name": str(row["name"]),
            "brand": str(row.get("brand", "") or "").strip(),
            "category": self.category_names.get(int(row["category_id"]), "Unmapped category"),
            "description": str(row.get("description", "")),
            "price": price,
            "price_brl": price,
            "effective_price": effective_price,
            "effective_price_brl": effective_price,
            "promotion": promotion,
            "stock": stock,
            "stock_quantity": stock,
            "status": status,
            "available": status.strip().lower() == "active" and stock > 0,
            "specs": specs,
        }

    @staticmethod
    def _normalize_sort(sort_by: Any, sort_order: Any) -> tuple[str | None, str | None]:
        if sort_by is None or str(sort_by).strip() == "":
            return (None, None)
        key = normalize(sort_by).replace(" ", "_")
        key = {
            "price_brl": "price",
            "effective_price": "price",
            "effective_price_brl": "price",
            "stock_quantity": "stock",
            "product_name": "name",
        }.get(key, key)
        if key not in {"price", "stock", "name"}:
            raise ValueError("sort_by must be one of: price, stock, name")
        order = normalize(sort_order or "asc")
        order = {"ascending": "asc", "descending": "desc"}.get(order, order)
        if order not in {"asc", "desc"}:
            raise ValueError("sort_order must be asc or desc")
        return (key, order)

    @staticmethod
    def _sort_frame(frame: pd.DataFrame, sort_key: str, sort_order: str) -> pd.DataFrame:
        ascending = sort_order == "asc"
        if sort_key == "price":
            ordered = frame.assign(_sort_price=pd.to_numeric(frame["price_brl"], errors="coerce"))
            return ordered.sort_values(
                ["_sort_price", "product_id"],
                ascending=[ascending, True],
                kind="mergesort",
            )
        if sort_key == "stock":
            ordered = frame.assign(_sort_stock=pd.to_numeric(frame["stock_quantity"], errors="coerce"))
            return ordered.sort_values(
                ["_sort_stock", "price_brl", "product_id"],
                ascending=[ascending, True, True],
                kind="mergesort",
            )
        ordered = frame.assign(_sort_name=frame["name"].map(normalize))
        return ordered.sort_values(
            ["_sort_name", "product_id"],
            ascending=[ascending, True],
            kind="mergesort",
        )

    def _filters_payload(
        self,
        *,
        query: str,
        brand_key: str,
        brand: str | None,
        category_id: int | None,
        min_price: float | None,
        max_price: float | None,
        only_available: bool,
        sort_key: str | None,
        sort_order: str | None,
        limit: int,
    ) -> dict[str, Any]:
        return {
            "query": query or None,
            "brand": brand_display(brand_key, brand) if brand_key else None,
            "brand_normalized": brand_key or None,
            "category": self.category_names.get(category_id) if category_id else None,
            "min_price_brl": min_price,
            "max_price_brl": max_price,
            "only_available": only_available,
            "sort_by": sort_key,
            "sort_order": sort_order,
            "limit": limit,
        }

    def search_products(
        self,
        query: str = "",
        category: str | None = None,
        max_price: float | None = None,
        only_available: bool = True,
        limit: int = 10,
        brand: str | None = None,
        min_price: float | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> dict[str, Any]:
        """Unified deterministic catalog query.

        Filters are applied in this order: brand, availability, category/name,
        price range, sorting and finally the result limit. Brand matching is an
        exact normalized match against a derived structured brand field.
        """
        only_available = _coerce_bool(only_available, True)
        min_price = _coerce_optional_float(min_price, "min_price")
        max_price = _coerce_optional_float(max_price, "max_price")
        if max_price is None:
            max_price = parse_price_limit(query)

        try:
            limit_value = int(limit)
        except (TypeError, ValueError):
            limit_value = 10
        limit_value = max(1, min(limit_value, 500))

        requested_brand = str(brand).strip() if brand is not None else ""
        brand_key = normalize(requested_brand)
        query_brand = extract_brand(query, allow_fallback=False) if not brand_key else ""
        if query_brand:
            brand_key = normalize(query_brand)

        if sort_by is None:
            inferred_sort = infer_sort_intent(query)
            if inferred_sort is not None:
                sort_by, sort_order = inferred_sort
        sort_key, sort_order = self._normalize_sort(sort_by, sort_order)

        inferred_category = infer_category(category or query)
        unsupported_category = infer_unsupported_category(category or query)

        filters = self._filters_payload(
            query=query,
            brand_key=brand_key,
            brand=requested_brand or None,
            category_id=inferred_category,
            min_price=min_price,
            max_price=max_price,
            only_available=only_available,
            sort_key=sort_key,
            sort_order=sort_order,
            limit=limit_value,
        )

        # Instrument categories in the taxonomy but absent from this catalog
        # return zero results instead of falling back to fuzzy matches.
        if unsupported_category is not None and inferred_category == unsupported_category:
            filters["category"] = self.category_names.get(unsupported_category)
            return {
                "count": 0,
                "total_matching": 0,
                "total_matching_results": 0,
                "filters": filters,
                "applied_filters": dict(filters),
                "products": [],
                "notice": "No products match these filters in the supplied catalog.",
            }

        frame = self.products.copy()

        # 1. Brand filter: exact normalized equality, never a global fallback.
        if brand_key:
            frame = frame[frame["brand_normalized"] == brand_key]

        # 2. Availability: active status and positive stock.
        if only_available:
            status = frame["status"].astype(str).str.strip().str.lower()
            frame = frame[(status == "active") & (frame["stock_quantity"] > 0)]

        # 3. Category and product name/query.
        if inferred_category is not None:
            frame = frame[frame["category_id"] == inferred_category]

        if frame.empty:
            return {
                "count": 0,
                "total_matching": 0,
                "total_matching_results": 0,
                "filters": filters,
                "applied_filters": dict(filters),
                "products": [],
                "notice": "No products match these filters in the supplied catalog.",
            }

        frame = frame.assign(
            effective_price=frame.apply(
                lambda row: self._effective_price(float(row["price_brl"]), self.active_promotions.get(int(row["product_id"]))),
                axis=1,
            ).astype(float)
        )

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
        if brand_key:
            brand_tokens = set(brand_key.split())
            query_terms = [term for term in query_terms if term not in brand_tokens]
        cleaned_query = " ".join(query_terms)

        scores: list[float] = []
        for _, row in frame.iterrows():
            candidate = normalize(f"{row['name']} {row.get('description', '')}")
            if cleaned_query:
                score_name = fuzz.token_set_ratio(cleaned_query, normalize(row["name"]))
                score_full = fuzz.token_set_ratio(cleaned_query, candidate)
                coverage = sum(1 for term in query_terms if term in candidate) / max(1, len(query_terms))
                scores.append(max(score_name, score_full * 0.9, coverage * 100))
            else:
                scores.append(0.0)
        frame = frame.assign(_query_score=scores)
        if cleaned_query:
            frame = frame[frame["_query_score"] >= 32]

        # 4. Price range, using the numeric final price after active promotions.
        if min_price is not None:
            frame = frame[frame["effective_price"] >= min_price - 0.001]
        if max_price is not None:
            frame = frame[frame["effective_price"] <= max_price + 0.001]

        total_matching = int(len(frame))

        # 5. Sorting. Explicit sorting uses numeric database values, not strings.
        if frame.empty:
            ordered = frame
        elif sort_key is not None and sort_order is not None:
            ordered = self._sort_frame(frame, sort_key, sort_order)
        elif cleaned_query:
            ordered = frame.sort_values(
                ["_query_score", "effective_price", "product_id"],
                ascending=[False, False, True],
                kind="mergesort",
            )
        else:
            ordered = frame.sort_values(
                ["effective_price", "product_id"],
                ascending=[True, True],
                kind="mergesort",
            )

        # 6. Result limit is the final step. count is returned rows; total_matching
        # is the full number of rows that satisfied every filter.
        results = [self._product_dict(row) for _, row in ordered.head(limit_value).iterrows()]
        return {
            "count": len(results),
            "total_matching": total_matching,
            "total_matching_results": total_matching,
            "filters": filters,
            "applied_filters": dict(filters),
            "products": results,
            "notice": None if results else "No products match these filters in the supplied catalog.",
        }

    def get_catalog_extremes(
        self,
        metric: str = "price",
        direction: str = "max",
        limit: int = 5,
        only_available: bool = True,
    ) -> dict[str, Any]:
        """Internal ranking helper retained for backwards compatibility.

        This method is deliberately not exposed as an LLM-facing tool. New
        product queries should use search_products with sort_by/sort_order.
        """
        metric_key = normalize(metric or "price").replace(" ", "_")
        metric_key = {
            "most_expensive": "price",
            "highest_price": "price",
            "lowest_price": "price",
            "cheapest": "price",
            "preco": "price",
            "precos": "price",
            "valor": "price",
            "estoque": "stock",
            "average": "average_price",
            "mean_price": "average_price",
            "media": "average_price",
            "preco_medio": "average_price",
            "average_price_brl": "average_price",
            "top": "top_by_price",
            "top_n_by_price": "top_by_price",
        }.get(metric_key, metric_key)
        if metric_key not in AGGREGATION_METRICS:
            return {"error": f"Unsupported metric '{metric}'. Use one of: {', '.join(sorted(AGGREGATION_METRICS))}.", "products": []}

        direction_key = normalize(direction or "max")
        direction_key = {
            "desc": "max",
            "descending": "max",
            "highest": "max",
            "maior": "max",
            "mais_alto": "max",
            "mais_caro": "max",
            "asc": "min",
            "ascending": "min",
            "lowest": "min",
            "menor": "min",
            "mais_baixo": "min",
            "mais_barato": "min",
        }.get(direction_key, direction_key)
        if direction_key not in {"min", "max"}:
            return {"error": f"Unsupported direction '{direction}'. Use 'max' or 'min'.", "products": []}

        try:
            limit_value = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            limit_value = 5
        only_available = _coerce_bool(only_available, True)
        catalog_size = int(len(self.products))

        status = self.products["status"].astype(str).str.strip().str.lower()
        frame = self.products[status == "active"].copy()
        if only_available:
            frame = frame[frame["stock_quantity"] > 0]
        frame["_price"] = pd.to_numeric(frame["price_brl"], errors="coerce")
        frame = frame[frame["_price"].notna()]

        base = {
            "metric": metric_key,
            "direction": direction_key,
            "only_available": only_available,
            "catalog_size": catalog_size,
            "eligible_count": int(len(frame)),
        }

        if frame.empty:
            return {
                **base,
                "value": None,
                "products": [],
                "notice": "No eligible products in the supplied catalog.",
            }

        if metric_key == "average_price":
            effective = [
                self._effective_price(float(row["_price"]), self.active_promotions.get(int(row["product_id"])))
                for _, row in frame.iterrows()
            ]
            average = round(float(frame["_price"].mean()), 2)
            return {
                **base,
                "value": average,
                "average_price_brl": average,
                "average_effective_price_brl": round(sum(effective) / len(effective), 2) if effective else None,
                "min_price_brl": round(float(frame["_price"].min()), 2),
                "max_price_brl": round(float(frame["_price"].max()), 2),
                "products": [],
                "notice": None,
            }

        if metric_key == "price":
            extreme = float(frame["_price"].max() if direction_key == "max" else frame["_price"].min())
            tied = frame[(frame["_price"] - extreme).abs() < 0.005].sort_values("product_id", kind="mergesort")
            products = [self._product_dict(row) for _, row in tied.iterrows()]
            return {
                **base,
                "value": round(extreme, 2),
                "tie_count": len(products),
                "products": products,
                "notice": None,
            }

        if metric_key == "stock":
            ordered = frame.sort_values(
                ["stock_quantity", "_price", "product_id"],
                ascending=[direction_key == "min", direction_key == "min", True],
                kind="mergesort",
            )
        else:
            ordered = frame.sort_values(
                ["_price", "product_id"],
                ascending=[direction_key == "min", True],
                kind="mergesort",
            )

        products = [self._product_dict(row) for _, row in ordered.head(limit_value).iterrows()]
        value = (
            int(products[0]["stock_quantity"])
            if metric_key == "stock" and products
            else (products[0]["price_brl"] if products else None)
        )
        return {
            **base,
            "value": value,
            "tie_count": len(products),
            "products": products,
            "notice": None,
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
