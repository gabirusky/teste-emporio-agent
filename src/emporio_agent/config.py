from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    base_url: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    model: str = os.getenv("LLM_MODEL", "")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    max_tool_rounds: int = int(os.getenv("LLM_MAX_TOOL_ROUNDS", "4"))
    products_csv: str = os.getenv("PRODUCTS_CSV", "data/products.csv")
    orders_csv: str = os.getenv("ORDERS_CSV", "data/orders.csv")
    customers_csv: str = os.getenv("CUSTOMERS_CSV", "data/customers.csv")
    categories_csv: str = os.getenv("CATEGORIES_CSV", "data/categories.csv")
    promotions_csv: str = os.getenv("PROMOTIONS_CSV", "data/promotions.csv")
    policies_pdf: str = os.getenv("POLICIES_PDF", "data/policies.pdf")

    def validate_llm(self) -> None:
        missing = [name for name, value in (("LLM_API_KEY", self.api_key), ("LLM_MODEL", self.model)) if not value]
        if missing:
            raise RuntimeError("Missing settings: " + ", ".join(missing) + ". Check your .env file.")
