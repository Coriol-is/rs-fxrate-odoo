# -*- coding: utf-8 -*-
"""Accounting settings page for the system parameters this module reads.

Everything here is stored in ir.config_parameter — the settings form is a
friendly front end for the same rs_fx.* keys, so instances that were
configured by hand keep working untouched.
"""

from odoo import api, fields, models

from .fx_rate import SOURCES

# Kept out of config_parameter on purpose: an unchecked boolean makes Odoo
# delete the parameter, and a missing rs_fx.update_currency_rates means
# "enabled" for every install that predates this settings page. So the
# value is read and written explicitly below, always as "1" or "0".
UPDATE_RATES_PARAM = "rs_fx.update_currency_rates"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    rs_fx_rate_source = fields.Selection(
        SOURCES,
        string="Rate source",
        default="nbs",
        config_parameter="rs_fx.rate_source",
        help="Where the daily rate list is fetched from.",
    )
    rs_fx_custom_url = fields.Char(
        string="Custom endpoint URL",
        config_parameter="rs_fx.custom_url",
        help="JSON endpoint used when the rate source is 'Custom endpoint'.",
    )
    rs_fx_update_currency_rates = fields.Boolean(
        string="Update Odoo currency rates",
        default=True,
        help="Write the middle rate into the standard res.currency.rate "
             "table. Requires the company currency to be RSD.",
    )
    rs_fx_ecb_url = fields.Char(
        string="ECB feed override URL",
        config_parameter="rs_fx.ecb_url",
        help="Enterprise only: serve the built-in 'European Central Bank' "
             "currency provider from this eurofxref-format URL instead of "
             "ecb.europa.eu. Leave empty for stock behaviour.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        value = self.env["ir.config_parameter"].sudo().get_param(
            UPDATE_RATES_PARAM, "1"
        )
        res["rs_fx_update_currency_rates"] = value not in (
            "0", "False", "false",
        )
        return res

    def set_values(self):
        super().set_values()
        self.env["ir.config_parameter"].sudo().set_param(
            UPDATE_RATES_PARAM,
            "1" if self.rs_fx_update_currency_rates else "0",
        )
