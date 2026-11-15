import csv
import reconciler as r


def row(i, amt=1000, cur="usd", ref=0):
    return {"id": i, "amount": amt, "currency": cur, "refunded": ref}


def test_clean_match():
    rep = r.reconcile([row("ch_1")], {"ch_1": row("ch_1")})
    assert (rep.matched, rep.problems) == (1, 0)


def test_missing_both_directions():
    rep = r.reconcile([row("ch_1")], {"ch_2": row("ch_2")})
    assert [x["id"] for x in rep.missing_in_ledger] == ["ch_1"]
    assert [x["id"] for x in rep.missing_in_stripe] == ["ch_2"]


def test_amount_currency_refund_mismatches():
    stripe_rows = [row("a", 1000), row("b", 1000, "eur"), row("c", 1000, ref=1000)]
    ledger = {"a": row("a", 900), "b": row("b", 1000, "usd"), "c": row("c", 1000, ref=0)}
    rep = r.reconcile(stripe_rows, ledger)
    assert len(rep.amount_mismatch) == 1
    assert len(rep.currency_mismatch) == 1
    assert len(rep.refund_mismatch) == 1


def test_load_ledger_normalizes(tmp_path):
    f = tmp_path / "l.csv"
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["charge_id", "amount", "currency"]); w.writerow([" ch_1 ", "500", "USD"])
    assert r.load_ledger(str(f))["ch_1"] == row("ch_1", 500, "usd", 0)


class FakeList:
    def __init__(self, items): self.items = items
    def auto_paging_iter(self): return iter(self.items)

class FakeClient:
    class Charge:
        @staticmethod
        def list(created, limit):
            return FakeList([
                {"id": "ch_ok", "status": "succeeded", "paid": True, "amount": 100, "currency": "USD", "amount_refunded": 20},
                {"id": "ch_failed", "status": "failed", "paid": False, "amount": 100, "currency": "usd", "amount_refunded": 0},
            ])

def test_fetch_filters_unpaid_and_normalizes():
    rows = r.fetch_stripe_charges(FakeClient, 0)
    assert rows == [{"id": "ch_ok", "amount": 100, "currency": "usd", "refunded": 20}]


def test_exit_code_on_problems(capsys):
    assert r.main(["--demo"]) == 1
    assert "MISSING IN LEDGER" in capsys.readouterr().out
