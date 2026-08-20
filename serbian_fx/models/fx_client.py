# -*- coding: utf-8 -*-
"""Pure HTTP clients for Serbian exchange-rate sources.

Every fetcher returns a list of dicts with the same shape:

    {'date': date, 'currency': 'EUR', 'unit': 1,
     'buy': float, 'middle': float, 'sell': float,
     'buy_cash': float, 'sell_cash': float}

Sources:

  fetch_nbs_day(day)      official National Bank of Serbia list
                          (kurs.resenje.org mirror) — the default source.
  fetch_alta_rates()      Alta Banka commercial list scraped from
                          altabanka.rs (wpDataTables backend).
  fetch_custom_rates(url) any endpoint returning this module's own JSON
                          contract ({"rates": [...]}) — e.g. another Odoo
                          instance running this module, or a self-hosted
                          rate service.

Adding a bank = adding one fetch_<bank>_rates() here plus a selection entry
in fx_rate.py.

No Odoo imports, testable standalone:

    python3 -m serbian_fx.models.fx_client
"""

import re
from datetime import datetime

import requests

TIMEOUT = 30

# ---------------------------------------------------------------------------
# NBS — official list, via the public mirror kurs.resenje.org
# ---------------------------------------------------------------------------

NBS_DAY_URL = "https://kurs.resenje.org/api/v1/rates/%s"


def fetch_nbs_day(day, session=None):
    """Official NBS rates for one date.

    Buy/sell are the official NBS spreads; currencies quoted middle-only
    come back with zeros. 'date' is the list's validity start (date_from),
    so weekends resolve to the preceding published list and dedupe
    naturally.
    """
    session = session or requests.Session()
    response = session.get(NBS_DAY_URL % day.isoformat(), timeout=TIMEOUT)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    rates = []
    for row in response.json().get("rates", []):
        middle = row.get("exchange_middle")
        if not middle:
            continue
        rates.append({
            "date": datetime.strptime(row["date_from"], "%Y-%m-%d").date(),
            "currency": row["code"].strip().upper(),
            "unit": int(row.get("parity") or 1),
            "buy": float(row.get("exchange_buy") or 0),
            "middle": float(middle),
            "sell": float(row.get("exchange_sell") or 0),
            "buy_cash": float(row.get("cash_buy") or 0),
            "sell_cash": float(row.get("cash_sell") or 0),
        })
    return rates


# ---------------------------------------------------------------------------
# Alta Banka — commercial list scraped from altabanka.rs
# ---------------------------------------------------------------------------
# The rates page renders via wpDataTables in server-side mode: the page
# itself contains no data, only a per-day nonce. Flow:
#   1. GET the page, extract ``wdtNonceFrontendServerSide_1``.
#   2. POST a DataTables request (11 declared columns) with that nonce.
# The server applies its own filter and returns only the most recent list.

ALTA_PAGE_URL = "https://altabanka.rs/kursna-lista-2/"
ALTA_AJAX_URL = (
    "https://altabanka.rs/wp-admin/admin-ajax.php?action=get_wdtable&table_id=1"
)
ALTA_NONCE_RE = re.compile(r'wdtNonceFrontendServerSide_1"\s+value="([^"]+)"')
ALTA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OdooSerbianFX/1.0)",
    "Referer": ALTA_PAGE_URL,
    "X-Requested-With": "XMLHttpRequest",
}
# formula_1, DATUM, SIFVAL, OZNVAL, PARITET, IOTKHART, ISREDEN, IPRODHART,
# IOTKEFEKT, IPRODEFEKT — plus the hidden wdt_ID column the server expects.
ALTA_N_COLUMNS = 11


def parse_sr_number(value):
    """Parse a Serbian-formatted number: '1.234,5678' -> 1234.5678"""
    return float(value.strip().replace(".", "").replace(",", "."))


def _fetch_alta_nonce(session):
    response = session.get(ALTA_PAGE_URL, headers=ALTA_HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    match = ALTA_NONCE_RE.search(response.text)
    if not match:
        raise ValueError(
            "Alta Banka: wpDataTables nonce not found on %s" % ALTA_PAGE_URL
        )
    return match.group(1)


def fetch_alta_rates(session=None):
    """Latest Alta Banka kursna lista (commercial spreads)."""
    session = session or requests.Session()
    nonce = _fetch_alta_nonce(session)

    params = {
        "draw": "1",
        "start": "0",
        "length": "100",
        "wdtNonce": nonce,
        "search[value]": "",
        "search[regex]": "false",
        "order[0][column]": "1",
        "order[0][dir]": "desc",
    }
    for i in range(ALTA_N_COLUMNS):
        params["columns[%d][data]" % i] = str(i)
        params["columns[%d][name]" % i] = ""
        params["columns[%d][searchable]" % i] = "true"
        params["columns[%d][orderable]" % i] = "true"
        params["columns[%d][search][value]" % i] = ""
        params["columns[%d][search][regex]" % i] = "false"

    response = session.post(
        ALTA_AJAX_URL, data=params, headers=ALTA_HEADERS, timeout=TIMEOUT
    )
    response.raise_for_status()
    rows = response.json().get("data") or []
    if not rows:
        raise ValueError(
            "Alta Banka: empty rate table (nonce expired or layout changed)"
        )

    rates = []
    for row in rows:
        # [formula, DATUM, SIFVAL, OZNVAL, PARITET, buy, middle, sell,
        #  buy_cash, sell_cash]
        rates.append({
            "date": datetime.strptime(row[1], "%d/%m/%Y %H:%M").date(),
            "currency": row[3].strip().upper(),
            "unit": int(parse_sr_number(row[4])),
            "buy": parse_sr_number(row[5]),
            "middle": parse_sr_number(row[6]),
            "sell": parse_sr_number(row[7]),
            "buy_cash": parse_sr_number(row[8]),
            "sell_cash": parse_sr_number(row[9]),
        })

    # Guard against the server-side filter ever widening: keep only the
    # most recent date.
    latest = max(rate["date"] for rate in rates)
    return [rate for rate in rates if rate["date"] == latest]


# ---------------------------------------------------------------------------
# Custom endpoint — this module's own JSON contract
# ---------------------------------------------------------------------------

def fetch_custom_rates(url, session=None):
    """Rates from any endpoint speaking this module's JSON contract:

        {"rates": [{"date": "2026-08-19", "currency": "EUR", "unit": 1,
                    "buy": ..., "middle": ..., "sell": ...,
                    "buy_cash": ..., "sell_cash": ...}, ...]}

    Only 'date', 'currency' and 'middle' are required per row.
    """
    session = session or requests.Session()
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    rates = []
    for row in response.json().get("rates", []):
        if not row.get("middle"):
            continue
        rates.append({
            "date": datetime.strptime(row["date"], "%Y-%m-%d").date(),
            "currency": row["currency"].strip().upper(),
            "unit": int(row.get("unit") or 1),
            "buy": float(row.get("buy") or 0),
            "middle": float(row["middle"]),
            "sell": float(row.get("sell") or 0),
            "buy_cash": float(row.get("buy_cash") or 0),
            "sell_cash": float(row.get("sell_cash") or 0),
        })
    if not rates:
        raise ValueError("Custom rate endpoint returned no usable rates: %s" % url)
    return rates


if __name__ == "__main__":
    from datetime import date

    print("--- NBS (official, default) ---")
    for rate in fetch_nbs_day(date.today()):
        if rate["currency"] in ("EUR", "USD", "CHF", "JPY"):
            print(rate)
    print("--- Alta Banka ---")
    for rate in fetch_alta_rates():
        if rate["currency"] in ("EUR", "USD", "CHF", "JPY"):
            print(rate)
