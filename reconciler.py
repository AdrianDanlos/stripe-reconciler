"""Stripe reconciliation: compare Stripe charges against your own ledger (CSV)
and report what is missing, mismatched or refunded differently.

Amounts are integers in the currency's minor unit (cents), as Stripe returns them.
Exit code is 1 when mismatches exist, so it can run from cron or CI and alert.
"""
import argparse, csv, os, sys, time
from dataclasses import dataclass, field


@dataclass
class Report:
    checked: int = 0
    matched: int = 0
    missing_in_ledger: list = field(default_factory=list)   # paid in Stripe, not recorded
    missing_in_stripe: list = field(default_factory=list)   # recorded, no such Stripe charge
    amount_mismatch: list = field(default_factory=list)
    currency_mismatch: list = field(default_factory=list)
    refund_mismatch: list = field(default_factory=list)

    @property
    def problems(self) -> int:
        return (len(self.missing_in_ledger) + len(self.missing_in_stripe) + len(self.amount_mismatch)
                + len(self.currency_mismatch) + len(self.refund_mismatch))


def fetch_stripe_charges(client, since_ts: int):
    """Return succeeded charges created since since_ts. `client` is the stripe module
    (or any object exposing Charge.list), which keeps this testable without network."""
    rows = []
    for ch in client.Charge.list(created={"gte": since_ts}, limit=100).auto_paging_iter():
        if ch["status"] != "succeeded" or not ch["paid"]:
            continue
        rows.append({"id": ch["id"], "amount": int(ch["amount"]), "currency": ch["currency"].lower(),
                     "refunded": int(ch.get("amount_refunded") or 0)})
    return rows


def load_ledger(path: str):
    with open(path, newline="") as f:
        out = {}
        for r in csv.DictReader(f):
            out[r["charge_id"].strip()] = {
                "id": r["charge_id"].strip(), "amount": int(r["amount"]),
                "currency": r["currency"].strip().lower(), "refunded": int(r.get("refunded") or 0)}
        return out


def reconcile(stripe_rows, ledger: dict) -> Report:
    rep = Report()
    seen = set()
    for s in stripe_rows:
        rep.checked += 1
        seen.add(s["id"])
        l = ledger.get(s["id"])
        if l is None:
            rep.missing_in_ledger.append(s)
            continue
        bad = False
        if l["currency"] != s["currency"]:
            rep.currency_mismatch.append((s, l)); bad = True
        elif l["amount"] != s["amount"]:
            rep.amount_mismatch.append((s, l)); bad = True
        if l["refunded"] != s["refunded"]:
            rep.refund_mismatch.append((s, l)); bad = True
        if not bad:
            rep.matched += 1
    for cid, l in ledger.items():
        if cid not in seen:
            rep.missing_in_stripe.append(l)
    return rep


def money(minor: int, cur: str) -> str:
    return f"{minor / 100:,.2f} {cur.upper()}"


def format_report(rep: Report) -> str:
    lines = [f"Checked {rep.checked} Stripe charges: {rep.matched} matched, {rep.problems} problem(s)."]
    for s in rep.missing_in_ledger:
        lines.append(f"  MISSING IN LEDGER   {s['id']}  {money(s['amount'], s['currency'])}  (paid in Stripe, not recorded)")
    for l in rep.missing_in_stripe:
        lines.append(f"  MISSING IN STRIPE   {l['id']}  {money(l['amount'], l['currency'])}  (in ledger, no matching charge)")
    for s, l in rep.amount_mismatch:
        lines.append(f"  AMOUNT MISMATCH     {s['id']}  stripe {money(s['amount'], s['currency'])} vs ledger {money(l['amount'], l['currency'])}")
    for s, l in rep.currency_mismatch:
        lines.append(f"  CURRENCY MISMATCH   {s['id']}  stripe {s['currency'].upper()} vs ledger {l['currency'].upper()}")
    for s, l in rep.refund_mismatch:
        lines.append(f"  REFUND MISMATCH     {s['id']}  stripe refunded {money(s['refunded'], s['currency'])} vs ledger {money(l['refunded'], l['currency'])}")
    return "\n".join(lines)


def demo_data():
    stripe_rows = [
        {"id": "ch_001", "amount": 4900, "currency": "usd", "refunded": 0},
        {"id": "ch_002", "amount": 12000, "currency": "usd", "refunded": 0},
        {"id": "ch_003", "amount": 2500, "currency": "eur", "refunded": 2500},
        {"id": "ch_004", "amount": 7900, "currency": "usd", "refunded": 0},
    ]
    ledger = {
        "ch_001": {"id": "ch_001", "amount": 4900, "currency": "usd", "refunded": 0},
        "ch_002": {"id": "ch_002", "amount": 11000, "currency": "usd", "refunded": 0},
        "ch_003": {"id": "ch_003", "amount": 2500, "currency": "eur", "refunded": 0},
        "ch_999": {"id": "ch_999", "amount": 3000, "currency": "usd", "refunded": 0},
    }
    return stripe_rows, ledger


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Reconcile Stripe charges against a ledger CSV")
    p.add_argument("--ledger", help="CSV with columns: charge_id,amount,currency[,refunded]")
    p.add_argument("--days", type=int, default=30, help="look back this many days")
    p.add_argument("--demo", action="store_true", help="run on built-in sample data, no API key needed")
    a = p.parse_args(argv)
    if a.demo:
        stripe_rows, ledger = demo_data()
    else:
        import stripe
        key = os.getenv("STRIPE_API_KEY")
        if not key or not a.ledger:
            p.error("set STRIPE_API_KEY and pass --ledger (or use --demo)")
        stripe.api_key = key
        stripe_rows = fetch_stripe_charges(stripe, int(time.time()) - a.days * 86400)
        ledger = load_ledger(a.ledger)
    rep = reconcile(stripe_rows, ledger)
    print(format_report(rep))
    return 1 if rep.problems else 0


if __name__ == "__main__":
    sys.exit(main())
