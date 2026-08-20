# -*- coding: utf-8 -*-
"""Optional redirect of the stock ECB currency provider to a custom feed.

Odoo Enterprise's Automatic Currency Rates (currency_rate_live) hardcodes
the ECB feed URL inside ``_parse_ecb_data``. Set the system parameter

    rs_fx.ecb_url = https://<your-service>/eurofxref-daily.xml

and select "European Central Bank" as the currency provider: this override
fetches that URL (same eurofxref XML format) instead of ecb.europa.eu.
With the parameter unset, the stock behaviour is untouched.

NOTE: written against the Odoo 17-19 provider contract
(_parse_<provider>_data(available_currencies) -> {code: (rate, 'YYYY-MM-DD')},
rates quoted against EUR). Verify once on your instance after install.
"""

import logging
import xml.etree.ElementTree as ET

import requests

from odoo import models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    def _parse_ecb_data(self, available_currencies):
        url = (
            self.env["ir.config_parameter"].sudo().get_param("rs_fx.ecb_url")
        )
        if not url:
            return super()._parse_ecb_data(available_currencies)

        _logger.info("Serbian FX: fetching ECB-format rates from %s", url)
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        date = None
        rates = {}
        for node in root.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag != "Cube":
                continue
            if node.get("time"):
                date = node.get("time")
            elif node.get("currency"):
                rates[node.get("currency")] = float(node.get("rate"))

        if not date or not rates:
            raise ValueError("Serbian FX: no rates in ECB-format feed %s" % url)

        available_names = set(available_currencies.mapped("name"))
        result = {}
        if "EUR" in available_names:
            result["EUR"] = (1.0, date)
        for code, value in rates.items():
            if code in available_names:
                result[code] = (value, date)
        return result
