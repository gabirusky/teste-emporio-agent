from pathlib import Path

import pytest

from emporio_agent.data_store import DataStore
from emporio_agent.policy_retriever import PolicyRetriever
from emporio_agent.tools import AgentTools

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def data() -> DataStore:
    return DataStore(
        ROOT / "data/products.csv",
        ROOT / "data/orders.csv",
        ROOT / "data/categories.csv",
        ROOT / "data/promotions.csv",
        ROOT / "data/customers.csv",
        ROOT / "data/order_items.csv",
    )


@pytest.fixture(scope="module")
def policies() -> PolicyRetriever:
    return PolicyRetriever(ROOT / "data/policies.pdf")


@pytest.fixture(scope="module")
def tools(data: DataStore, policies: PolicyRetriever) -> AgentTools:
    return AgentTools(data, policies)


def test_available_products_respect_price_and_stock(data: DataStore):
    result = data.search_products(
        "Which acoustic or classical guitars do you have available for up to R$1,000?"
    )
    assert result["count"] > 0
    assert result["filters"]["category"] == "Violões"
    assert result["filters"]["max_price_brl"] == 1000.0
    assert all(product["available"] for product in result["products"])
    assert all(product["effective_price_brl"] <= 1000 for product in result["products"])


def test_active_promotion_changes_effective_price(data: DataStore):
    product = data.get_product_details("Kalani KAL-700T")
    assert product["found"] is True
    assert product["price_brl"] == 359.0
    assert product["promotion"]["discount_percent"] == 10.0
    assert product["effective_price_brl"] == 323.1


def test_zero_stock_product_is_not_available(data: DataStore):
    product = data.get_product_details("Giannini GF-3D")
    assert product["found"] is True
    assert product["stock_quantity"] == 0
    assert product["available"] is False


def test_specific_product_lookup(data: DataStore):
    product = data.get_product_details("Takamine GD20")
    assert product["found"] is True
    assert product["name"] == "Takamine GD20 Dreadnought Natural"
    assert product["price_brl"] == 2199.0
    assert product["available"] is True


def test_order_status_includes_items_and_security_warning(data: DataStore):
    order = data.get_order_status(8)
    assert order["found"] is True
    assert order["status"] == "shipped"
    assert order["tracking_code"] == "BRJL5544332BR"
    assert order["items"][0]["name"] == "Kala KA-C Concert Mogno"
    assert "authentication" in order["data_warning"]


def test_return_policy_retrieval(policies: PolicyRetriever):
    result = policies.search("I bought a guitar online and changed my mind. Can I return it?", top_k=1)
    top = result["results"][0]
    assert top["page"] == 4
    assert "7 (sete) dias" in top["text"]
    assert "reembolso" in top["text"]


def test_business_hours_retrieval(policies: PolicyRetriever):
    top = policies.search("What are your business hours?", top_k=1)["results"][0]
    assert top["page"] == 2
    assert "Horário de Funcionamento" in top["text"]


def test_accessory_scope_retrieval(policies: PolicyRetriever):
    top = policies.search("Do you sell guitar picks and cables?", top_k=1)["results"][0]
    assert top["page"] in {2, 6}
    assert "acessórios" in top["text"].lower()


def test_price_limit_written_in_words(data: DataStore):
    result = data.search_products("acoustic guitars up to one thousand")
    assert result["filters"]["max_price_brl"] == 1000.0
    assert result["count"] > 0


def test_out_of_scope_redirection(tools: AgentTools):
    result = tools.execute("redirect_out_of_scope", {"topic": "guitar cables"})
    assert result["out_of_scope"] is True
    assert "musical instruments" in result["message"]


def test_unknown_tool_returns_error(tools: AgentTools):
    assert "Unknown tool" in tools.execute("does_not_exist", {})["error"]


def test_flauta_doce_returns_zero_products(data: DataStore):
    result = data.search_products("flauta doce", only_available=True, limit=10)
    assert result["count"] == 0
    assert result["filters"]["category"] == "Instrumentos de Sopro (Madeiras)"
    assert result["products"] == []
    assert result["notice"] is not None


def test_flauta_returns_zero_products(data: DataStore):
    result = data.search_products("flauta", only_available=True, limit=10)
    assert result["count"] == 0
    assert result["products"] == []


def test_unsupported_category_never_recommends_guitars_or_ukuleles(data: DataStore):
    result = data.search_products("flauta doce", only_available=True, limit=10)
    categories = {product["category"] for product in result["products"]}
    assert "Violões" not in categories
    assert "Guitarras" not in categories
    assert "Ukuleles" not in categories


def test_unsupported_category_normal_searches_still_work(data: DataStore):
    guitars = data.search_products("guitarra", only_available=True, limit=10)
    assert guitars["count"] > 0
    assert all(product["category"] == "Guitarras" for product in guitars["products"])

    ukuleles = data.search_products("ukulele", only_available=True, limit=10)
    assert ukuleles["count"] > 0
    assert all(product["category"] == "Ukuleles" for product in ukuleles["products"])

    violoes = data.search_products("violao", only_available=True, limit=10)
    assert violoes["count"] > 0
    assert all(product["category"] == "Violões" for product in violoes["products"])
