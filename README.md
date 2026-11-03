# Empório da Música — AI Customer Service Agent

A Python customer-service agent for Empório da Música, a fictional musical instrument store in Campo Grande, Brazil. Built for the Artefact AI Engineer technical challenge.

Repository: https://github.com/gabirusky/teste-emporio-agent

The agent answers text messages, uses LLM function calling to query operational data, retrieves store policies from a PDF, and redirects requests that are outside the store's scope. The five interaction examples in `examples/` are real transcripts from the configured model.

## 1. What the agent does

- Answers customers in their language: pt-BR for Portuguese, English for English.
- Searches the product catalog by name, category, model, availability, and maximum price.
- Reports list price, final price, stock, and active promotions.
- Looks up demonstration orders by numeric ID, including items, tracking, and delivery estimate.
- Retrieves policy excerpts for hours, address, payments, installments, returns, exchanges, warranty, shipping, promotions, privacy, and store scope.
- Refuses accessory and unrelated requests, redirecting to supported topics.
- Keeps recent conversation context in memory for the current session.

## 2. Architecture

The design is hybrid: the LLM interprets the customer message, but business facts come from controlled Python tools.

```text
Customer message (CLI)
        |
        v
MusicStoreAgent + in-memory history
        |
        v
LLM with function-calling schemas
        |
        +--> search_products ----------> data/products.csv + promotions.csv + categories.csv
        +--> get_product_details ------> data/products.csv + promotions.csv
        +--> get_order_status ---------> data/orders.csv + order_items.csv
        +--> search_policies ----------> data/policies.pdf (section-aware lexical/fuzzy RAG)
        +--> redirect_out_of_scope ---> application policy
        |
        v
Grounded answer in the customer's language
```

### Why function calling

The model does not receive the full CSVs in the prompt. It selects a targeted Python tool, and the tool reads the authoritative source. This keeps prices, stock, and order facts anchored in the supplied data and reduces hallucination.

### Why retrieval (RAG)

Return, payment, warranty, and delivery rules live in an eight-page PDF. The agent retrieves only the relevant excerpts and preserves the source page number. Retrieval is section-aware: the PDF is split by numbered sections, with a fixed-size fallback. Ranking combines lexical overlap, RapidFuzz similarity, and intent-specific anchors. English queries are expanded to Portuguese terms because the official policy document is in Portuguese.

### Why hybrid instead of pure LLM or pure SQL

Commercial information requires precision. The LLM is good at understanding intent and writing the response; deterministic tools are better at filtering stock, applying active discounts, and finding policy passages. Keeping those responsibilities separate makes the system easier to test and audit.

## 3. Data handling

The project uses the files supplied for the challenge:

| File | Use |
|---|---|
| `data/products.csv` | Catalog, prices, stock, status, specifications |
| `data/orders.csv` | Order status, totals, payment, tracking, delivery estimate |
| `data/order_items.csv` | Line items shown in order lookups |
| `data/categories.csv` | Official category names |
| `data/promotions.csv` | Active promotions and discount percentages |
| `data/customers.csv` | Loaded and validated, but not used for identity verification |
| `data/policies.pdf` | Store policy manual |

Key rules:

- A product is available only when `status == active` and `stock_quantity > 0`.
- Only promotions with `is_active` truthy are applied. The highest active discount is used if a product appears more than once.
- The final price is the list price minus the active promotion. Promotions are not cumulative.
- Order lookups are demonstrations over static sample data. The dataset has no authentication, so the agent warns about this and avoids implying ownership.

## 4. Setup

Requirements: Python 3.10 or newer.

```bash
git clone https://github.com/gabirusky/teste-emporio-agent.git
cd teste-emporio-agent

python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

cp .env.example .env
# Edit .env with your provider credentials
```

### Provider configuration

The verified setup uses NVIDIA NIM:

```dotenv
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=your_nvidia_key_here
LLM_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
```

OpenRouter is also supported because the client uses the OpenAI-compatible API:

```dotenv
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=your_openrouter_key_here
LLM_MODEL=your_model_with_tool_calling_support
```

The model must support function calling. Never commit `.env` or an API key; `.gitignore` excludes `.env`.

### Run

```bash
python -m pytest -q
emporio-agent
```

CLI commands: `/reset` clears the session history; `/exit` (or `/quit`, `/sair`) ends the program.

You can also run the module directly:

```bash
PYTHONPATH=src python -m emporio_agent.cli
```

## 5. Interaction examples

Five real transcripts are in `examples/`:

1. [Product search under R$1,000](examples/01_product_search.md)
2. [Price of a specific model](examples/02_specific_price.md)
3. [Online return policy](examples/03_return_policy.md) — non-trivial policy case
4. [Order status](examples/04_order_status.md)
5. [Out-of-scope request](examples/05_out_of_scope.md)

Each file shows the customer message, the actual tool call, the assistant response, and the observed behavior.

## 6. Testing and validation

```bash
python -m pytest -q
```

Result: **19 passed**.

The tests cover:

- Availability filtering and maximum-price limits.
- Active promotions and effective prices.
- Zero-stock and discontinued products.
- Fuzzy product lookup.
- Order status, line items, and the authentication warning.
- Policy retrieval for returns, hours, and accessory scope.
- Written price limits such as “up to one thousand”.
- Out-of-scope redirection and unknown-tool errors.
- The agent tool loop, malformed tool arguments, provider failure, max tool rounds.
- Language directives, order-ownership sanitization, history window, and reset.

Live smoke test performed on 2026-11-03 with `nvidia/nemotron-3.5-lightning-30b-a3b` through NVIDIA NIM. All five scenarios returned grounded answers with the expected tool calls.

## 7. Known limitations

1. **Static data:** the CSVs are a snapshot, not a live ERP, inventory, or order system.
2. **No order authentication:** `customers.csv` exists, but there is no login, token, or identity challenge. Order details must not be exposed to unverified callers in production.
3. **Lexical RAG:** retrieval does not use embeddings or a vector database. It is effective for this short manual but may miss distant paraphrases.
4. **Promotion coverage:** only the `is_active` flag in `promotions.csv` is authoritative. Recurring campaigns described in the manual are not assumed to be active.
5. **Policy ambiguities:** the manual contains conflicting contact numbers and an email spelling variation. The agent should recommend confirmation instead of choosing one.
6. **In-memory history:** conversation state is lost when the process exits.
7. **No side effects:** the agent cannot place orders, reserve stock, process payments, cancel orders, or change customer records.
8. **Provider dependency:** tool calling depends on the selected model and endpoint. A model without reliable function calling needs to be replaced.

## 8. Future work

- Add authentication and authorization before exposing order data.
- Integrate live inventory, orders, and promotion services.
- Add a structured promotion calendar with start/end dates and eligibility rules.
- Evaluate retrieval with a labeled question set; add embeddings/reranking if needed.
- Add human handoff for complaints and ambiguous policy cases.
- Add structured logs for tool selection, latency, errors, and retrieval sources.
- Persist conversation state with retention and LGPD controls if the product requires it.

## 9. AI-assisted development workflow

This project was developed with **opencode** using the **DeepSeek V4.1 Flash** model as an AI coding assistant.

The assistant supported project structuring, Python implementation, debugging, test creation, documentation, and architectural decisions. All generated code and suggestions were reviewed, executed, and validated with the automated test suite and live provider calls. The final architecture, limitations, and results are documented here so they can be explained and defended independently.

## 10. Repository structure

```text
.
├── data/
│   ├── products.csv
│   ├── orders.csv
│   ├── order_items.csv
│   ├── categories.csv
│   ├── promotions.csv
│   ├── customers.csv
│   └── policies.pdf
├── examples/
├── src/emporio_agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── cli.py
│   ├── config.py
│   ├── data_store.py
│   ├── policy_retriever.py
│   └── tools.py
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## 11. Security notes

- Do not commit `.env` or API keys.
- Use only the fictional sample data during demonstrations.
- Do not use the order lookup for real customer data without authentication.
- Treat customer messages and retrieved document text as data, not instructions.
