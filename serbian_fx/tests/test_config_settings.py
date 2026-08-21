# -*- coding: utf-8 -*-
"""The settings page must round-trip to the same rs_fx.* parameters the
fetching code reads — especially the boolean, which Odoo would otherwise
delete when unchecked."""

from odoo.tests.common import TransactionCase


class TestRsFxSettings(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Settings = cls.env["res.config.settings"]
        cls.icp = cls.env["ir.config_parameter"].sudo()

    def _apply(self, **values):
        settings = self.Settings.create(values)
        settings.execute()
        return settings

    def test_defaults_installed(self):
        self.assertEqual(self.icp.get_param("rs_fx.rate_source"), "nbs")
        self.assertEqual(
            self.icp.get_param("rs_fx.update_currency_rates"), "1"
        )

    def test_source_and_url_saved(self):
        self._apply(
            rs_fx_rate_source="custom",
            rs_fx_custom_url="https://example.com/rates.json",
        )
        self.assertEqual(self.icp.get_param("rs_fx.rate_source"), "custom")
        self.assertEqual(
            self.icp.get_param("rs_fx.custom_url"),
            "https://example.com/rates.json",
        )

    def test_currency_rate_toggle_off_is_stored_not_deleted(self):
        self._apply(rs_fx_update_currency_rates=False)
        # A plain config_parameter boolean would unlink the row here, and
        # _update_currency_rate reads a missing value as enabled.
        self.assertEqual(
            self.icp.get_param("rs_fx.update_currency_rates"), "0"
        )
        self.assertFalse(
            self.Settings.default_get(["rs_fx_update_currency_rates"]).get(
                "rs_fx_update_currency_rates"
            )
        )

    def test_currency_rate_toggle_back_on(self):
        self._apply(rs_fx_update_currency_rates=False)
        self._apply(rs_fx_update_currency_rates=True)
        self.assertEqual(
            self.icp.get_param("rs_fx.update_currency_rates"), "1"
        )
        self.assertTrue(
            self.Settings.default_get(["rs_fx_update_currency_rates"]).get(
                "rs_fx_update_currency_rates"
            )
        )

    def test_ecb_url_saved_and_cleared(self):
        self._apply(rs_fx_ecb_url="https://example.com/eurofxref-daily.xml")
        self.assertEqual(
            self.icp.get_param("rs_fx.ecb_url"),
            "https://example.com/eurofxref-daily.xml",
        )
        self._apply(rs_fx_ecb_url=False)
        self.assertFalse(self.icp.get_param("rs_fx.ecb_url"))
