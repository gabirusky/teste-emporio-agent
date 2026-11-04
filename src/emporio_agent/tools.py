from __future__ import annotations

from typing import Any

from .data_store import DataStore
from .policy_retriever import PolicyRetriever


class AgentTools:
    def __init__(self, data: DataStore, policies: PolicyRetriever):
        self.data = data
        self.policies = policies

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
        return self.data.search_products(
            query=query,
            category=category,
            max_price=max_price,
            only_available=only_available,
            limit=limit,
            brand=brand,
            min_price=min_price,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def get_product_details(self, product_query: str) -> dict[str, Any]:
        return self.data.get_product_details(product_query)

    def get_order_status(self, order_id: int) -> dict[str, Any]:
        return self.data.get_order_status(order_id)

    def search_policies(self, query: str, top_k: int = 3) -> dict[str, Any]:
        return self.policies.search(query, top_k)

    @staticmethod
    def redirect_out_of_scope(topic: str) -> dict[str, Any]:
        return {
            "out_of_scope": True,
            "topic": topic,
            "message": (
                "Empório da Música sells musical instruments only. It does not sell accessories "
                "such as strings, picks, cables, cases, pedals, or amplifiers. Offer help with "
                "instruments, orders, delivery, or store policies instead."
            ),
        }

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "search_products": self.search_products,
            "get_product_details": self.get_product_details,
            "get_order_status": self.get_order_status,
            "search_policies": self.search_policies,
            "redirect_out_of_scope": self.redirect_out_of_scope,
        }
        if name not in handlers:
            return {"error": f"Unknown tool: {name}"}
        if not isinstance(arguments, dict):
            return {"error": f"Invalid arguments for {name}: expected an object"}
        try:
            return handlers[name](**arguments)
        except TypeError as exc:
            return {"error": f"Invalid arguments for {name}: {exc}"}
        except Exception as exc:
            return {"error": f"Tool {name} failed: {type(exc).__name__}: {exc}"}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Unified product catalog query for search, filtering, ranking, and stock/price checks. "
                "Use this for every product question, including cheapest/most expensive and top-N "
                "rankings. Filtering and sorting are deterministic inside the tool. By default it "
                "returns only active products with positive stock. An empty result means no product "
                "matched the filters; never replace a brand filter with catalog-wide results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional product name, model, instrument, or description. Omit to browse."},
                    "brand": {"type": "string", "description": "Optional exact brand name, matched case-insensitively, e.g. Yamaha, Tagima, Martin, Nord."},
                    "category": {"type": "string", "description": "Optional category, e.g. acoustic guitars, electric guitars, basses, drums, keyboards, or ukuleles."},
                    "min_price": {"type": "number", "description": "Minimum final price in BRL, without the currency symbol."},
                    "max_price": {"type": "number", "description": "Maximum final price in BRL, without the currency symbol."},
                    "only_available": {"type": "boolean", "description": "Default true: active status and stock greater than zero. Set false to include unavailable items."},
                    "sort_by": {"type": "string", "enum": ["price", "stock", "name"], "description": "Sort field using numeric price, numeric stock, or product name."},
                    "sort_order": {"type": "string", "enum": ["asc", "desc"], "description": "Sort direction. Use desc for most expensive and asc for cheapest."},
                    "limit": {"type": "integer", "description": "Maximum number of returned rows after all filters (1 to 500)."},
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": (
                "Look up a specific product by name or model, including list price, final price, "
                "stock, specifications, and active promotion. Use this before answering a price "
                "or availability question about a specific model."
            ),
            "parameters": {
                "type": "object",
                "properties": {"product_query": {"type": "string", "description": "Product name or model, e.g. Takamine GD20."}},
                "required": ["product_query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": (
                "Look up a demonstration order by numeric order ID. Returns status, items, "
                "tracking code, and estimated delivery. The dataset has no customer "
                "authentication, so do not present this as a secure production lookup."
            ),
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "integer", "description": "Numeric order identifier."}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policies",
            "description": (
                "Search the store policy PDF. Use this for business hours, address, payment "
                "methods, installments, exchanges, returns, warranty, shipping, delivery, "
                "promotions, privacy, and store scope. English questions are expanded to "
                "Portuguese before retrieval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Customer question or key policy terms."},
                    "top_k": {"type": "integer", "description": "Number of excerpts to return (1 to 5)."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redirect_out_of_scope",
            "description": (
                "Use this when the request is unrelated to the store's musical instruments, "
                "orders, delivery, or policies."
            ),
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string", "description": "Short description of the unsupported topic."}},
                "required": ["topic"],
                "additionalProperties": False,
            },
        },
    },
]
