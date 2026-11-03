# 4. Order status

**Customer:** What is the status of order number 8?

**Tools called:**
- `get_order_status({"order_id": 8})`

**Assistant:**

Order #8 in the demonstration dataset is **shipped**.

- **Order date:** 15 Feb 2026  
- **Total:** R$ 349,90  
- **Payment method:** debit  
- **Items:** 1 × Kala KA‑C Concert Mogno  
- **Tracking code:** BRJL5544332BR  
- **Estimated delivery:** 28 Feb 2026  

*Note: This is demonstration data only. The system has no customer authentication, so order details cannot be verified against a real customer record.*

Is there anything else I can help you with—perhaps checking another order, browsing instruments, or learning about our delivery policies?

**Observed behavior:** Order lookup with items, tracking, delivery estimate, and the authentication warning.

*Live transcript from `nvidia/nemotron-3.5-lightning-30b-a3b` via NVIDIA NIM, 2026-11-03.*
