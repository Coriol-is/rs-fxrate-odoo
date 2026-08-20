# -*- coding: utf-8 -*-
"""Odoo integration tests for rs.fx.rate — sources are mocked, no network."""

from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.serbian_fx.models import fx_client

NBS_ROWS = [
    {"date": date(2026, 8, 19), "currency": "EUR", "unit": 1,
     "buy": 117.0073, "middle": 117.3594, "sell": 117.7115,
     "buy_cash": 116.5379, "sell_cash": 118.1809},
    {"date": date(2026, 8, 19), "currency": "JPY", "unit": 100,
     "buy": 63.3843, "middle": 63.575, "sell": 63.7657,
     "buy_cash": 0.0, "sell_cash": 0.0},
    {"date": date(2026, 8, 19), "currency": "XXX", "unit": 1,
     "buy": 0.0, "middle": 1.0, "sell": 0.0,
     "buy_cash": 0.0, "sell_cash": 0.0},
]
ALTA_ROWS = [
    {"date": date(2026, 8, 19), "currency": "EUR", "unit": 1,
     "buy": 115.1296, "middle": 117.3594, "sell": 119.5775,
     "buy_cash": 115.8924, "sell_cash": 118.8264},
]


class TestRsFxRate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rate = cls.env["rs.fx.rate"]
        cls.CurrencyRate = cls.env["res.currency.rate"]
        cls.icp = cls.env["ir.config_parameter"].sudo()
        cls.eur = cls.env.ref("base.EUR")
        cls.jpy = cls.env.ref("base.JPY")
        cls.rsd = cls.env.ref("base.RSD")
        (cls.eur | cls.jpy | cls.rsd).action_unarchive()
        cls.env.company.currency_id = cls.rsd

    def _fetch(self, rows=NBS_ROWS, fetcher="fetch_nbs_day"):
        with patch.object(fx_client, fetcher, return_value=list(rows)):
            return self.Rate._fetch_rates()

    def test_fetch_creates_rows_default_nbs(self):
        created = self._fetch()
        # XXX is not an Odoo currency and must be skipped
        self.assertEqual(created, 2)
        eur = self.Rate.search([("currency_id", "=", self.eur.id)])
        self.assertEqual(len(eur), 1)
        self.assertEqual(eur.source, "nbs")
        self.assertEqual(eur.middle, 117.3594)
        self.assertEqual(eur.buy, 117.0073)
        self.assertEqual(eur.date, date(2026, 8, 19))

    def test_currency_rate_written_with_parity(self):
        self._fetch()
        jpy_rate = self.CurrencyRate.search([
            ("currency_id", "=", self.jpy.id),
            ("name", "=", date(2026, 8, 19)),
            ("company_id", "=", False),
        ])
        self.assertEqual(len(jpy_rate), 1)
        # rate = unit / middle = 100 / 63.575
        self.assertAlmostEqual(jpy_rate.rate, 100 / 63.575, places=6)

    def test_upsert_idempotent(self):
        self.assertEqual(self._fetch(), 2)
        self.assertEqual(self._fetch(), 0)  # second run updates, creates none
        self.assertEqual(
            self.Rate.search_count([("currency_id", "=", self.eur.id)]), 1
        )

    def test_source_alta(self):
        self.icp.set_param("rs_fx.rate_source", "alta")
        created = self._fetch(rows=ALTA_ROWS, fetcher="fetch_alta_rates")
        self.assertEqual(created, 1)
        eur = self.Rate.search([("currency_id", "=", self.eur.id)])
        self.assertEqual(eur.source, "alta")
        self.assertEqual(eur.buy, 115.1296)

    def test_source_custom_requires_url(self):
        self.icp.set_param("rs_fx.rate_source", "custom")
        with self.assertRaises(UserError):
            self.Rate._fetch_rates()

    def test_source_custom(self):
        self.icp.set_param("rs_fx.rate_source", "custom")
        self.icp.set_param("rs_fx.custom_url", "https://example.com/rates")
        with patch.object(
            fx_client, "fetch_custom_rates", return_value=list(ALTA_ROWS)
        ) as mock_fetch:
            created = self.Rate._fetch_rates()
        mock_fetch.assert_called_once_with("https://example.com/rates")
        self.assertEqual(created, 1)
        eur = self.Rate.search([("currency_id", "=", self.eur.id)])
        self.assertEqual(eur.source, "custom")

    def test_update_currency_rates_disabled(self):
        self.icp.set_param("rs_fx.update_currency_rates", "0")
        self._fetch()
        self.assertFalse(self.CurrencyRate.search([
            ("currency_id", "=", self.eur.id),
            ("name", "=", date(2026, 8, 19)),
        ]))

    def test_non_rsd_company_skips_currency_rate(self):
        usd = self.env.ref("base.USD")
        usd.action_unarchive()
        self.env.company.currency_id = usd
        self._fetch()
        # rs.fx.rate rows are stored, res.currency.rate untouched
        self.assertTrue(self.Rate.search([("currency_id", "=", self.eur.id)]))
        self.assertFalse(self.CurrencyRate.search([
            ("currency_id", "=", self.eur.id),
            ("name", "=", date(2026, 8, 19)),
            ("company_id", "=", False),
        ]))

    def test_backfill_skips_existing_and_dedupes_weekends(self):
        # Friday list returned for Fri/Sat/Sun requests alike
        friday_rows = [dict(NBS_ROWS[0], date=date(2026, 8, 14))]
        with patch.object(
            fx_client, "fetch_nbs_day", return_value=friday_rows
        ), patch("time.sleep"):
            created = self.Rate._backfill_history(
                date(2026, 8, 14), date(2026, 8, 16)
            )
        self.assertEqual(created, 1)  # one list, not three
        row = self.Rate.search([("date", "=", date(2026, 8, 14))])
        self.assertEqual(row.source, "nbs")
        # second run: nothing new
        with patch.object(
            fx_client, "fetch_nbs_day", return_value=friday_rows
        ), patch("time.sleep"):
            self.assertEqual(
                self.Rate._backfill_history(
                    date(2026, 8, 14), date(2026, 8, 16)
                ),
                0,
            )
