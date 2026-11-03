from __future__ import annotations

from .agent import MusicStoreAgent
from .config import Settings
from .data_store import DataStore
from .policy_retriever import PolicyRetriever
from .tools import AgentTools


def build_agent(settings: Settings) -> MusicStoreAgent:
    data = DataStore(
        settings.products_csv,
        settings.orders_csv,
        settings.categories_csv,
        settings.promotions_csv,
        settings.customers_csv,
        settings.order_items_csv,
    )
    policies = PolicyRetriever(settings.policies_pdf)
    return MusicStoreAgent(settings, AgentTools(data, policies))


def main() -> None:
    settings = Settings()
    settings.validate_llm()
    agent = build_agent(settings)

    print("\nEmpório da Música | Virtual assistant")
    print("Type your message. Commands: /reset to clear history, /exit to quit.\n")
    while True:
        try:
            message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSee you soon!")
            break
        if not message:
            continue
        if message.lower() in {"/exit", "/quit", "/sair"}:
            print("Empório da Música: See you soon! Keep making music.")
            break
        if message.lower() == "/reset":
            agent.reset()
            print("Conversation history cleared.\n")
            continue
        try:
            answer = agent.respond(message)
            print(f"\nEmpório da Música: {answer}\n")
        except Exception as exc:
            print(f"\nCould not reach the AI service ({type(exc).__name__}). Check your .env settings and connection.\n")


if __name__ == "__main__":
    main()
