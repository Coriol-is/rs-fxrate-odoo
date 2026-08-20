# -*- coding: utf-8 -*-
"""Pure unit tests for fx_client — no Odoo, no network.

Run standalone:  python3 serbian_fx/tests/test_fx_client.py
Run in Odoo:     odoo-bin --test-tags /serbian_fx ...
"""

import unittest
from datetime import date

try:
    from odoo.addons.serbian_fx.models import fx_client
except ImportError:  # standalone run without Odoo
    import pathlib
    import sys

    sys.path.insert(
        0, str(pathlib.Path(__file__).resolve().parent.parent / "models")
    )
    import fx_client


class FakeResponse:
    def __init__(self, json_data=None, text="", status_code=200):
        self._json = json_data
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise fx_client.requests.HTTPError("HTTP %s" % self.status_code)


class FakeSession:
    """Maps URL substrings to canned responses."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def _match(self, url):
        for fragment, response in self.responses.items():
            if fragment in url:
                return response
        raise AssertionError("unexpected URL: %s" % url)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return self._match(url)

    def post(self, url, data=None, **kwargs):
        self.calls.append(("POST", url, data))
        return self._match(url)


ALTA_PAGE = (
    '<input id="wdtNonceFrontendServerSide_1" '
    'name="wdtNonceFrontendServerSide_1" value="60bafcdba7">'
)
ALTA_DATA = {
    "data": [
        # stale date row — must be filtered out
        ["0,00", "18/08/2026 00:00", "978", "EUR", "1",
         "114,0000", "116,0000", "118,0000", "115,0000", "117,0000"],
        ["2.026,00", "19/08/2026 00:00", "978", "EUR", "1",
         "115,1296", "117,3594", "119,5775", "115,8924", "118,8264"],
        ["2.026,00", "19/08/2026 00:00", "392", "JPY", "100",
         "57,2175", "63,5750", "69,9325", "60,3963", "66,7538"],
    ]
}
NBS_DATA = {
    "rates": [
        {"code": "EUR", "date": "2026-08-19", "date_from": "2026-08-19",
         "parity": 1, "exchange_buy": 117.0073, "exchange_middle": 117.3594,
         "exchange_sell": 117.7115, "cash_buy": 116.5379,
         "cash_sell": 118.1809},
        # middle-only currency: spreads default to zero
        {"code": "ATS", "date": "2026-08-19", "date_from": "2026-08-19",
         "parity": 1, "exchange_middle": 8.5288},
        # no middle at all: skipped
        {"code": "XXX", "date": "2026-08-19", "date_from": "2026-08-19",
         "parity": 1},
    ]
}
CUSTOM_DATA = {
    "rates": [
        {"currency": "eur", "date": "2026-08-19", "unit": 1,
         "buy": 115.0, "middle": 117.3594, "sell": 119.0,
         "buy_cash": 115.5, "sell_cash": 118.5},
        {"currency": "CHF", "date": "2026-08-19", "middle": 124.82},
        {"currency": "BAD", "date": "2026-08-19"},  # no middle: skipped
    ]
}


class TestParseSrNumber(unittest.TestCase):
    def test_decimal_comma(self):
        self.assertEqual(fx_client.parse_sr_number("115,1296"), 115.1296)

    def test_thousands_dot(self):
        self.assertEqual(fx_client.parse_sr_number("1.234,5678"), 1234.5678)

    def test_formula_style(self):
        self.assertEqual(fx_client.parse_sr_number("2.026,00"), 2026.0)


class TestFetchAltaRates(unittest.TestCase):
    def _session(self, data=ALTA_DATA):
        return FakeSession({
            "kursna-lista-2": FakeResponse(text=ALTA_PAGE),
            "admin-ajax.php": FakeResponse(json_data=data),
        })

    def test_parses_and_keeps_latest_date_only(self):
        rates = fx_client.fetch_alta_rates(session=self._session())
        self.assertEqual(len(rates), 2)  # stale 18/08 row dropped
        eur = next(r for r in rates if r["currency"] == "EUR")
        self.assertEqual(eur["date"], date(2026, 8, 19))
        self.assertEqual(eur["buy"], 115.1296)
        self.assertEqual(eur["middle"], 117.3594)
        self.assertEqual(eur["sell"], 119.5775)
        self.assertEqual(eur["buy_cash"], 115.8924)
        self.assertEqual(eur["sell_cash"], 118.8264)

    def test_parity(self):
        rates = fx_client.fetch_alta_rates(session=self._session())
        jpy = next(r for r in rates if r["currency"] == "JPY")
        self.assertEqual(jpy["unit"], 100)

    def test_nonce_sent(self):
        session = self._session()
        fx_client.fetch_alta_rates(session=session)
        post = next(c for c in session.calls if c[0] == "POST")
        self.assertEqual(post[2]["wdtNonce"], "60bafcdba7")

    def test_empty_data_raises(self):
        with self.assertRaises(ValueError):
            fx_client.fetch_alta_rates(session=self._session({"data": []}))

    def test_missing_nonce_raises(self):
        session = FakeSession({"kursna-lista-2": FakeResponse(text="<html/>")})
        with self.assertRaises(ValueError):
            fx_client.fetch_alta_rates(session=session)


class TestFetchNbsDay(unittest.TestCase):
    def test_parses_full_row(self):
        session = FakeSession({"kurs.resenje.org": FakeResponse(json_data=NBS_DATA)})
        rates = fx_client.fetch_nbs_day(date(2026, 8, 19), session=session)
        eur = next(r for r in rates if r["currency"] == "EUR")
        self.assertEqual(eur["buy"], 117.0073)
        self.assertEqual(eur["middle"], 117.3594)
        self.assertEqual(eur["sell"], 117.7115)
        self.assertEqual(eur["buy_cash"], 116.5379)
        self.assertEqual(eur["sell_cash"], 118.1809)

    def test_middle_only_zero_spreads(self):
        session = FakeSession({"kurs.resenje.org": FakeResponse(json_data=NBS_DATA)})
        rates = fx_client.fetch_nbs_day(date(2026, 8, 19), session=session)
        ats = next(r for r in rates if r["currency"] == "ATS")
        self.assertEqual(ats["middle"], 8.5288)
        self.assertEqual(ats["buy"], 0.0)
        self.assertEqual(ats["sell_cash"], 0.0)

    def test_no_middle_skipped(self):
        session = FakeSession({"kurs.resenje.org": FakeResponse(json_data=NBS_DATA)})
        rates = fx_client.fetch_nbs_day(date(2026, 8, 19), session=session)
        self.assertNotIn("XXX", [r["currency"] for r in rates])

    def test_404_returns_empty(self):
        session = FakeSession(
            {"kurs.resenje.org": FakeResponse(status_code=404)}
        )
        self.assertEqual(
            fx_client.fetch_nbs_day(date(2026, 8, 19), session=session), []
        )


class TestFetchCustomRates(unittest.TestCase):
    def test_contract(self):
        session = FakeSession({"example.com": FakeResponse(json_data=CUSTOM_DATA)})
        rates = fx_client.fetch_custom_rates(
            "https://example.com/rates", session=session
        )
        self.assertEqual(len(rates), 2)  # BAD row skipped
        eur = next(r for r in rates if r["currency"] == "EUR")  # upcased
        self.assertEqual(eur["date"], date(2026, 8, 19))
        self.assertEqual(eur["middle"], 117.3594)
        chf = next(r for r in rates if r["currency"] == "CHF")
        self.assertEqual(chf["unit"], 1)  # defaults
        self.assertEqual(chf["buy"], 0.0)

    def test_empty_raises(self):
        session = FakeSession(
            {"example.com": FakeResponse(json_data={"rates": []})}
        )
        with self.assertRaises(ValueError):
            fx_client.fetch_custom_rates(
                "https://example.com/rates", session=session
            )


if __name__ == "__main__":
    unittest.main()
