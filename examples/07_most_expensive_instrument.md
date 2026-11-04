# 7. Most expensive instrument in the store

**Customer:** qual o instrumento mais caro da loja?

**Tools called:**
- `search_products({"only_available": true, "sort_by": "price", "sort_order": "desc", "limit": 1})`

**Assistant:**

O instrumento mais caro disponível na loja é o **Teclado Sintetizador Nord Synth 2 Pro**, da marca Nord, com preço de **R$ 19.567,00** e 3 unidades em estoque.

Se você estiver procurando por opções mais acessíveis ou por um instrumento de outra categoria, é só me dizer! Estou à disposição para ajudar.

**Observed behavior:** Uses the unified `search_products` tool with numeric price sorting in descending order and `limit=1`. No separate catalog-extremes tool is called.

*Live transcript from `nvidia/nemotron-3.5-lightning-30b-a3b` via NVIDIA NIM, 2026-11-04.*
