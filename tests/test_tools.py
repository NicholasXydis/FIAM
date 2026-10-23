# The data tools on tiny inputs: SEC links, spending guards, extracts.

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools" / "data"
sys.path.insert(0, str(TOOLS))


# Loads one data tool as a module without running its command line.
def tool(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Both SEC folders are found, other zips and duplicates are not.
def test_13f_links_cover_both_folders_and_nothing_else():
    page = (
        '<a href="/files/structureddata/data/form-13f-data-sets/2013q2_form13f.zip">'
        '<a href="/files/datastandardsinnovation/data/x/01jun2026-31aug2026_form13f.zip">'
        '<a href="/files/structureddata/data/form-13f-data-sets/2013q2_form13f.zip">'
        '<a href="/files/other/readme.zip">'
    )
    links = tool("edgar").listed(page)
    assert [link.rsplit("/", 1)[1] for link in links] == [
        "01jun2026-31aug2026_form13f.zip",
        "2013q2_form13f.zip",
    ]


# Only a real positive number is a price; 0.0 means it cannot be filled.
@pytest.mark.parametrize(
    "price, ok",
    [(4.99, True), (0.01, True), (0, False), (0.0, False)]
    + [(None, False), ("4.99", False), (-1, False), (True, False)],
)
def test_only_a_positive_quote_is_a_price(price, ok):
    assert tool("carbon_arc").priced(price) is ok


# Framework ids are found at any depth, and rows in either reply shape.
def test_order_ids_and_row_counts_are_read_from_any_shape():
    ca = tool("carbon_arc")
    order = {"order": {"frameworks": [{"framework_id": "f1", "price": 0}]}}
    assert ca.find(order, "framework_id") == ["f1"]
    reply = {"order_id": "o1", "frameworks": ["2849de38"], "total_price": 4.99}
    assert ca.bought(reply) == ["2849de38"]
    assert ca.bought(order) == ["f1"]
    assert ca.rows({"data": [{"a": 1}, {"a": 2}]}) == 2
    assert ca.rows({"data": {"date": ["d1", "d2", "d3"], "value": [1, 2, 3]}}) == 3
    assert ca.rows({"data": []}) == 0


# A stand-in for the SDK explorer: card panel filters and fixed prices.
class Explorer:
    def __init__(self, prices=None):
        self.prices, self.orders = prices or {}, []

    def build_framework(self, entities, insight, filters, aggregate=None):
        base = {"entities": entities, "insight": {"insight_id": insight}}
        return base | {"filters": filters, "aggregate": aggregate}

    def collect_framework_filters(self, framework):
        span = {"start_date": "2021-10-19T00:00:00Z", "end_date": "2026-10-18T00:00:00Z"}
        return {
            "filters": [
                {"key": "date_resolution", "select_type": "single-selection",
                 "default_value": "day", "option_values": [{"key": "day"}, {"key": "month"}]},
                {"key": "location_resolution", "select_type": "single-selection",
                 "default_value": "state", "option_values": [{"key": "us"}, {"key": "state"}]},
                {"key": "date_range", "select_type": "date-range", "default_value": span,
                 "table_earliest_date": "2019-01-01T00:00:00Z",
                 "table_latest_date": "2026-10-18T00:00:00Z"},
                {"key": "transaction_method", "select_type": "multi-selection",
                 "default_value": None, "option_values": [{"key": "Online"}]},
            ]
        }  # fmt: skip

    def check_framework_price(self, framework):
        return self.prices.get(framework["insight"]["insight_id"], 0.0)

    def buy_frameworks(self, order):
        self.orders.append(order)
        self.wallet.spend(self.prices[order[0]["insight"]["insight_id"]])
        return {"order_id": "o", "frameworks": [f"f{len(self.orders)}"]}

    def get_framework_data(self, fid, fetch_all=True):
        return {"data": [{"date": "2026-01-01", "value": 1}]}

    def get_framework_metadata(self, fid):
        return {"id": fid}


# A stand-in wallet whose balance falls by whatever is bought.
class Wallet:
    def __init__(self, balance):
        self.balance = balance

    def spend(self, amount):
        self.balance = round(self.balance - amount, 6)

    def get_balance(self):
        return {"total_balance": self.balance}

    def get_order_history(self):
        return {"total": 0}


# A stand-in client joining the fake explorer and wallet.
class Client:
    def __init__(self, prices, balance=480.04):
        self.explorer, self.client = Explorer(prices), Wallet(balance)
        self.explorer.wallet = self.client


# A plan's printed cap rounds up, so its own sum never trips the guard.
def test_cents_round_up_so_the_printed_cap_covers_the_sum():
    ca = tool("carbon_arc")
    assert ca.cents(79.710033) == 79.72 and ca.cents(79.71) == 79.71
    assert ca.cents(8.721840600973284 + 4.99 + 4.99) == 18.71


# Named tickers, monthly, US, full history and the asked aggregate.
def test_request_names_tickers_month_full_history_and_aggregate(monkeypatch):
    ca = tool("carbon_arc")
    monkeypatch.setattr(ca, "tickers", lambda names: [{"carc_id": 729, "representation": "ticker"}])
    item = {"tickers": ["WMT"], "insight": 626, "aggregate": "sum"}
    built = ca.request(Explorer(), item)
    assert built["filters"]["date_resolution"] == "month"
    assert built["filters"]["location_resolution"] == "us"
    assert built["filters"]["date_range"] == {"start_date": "2019-01-01", "end_date": "2026-10-18"}
    assert "transaction_method" not in built["filters"] and built["aggregate"] == "sum"


# A plan over the cap, or a quote that rose since, buys nothing.
def test_buy_refuses_a_plan_over_cap_and_a_risen_quote(tmp_path, monkeypatch):
    ca = tool("carbon_arc")
    monkeypatch.setattr(ca, "SNAPSHOTS", tmp_path)
    framework = {"insight": {"insight_id": 626}}
    plan = tmp_path / "p.plan.json"
    items = [{"name": "card_WMT", "framework": framework, "price": 8.72}]
    plan.write_text(json.dumps({"snapshot": "s1", "items": items}))
    rich = Client({626: 8.72})
    assert ca.buy(str(plan), 5.0, rich) == 1 and rich.explorer.orders == []
    risen = Client({626: 9.50})
    assert ca.buy(str(plan), 20.0, risen) == 1 and risen.explorer.orders == []
    assert risen.client.balance == 480.04


# Within the cap each item is bought once, saved, then skipped.
def test_buy_saves_each_item_once_within_the_cap(tmp_path, monkeypatch):
    ca = tool("carbon_arc")
    monkeypatch.setattr(ca, "SNAPSHOTS", tmp_path)
    monkeypatch.setattr(ca.time, "sleep", lambda s: None)
    items = [
        {"name": "card_WMT", "framework": {"insight": {"insight_id": 626}}, "price": 8.72},
        {"name": "foot_WMT", "framework": {"insight": {"insight_id": 45862}}, "price": 4.99},
        {"name": "empty", "framework": {"insight": {"insight_id": 503}}, "price": 0.0},
    ]
    plan = tmp_path / "p.plan.json"
    plan.write_text(json.dumps({"snapshot": "s1", "items": items}))
    client = Client({626: 8.72, 45862: 4.99})
    assert ca.buy(str(plan), 13.71, client) == 0
    assert len(client.explorer.orders) == 2 and client.client.balance == 466.33
    receipt = json.loads((tmp_path / "s1" / "card_WMT.receipt.json").read_text())
    assert receipt["rows"] == 1 and receipt["framework_id"] == "f1"
    assert ca.buy(str(plan), 13.71, client) == 0 and len(client.explorer.orders) == 2
    assert ca.buy(str(plan), 0.0, client) == 0 and len(client.explorer.orders) == 2


# Events keep our gvkeys only, drop snapshot fields and leave a receipt.
def test_events_extract_filters_gvkeys_and_drops_snapshots(tmp_path, monkeypatch):
    sd = tool("stock_data")
    rows = pd.DataFrame(
        {
            "gvkey": ["1004", "999999", None],
            "headline": ["a", "b", "c"],
            "companyname": ["Now Inc"] * 3,
            "lastmodifieddate": ["2025-01-01"] * 3,
            "entereddateutc": ["2015-01-02 10:00:00"] * 3,
        }
    )
    rows.to_csv(tmp_path / "events_global.csv", index=False)
    monkeypatch.setattr(sd, "stock_data", lambda: tmp_path)
    monkeypatch.setattr(sd, "our_gvkeys", lambda: {"001004"})
    monkeypatch.setattr(sd, "OUT", tmp_path / "out")
    assert sd.events() == 0
    kept = pd.read_parquet(tmp_path / "out" / "events.parquet")
    assert kept["gvkey"].tolist() == ["001004"]
    assert not {"companyname", "lastmodifieddate"} & set(kept.columns)
    receipt = json.loads((tmp_path / "out" / "receipts.json").read_text())["events"]
    assert receipt["rows_in"] == 3 and receipt["rows_out"] == 1


# Amazon item rows never keep fields computed at the 2023 snapshot.
def test_amazon_items_keep_no_snapshot_fields():
    columns = tool("amazon").ITEM_COLUMNS
    assert set(columns) == {"parent_asin", "store", "main_category"}
    assert not {"average_rating", "rating_number", "price"} & set(columns)


# --into is taken out of the arguments and becomes the data root.
def test_into_moves_the_data_root_and_leaves_the_verbs():
    shared = tool("_shared")
    argv = ["noaa.py", "climdiv", "--into", "/tmp/x"]
    assert shared.data_root(argv) == Path("/tmp/x").resolve() and argv == ["noaa.py", "climdiv"]
    assert shared.data_root(["noaa.py"]) == ROOT / "data"


# The archive comes from the setting, else the first place found.
def test_stock_data_found_from_setting_or_usual_places(tmp_path, monkeypatch):
    shared = tool("_shared")
    there = tmp_path / "Stock Data"
    there.mkdir()
    monkeypatch.setattr(shared, "STOCK_DATA_PLACES", (tmp_path / "absent", there))
    monkeypatch.setattr(shared, "setting", lambda name, default="": "")
    assert shared.stock_data() == there
    monkeypatch.setattr(shared, "setting", lambda name, default="": "/elsewhere")
    assert shared.stock_data() == Path("/elsewhere")


# A changed or missing file is caught; an untouched one passes.
def test_check_catches_a_changed_or_missing_file(tmp_path):
    shared = tool("_shared")
    (tmp_path / "a.txt").write_text("alpha")
    (tmp_path / "b.txt").write_text("beta")
    digests = {n: shared.fingerprint(tmp_path / n) for n in ("a.txt", "b.txt")}
    (tmp_path / "b.txt").write_text("tampered")
    assert shared.check(tmp_path, digests | {"c.txt": "0" * 64}) == ["b.txt", "c.txt"]


# The bulk file stays home, receipts are never compared, data files are.
def test_usb_split_and_rebuild_bookkeeping():
    status = tool("status")
    assert status.stays_home("edgar/submissions.zip") and status.stays_home("amazon/raw")
    assert not status.stays_home("edgar/docs/1750/x.gz")
    assert not status.stays_home("edgar/13f/2013q2_form13f.zip")
    assert status.bookkeeping("climdiv/receipts.json") and status.bookkeeping("x.receipt.json")
    assert not status.bookkeeping("v4/extracts/events.parquet")


# Every data tool run.py names exists in tools/data.
def test_every_data_tool_exists():
    spec = importlib.util.spec_from_file_location("run_main", ROOT / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    assert all((TOOLS / script).exists() for script, _, _ in run.DATA_TOOLS.values())


# Run-time code reads only data/; the two bundle builders take a folder.
def test_run_time_code_never_names_the_raw_archive():
    builders = {"fiam/build_data.py", "fiam/wrds.py"}
    banned = ("Stock Data", "FIAM_STOCK_DATA", "@Apps", "E:/", "E:\\")
    for path in [*sorted((ROOT / "fiam").rglob("*.py")), ROOT / "run.py"]:
        name = path.relative_to(ROOT).as_posix()
        if name not in builders:
            text = path.read_text(encoding="utf-8")
            assert not [b for b in banned if b in text], name


# Compacting keeps every value and the same bytes from any row groups.
def test_compact_keeps_values_whatever_the_row_groups(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    stock = tool("stock_data")
    monkeypatch.setattr(stock, "GROUP", 7)
    table = pa.table({"k": [str(i) for i in range(30)], "v": [i / 3 for i in range(30)]})
    small, whole = tmp_path / "small.parquet", tmp_path / "whole.parquet"
    pq.write_table(table, small, row_group_size=4, compression="zstd")
    pq.write_table(table, whole, compression="zstd")
    stock.compact(small)
    stock.compact(whole)
    assert pq.read_table(small).equals(table)
    assert small.read_bytes() == whole.read_bytes()
    assert pq.ParquetFile(small).metadata.num_row_groups == 5


# Without the CRSP daily extract, replays are N/A and say so.
def test_stress_replays_are_missing_not_guessed(tmp_path, monkeypatch, capsys):
    from fiam.exhibits import stress

    monkeypatch.setattr(stress, "CACHE", tmp_path / "none.parquet")
    monkeypatch.setattr(stress, "DAILY", tmp_path / "crsp_daily")
    assert stress.episode_returns() is None
    assert "replays are N/A" in capsys.readouterr().err


# A month keeps the description in force on its date, never a later one.
def test_dedupe_keeps_the_description_known_on_the_date(tmp_path):
    stock = tool("stock_data")
    rows = [
        ("1", "2003-10-31", "2001-10-01", "OLD"),
        ("1", "2003-10-31", "2003-11-01", "NEW"),
        ("1", "2003-10-31", "2003-11-01", "NEW"),
        ("2", "2004-05-28", "2004-05-29", "LATER"),
        ("2", "2004-05-28", "2004-06-02", "LATEST"),
    ]
    path = tmp_path / "m.parquet"
    pd.DataFrame(rows, columns=["PERMNO", "MthCalDt", "SecInfoStartDt", "Ticker"]).to_parquet(path)
    assert stock.dedupe(path, ["PERMNO", "MthCalDt"], "SecInfoStartDt") == 3
    kept = pd.read_parquet(path).set_index("PERMNO")["Ticker"].to_dict()
    assert kept == {"1": "OLD", "2": "LATER"}


# The audit records each result and finds 13F members in any layout.
def test_audit_records_results_and_finds_members(tmp_path):
    spec = importlib.util.spec_from_file_location("audit", ROOT / "tools" / "audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    audit.zero(0, "s", "clean", "fail", "fix")
    audit.zero(3, "s", "dirty", "warn", "fix", 10)
    assert [f["level"] for f in audit.FINDINGS] == ["pass", "warn"]
    assert audit.FINDINGS[1]["evidence"] == "3 of 10 rows"
    path = tmp_path / "q.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("2013q2_form13f/SUBMISSION.tsv", "x")
    with zipfile.ZipFile(path) as zf:
        assert audit.member(zf, "SUBMISSION.TSV") == "2013q2_form13f/SUBMISSION.tsv"
