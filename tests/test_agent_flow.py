import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from emporio_agent.agent import MusicStoreAgent
from emporio_agent.config import Settings
from emporio_agent.data_store import DataStore
from emporio_agent.policy_retriever import PolicyRetriever
from emporio_agent.tools import AgentTools

ROOT = Path(__file__).resolve().parents[1]


def tool_response(name: str, arguments: dict, call_id: str = "call_1") -> SimpleNamespace:
    tool_call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call]))])


def raw_tool_response(name: str, raw_arguments: str, call_id: str = "call_1") -> SimpleNamespace:
    tool_call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=raw_arguments),
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call]))])


def text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))])


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return text_response("Done.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


@pytest.fixture(scope="module")
def tools() -> AgentTools:
    data = DataStore(
        ROOT / "data/products.csv",
        ROOT / "data/orders.csv",
        ROOT / "data/categories.csv",
        ROOT / "data/promotions.csv",
        ROOT / "data/customers.csv",
        ROOT / "data/order_items.csv",
    )
    return AgentTools(data, PolicyRetriever(ROOT / "data/policies.pdf"))


def make_agent(tools: AgentTools, responses, max_tool_rounds: int = 4):
    client = FakeClient(responses)
    settings = Settings(api_key="fake-key", model="fake-model", max_tool_rounds=max_tool_rounds)
    return MusicStoreAgent(settings, tools, client=client), client


def test_agent_executes_tool_and_returns_grounded_answer(tools: AgentTools):
    agent, client = make_agent(tools, [
        tool_response("get_product_details", {"product_query": "Takamine GD20"}),
        text_response("The Takamine GD20 costs R$ 2.199,00."),
    ])

    answer = agent.respond("How much does the Takamine GD20 cost?")

    assert answer == "The Takamine GD20 costs R$ 2.199,00."
    assert agent.last_tool_calls == [{"name": "get_product_details", "arguments": {"product_query": "Takamine GD20"}}]
    tool_message = next(message for message in client.completions.calls[1]["messages"] if message.get("role") == "tool")
    assert "2199.0" in tool_message["content"]


def test_agent_passes_policy_excerpts_to_model(tools: AgentTools):
    agent, client = make_agent(tools, [
        tool_response("search_policies", {"query": "return policy", "top_k": 1}),
        text_response("You have 7 days to return it."),
    ])

    agent.respond("I bought a guitar online and changed my mind. Can I return it?")

    tool_message = next(message for message in client.completions.calls[1]["messages"] if message.get("role") == "tool")
    payload = json.loads(tool_message["content"])
    assert payload["results"][0]["page"] == 4
    assert "7 (sete) dias" in payload["results"][0]["text"]


def test_agent_handles_provider_failure(tools: AgentTools):
    agent, _ = make_agent(tools, [RuntimeError("provider down")])

    answer = agent.respond("How much is the Takamine GD20?")

    assert "could not reach the ai service" in answer.lower()
    assert agent.history[-1]["role"] == "assistant"


def test_agent_handles_malformed_tool_arguments(tools: AgentTools):
    agent, _ = make_agent(tools, [
        raw_tool_response("get_order_status", "{not-json"),
        text_response("I could not check that order."),
    ])

    answer = agent.respond("What is the status of order number 8?")

    assert answer == "I could not check that order."
    assert agent.last_tool_calls == [{"name": "get_order_status", "arguments": {}}]


def test_agent_stops_after_max_tool_rounds(tools: AgentTools):
    agent, _ = make_agent(tools, [
        tool_response("get_product_details", {"product_query": "Takamine GD20"}),
        tool_response("get_product_details", {"product_query": "Takamine GD20"}, call_id="call_2"),
    ], max_tool_rounds=1)

    answer = agent.respond("How much is the Takamine GD20?")

    assert "human agent" in answer


def test_language_directive_follows_customer_message():
    english = MusicStoreAgent._language_directive("How much does the Takamine GD20 cost?")
    portuguese = MusicStoreAgent._language_directive("Quanto custa o Takamine GD20?")

    assert "English" in english
    assert "Portuguese" in portuguese


def test_order_answers_do_not_imply_ownership():
    assert MusicStoreAgent._sanitize_answer("Your order #8 is shipped.") == "Order #8 is shipped."
    assert MusicStoreAgent._sanitize_answer("Seu pedido #8 foi enviado.") == "Pedido #8 foi enviado."


def test_history_is_windowed_and_reset_clears_state(tools: AgentTools):
    responses = [text_response(f"Answer {index}") for index in range(9)]
    agent, client = make_agent(tools, responses)

    for index in range(9):
        agent.respond(f"Question {index}")

    last_messages = client.completions.calls[-1]["messages"]
    assert last_messages[0]["role"] == "system"
    assert len(last_messages) <= 17
    assert len(agent.history) == 18

    agent.reset()
    assert agent.history == []
    assert agent.last_tool_calls == []
