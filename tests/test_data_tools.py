from pathlib import Path

import pytest

from emporio_agent.data_store import DataStore
from emporio_agent.policy_retriever import PolicyRetriever
from emporio_agent.tools import AgentTools, TOOL_SCHEMAS

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


def test_most_expensive_instrument_in_stock(data: DataStore):
    result = data.search_products(sort_by="price", sort_order="desc", limit=1)
    assert result["count"] == 1
    product = result["products"][0]
    assert product["product_id"] == 143
    assert product["name"] == "Teclado Sintetizador Nord Synth 2 Pro"
    assert product["price_brl"] == 19567.0
    assert product["available"] is True


def test_cheapest_instrument_in_stock(data: DataStore):
    result = data.search_products(sort_by="price", sort_order="asc", limit=1)
    assert result["count"] == 1
    product = result["products"][0]
    assert product["product_id"] == 119
    assert product["price_brl"] == 159.9
    assert product["available"] is True


def test_cheapest_yamaha_instrument_in_stock(data: DataStore):
    result = data.search_products(brand="Yamaha", sort_by="price", sort_order="asc", limit=1)
    assert result["count"] == 1
    product = result["products"][0]
    assert product["product_id"] == 81
    assert product["name"] == "Yamaha C40 Nylon Natural"
    assert product["brand"] == "Yamaha"
    assert product["price_brl"] == 599.9


def test_all_available_products_from_brand(data: DataStore):
    result = data.search_products(brand="Yamaha", only_available=True, limit=100)
    assert result["count"] == 10
    assert result["total_matching"] == 10
    assert all(product["brand"] == "Yamaha" for product in result["products"])
    assert all(product["status"] == "active" for product in result["products"])
    assert all(product["stock_quantity"] > 0 for product in result["products"])
    assert {product["product_id"] for product in result["products"]} >= {81, 139, 141}


def test_brand_search_is_case_insensitive(data: DataStore):
    upper = data.search_products(brand="YAMAHA", limit=100)
    lower = data.search_products(brand="yamaha", limit=100)
    mixed = data.search_products(brand="YaMaHa", limit=100)
    expected_ids = [product["product_id"] for product in upper["products"]]
    assert expected_ids == [product["product_id"] for product in lower["products"]]
    assert expected_ids == [product["product_id"] for product in mixed["products"]]
    assert upper["filters"]["brand"] == "Yamaha"
    assert upper["filters"]["brand_normalized"] == "yamaha"


def test_brand_with_no_matching_products_is_empty(data: DataStore):
    result = data.search_products(brand="Steinway", limit=100)
    assert result["count"] == 0
    assert result["total_matching"] == 0
    assert result["products"] == []
    assert result["filters"]["brand"] == "Steinway"
    assert result["notice"] is not None


def test_yamaha_search_never_returns_other_brands(data: DataStore):
    by_brand = data.search_products(brand="Yamaha", limit=100)
    by_query = data.search_products(query="Yamaha", limit=100)
    assert by_brand["products"]
    assert all(product["brand"] == "Yamaha" for product in by_brand["products"])
    assert all(product["brand"] == "Yamaha" for product in by_query["products"])


def test_price_sorting_uses_numeric_values(data: DataStore):
    ascending = data.search_products(sort_by="price", sort_order="asc", limit=100)
    descending = data.search_products(sort_by="price", sort_order="desc", limit=100)
    ascending_prices = [product["price_brl"] for product in ascending["products"]]
    descending_prices = [product["price_brl"] for product in descending["products"]]
    assert ascending_prices == sorted(ascending_prices)
    assert descending_prices == sorted(descending_prices, reverse=True)
    assert ascending_prices[0] == 159.9
    assert descending_prices[0] == 19567.0


def test_combining_brand_price_range_and_availability(data: DataStore):
    result = data.search_products(
        brand="Yamaha",
        min_price=1000,
        max_price=4000,
        only_available=True,
        sort_by="price",
        sort_order="asc",
        limit=100,
    )
    assert result["total_matching"] == 4
    assert [product["product_id"] for product in result["products"]] == [92, 114, 104, 98]
    assert all(product["brand"] == "Yamaha" for product in result["products"])
    assert all(1000 <= product["price_brl"] <= 4000 for product in result["products"])
    assert all(product["available"] for product in result["products"])
    assert result["filters"]["brand"] == "Yamaha"
    assert result["filters"]["min_price_brl"] == 1000.0
    assert result["filters"]["max_price_brl"] == 4000.0
    assert result["filters"]["sort_by"] == "price"
    assert result["filters"]["sort_order"] == "asc"


def test_brand_filter_never_falls_back_to_global_catalog(data: DataStore):
    empty_brand = data.search_products(brand="Steinway", limit=100)
    global_catalog = data.search_products(sort_by="price", sort_order="asc", limit=100)
    assert empty_brand["products"] == []
    assert empty_brand["total_matching"] == 0
    assert global_catalog["total_matching"] > 0
    # A zero-match brand must not silently become an unfiltered catalog search.
    assert empty_brand["total_matching"] != global_catalog["total_matching"]


def test_search_products_schema_is_unified_and_has_no_extremes_tool():
    schemas = {schema["function"]["name"]: schema for schema in TOOL_SCHEMAS}
    assert "search_products" in schemas
    assert "get_catalog_extremes" not in schemas
    properties = schemas["search_products"]["function"]["parameters"]["properties"]
    for field in ("query", "brand", "min_price", "max_price", "only_available", "sort_by", "sort_order", "limit"):
        assert field in properties
    assert schemas["search_products"]["function"]["parameters"]["required"] == []
