# 1. Product search under R$1,000

**Customer:** Which acoustic or classical guitars do you have available for up to R$1,000?

**Tools called:**
- `search_products({"only_available": true, "max_price": 1000, "category": "acoustic guitars", "limit": 20, "query": "acoustic guitar"})`

**Assistant:**

Here are some acoustic‑ and classical‑guitar options we have in stock for **up to R$ 1 000,00**. All prices are the final price (no extra promotion applied unless noted).

| Model | Type | Price (BRL) | Stock |
|-------|------|-------------|-------|
| **Tagima Memphis AC‑39 Nylon Natural** | Classical (nylon strings) | R$ 429,90 | 15 units |
| **Rozini RC‑104 Nylon Estudante** | Classical (nylon strings) | R$ 459,90 | 10 units |
| **Shelby SN‑100 Folk Aço Preto** | Folk/steel‑string, black finish | R$ 549,00 | 5 units |
| **Giannini GF‑1R Aço Folk Sunburst** | Folk/steel‑string, sunburst | R$ 579,90 | 7 units |
| **Yamaha C40 Nylon Natural** | Classical (nylon strings) | R$ 599,90 | 12 units |

These guitars cover both nylon‑string (classical) and steel‑string (folk) styles, so you can choose the tone and feel that suits your playing. All are currently active and available for immediate pickup or delivery.

Would you like more details on any of these models (wood types, scale length, electronics, etc.), or are you looking for something in a different price range? I’m happy to help you find the right instrument!

**Observed behavior:** Product search with category inference and a maximum-price filter.

*Live transcript from `nvidia/nemotron-3.5-lightning-30b-a3b` via NVIDIA NIM, 2026-11-03.*
