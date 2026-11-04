# 8. Cheapest Yamaha model

**Customer:** qual modelo YAMAHA é o mais barato?

**Tools called:**
- `search_products({"brand": "Yamaha", "only_available": true, "sort_by": "price", "sort_order": "asc", "limit": 1})`

**Assistant:**

O modelo Yamaha mais barato disponível é o **Yamaha C40 Nylon Natural**, com preço de **R$ 599,90** e 12 unidades em estoque.

Precisa de mais informações sobre esse violão clássico ou gostaria de ver outras opções Yamaha? Estou à disposição!

**Observed behavior:** Normalizes uppercase `YAMAHA` to the exact brand filter `Yamaha`, combines it with availability and ascending numeric price sorting, and returns only a Yamaha product.

*Live transcript from `nvidia/nemotron-3.5-lightning-30b-a3b` via NVIDIA NIM, 2026-11-04.*
