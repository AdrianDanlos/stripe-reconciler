# stripe-reconciler

A small Python CLI that finds payments that are out of sync between Stripe and your own records.

Typical causes: a missed webhook, a failed database write, a manual refund nobody recorded, or a
wrong amount written by a buggy integration. This tool lists them so they get fixed before month-end.

## What it checks
- **Missing in ledger:** paid in Stripe, never recorded on your side
- **Missing in Stripe:** recorded on your side, no matching charge
- **Amount and currency mismatches**
- **Refund mismatches:** refunded in Stripe, not in your records

Exit code is `1` when problems are found, so it works in cron or CI and can trigger an alert.

## Try it (no API key needed)
    pip install -r requirements.txt
    python reconciler.py --demo

## Run on real data
    export STRIPE_API_KEY=sk_test_...
    python reconciler.py --ledger sample/ledger.csv --days 30

Ledger CSV columns: `charge_id,amount,currency[,refunded]` (amounts in cents).

## Test
    pytest -q     # 6 tests, no network needed (Stripe client is injected and faked)

## Demo output
```
Checked 4 Stripe charges: 1 matched, 4 problem(s).
  MISSING IN LEDGER   ch_004  79.00 USD  (paid in Stripe, not recorded)
  MISSING IN STRIPE   ch_999  30.00 USD  (in ledger, no matching charge)
  AMOUNT MISMATCH     ch_002  stripe 120.00 USD vs ledger 110.00 USD
  REFUND MISMATCH     ch_003  stripe refunded 25.00 EUR vs ledger 0.00 EUR
```

## Adapt
Swap `load_ledger` for your database, accounting export (Xero, QuickBooks) or CRM, keep `reconcile` as is.
