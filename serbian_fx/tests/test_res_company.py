# -*- coding: utf-8 -*-
"""The rs_fx.ecb_url override must parse eurofxref-format XML and refuse
feeds carrying a DTD or entity declaration (XXE guard around stdlib
ElementTree). No network: requests.get is mocked."""

from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.serbian_fx.models import res_company

ECB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
    xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-08-19">
      <Cube currency="USD" rate="1.1652"/>
      <Cube currency="JPY" rate="171.65"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""

DOCTYPE_XML = b"""<?xml version="1.0"?>
<!DOCTYPE Envelope [<!ENTITY x "boom">]>
<Envelope><Cube time="2026-08-19"/></Envelope>"""

ENTITY_XML = b"""<?xml version="1.0"?>
<Envelope><!ENTITY x "boom"><Cube time="2026-08-19"/></Envelope>"""


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class TestEcbOverride(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "rs_fx.ecb_url", "https://example.com/eurofxref-daily.xml"
        )

    def _parse(self, content):
        currencies = (
            self.env.ref("base.EUR")
            | self.env.ref("base.USD")
            | self.env.ref("base.JPY")
        )
        with patch.object(
            res_company.requests, "get", return_value=FakeResponse(content)
        ):
            return self.env.company._parse_ecb_data(currencies)

    def test_custom_feed_parsed(self):
        result = self._parse(ECB_XML)
        self.assertEqual(result["EUR"], (1.0, "2026-08-19"))
        self.assertEqual(result["USD"], (1.1652, "2026-08-19"))
        self.assertEqual(result["JPY"], (171.65, "2026-08-19"))

    def test_doctype_rejected(self):
        with self.assertRaises(ValueError):
            self._parse(DOCTYPE_XML)

    def test_entity_rejected(self):
        with self.assertRaises(ValueError):
            self._parse(ENTITY_XML)
