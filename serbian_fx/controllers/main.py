# -*- coding: utf-8 -*-
"""Read-only JSON/XML API for Serbian exchange rates.

Endpoints (GET, no auth — the rates are public data):

  /rs_fx/rates
      Latest stored list, all currencies.

  /rs_fx/rates?currency=EUR
      Latest rate for one currency.

  /rs_fx/rates?currency=EUR&date=2026-08-19
      Rate for one currency on a specific date (falls back to the most
      recent rate on or before that date, like Odoo's own rate lookup).

  /rs_fx/rates?currency=EUR&history=30
      Last N stored days for one currency.

  /rs_fx/rates/ecb
      Latest list in the European Central Bank eurofxref-daily.xml format
      (gesmes envelope, nested Cube elements), base RSD. ECB semantics:
      1 unit of base currency = rate units of the quoted currency, so
      rate = unit / middle. Optional params:
        rate=middle|buy|sell|buy_cash|sell_cash   (default middle)
        date=YYYY-MM-DD                           (most recent on/before)

The JSON shape doubles as the module's custom-source contract: another
instance can consume /rs_fx/rates via rs_fx.rate_source = custom.
"""

import json
from datetime import date as date_type

from odoo import http
from odoo.http import request


def _serialize(record):
    return {
        "currency": record.currency_id.name,
        "date": record.date.isoformat(),
        "unit": record.unit,
        "buy": record.buy,
        "middle": record.middle,
        "sell": record.sell,
        "buy_cash": record.buy_cash,
        "sell_cash": record.sell_cash,
        "source": record.source,
    }


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload, ensure_ascii=False),
        headers=[("Content-Type", "application/json; charset=utf-8")],
        status=status,
    )


class RsFxController(http.Controller):

    @http.route("/rs_fx/rates", type="http", auth="public",
                methods=["GET"], csrf=False)
    def rates(self, currency=None, date=None, history=None, **kwargs):
        Rate = request.env["rs.fx.rate"].sudo()
        domain = []

        if currency:
            domain.append(("currency_id.name", "=", currency.strip().upper()))

        if date:
            try:
                requested = date_type.fromisoformat(date)
            except ValueError:
                return _json_response(
                    {"error": "invalid date, expected YYYY-MM-DD"}, status=400)
            domain.append(("date", "<=", requested.isoformat()))

        if history:
            try:
                limit = max(1, min(int(history), 1000))
            except ValueError:
                return _json_response(
                    {"error": "invalid history, expected an integer"}, status=400)
            records = Rate.search(domain, order="date desc, currency_id",
                                  limit=limit if currency else limit * 20)
        else:
            latest = Rate.search(domain, order="date desc", limit=1)
            if not latest:
                return _json_response({"error": "no rates stored"}, status=404)
            records = Rate.search(
                domain + [("date", "=", latest.date)], order="currency_id")

        if not records:
            return _json_response({"error": "no rates stored"}, status=404)

        return _json_response({
            "date": records[0].date.isoformat(),
            "base": "RSD",
            "source": "serbian_fx (NBS / Alta Banka)",
            "rates": [_serialize(record) for record in records],
        })

    @http.route("/rs_fx/rates/ecb", type="http", auth="public",
                methods=["GET"], csrf=False)
    def rates_ecb(self, rate="middle", date=None, **kwargs):
        if rate not in ("middle", "buy", "sell", "buy_cash", "sell_cash"):
            return _json_response(
                {"error": "invalid rate, expected one of: "
                          "middle, buy, sell, buy_cash, sell_cash"}, status=400)

        Rate = request.env["rs.fx.rate"].sudo()
        domain = []
        if date:
            try:
                requested = date_type.fromisoformat(date)
            except ValueError:
                return _json_response(
                    {"error": "invalid date, expected YYYY-MM-DD"}, status=400)
            domain.append(("date", "<=", requested.isoformat()))

        latest = Rate.search(domain, order="date desc", limit=1)
        if not latest:
            return _json_response({"error": "no rates stored"}, status=404)
        records = Rate.search(
            domain + [("date", "=", latest.date)], order="currency_id")

        cubes = []
        for record in records:
            value = record[rate]
            if not value:
                continue
            # ECB semantics: 1 unit of base (RSD) = this many units of the
            # quoted currency. Lists quote RSD per `unit` units, so invert.
            cubes.append(
                '\t\t\t<Cube currency="%s" rate="%.8f"/>'
                % (record.currency_id.name, record.unit / value)
            )

        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gesmes:Envelope'
            ' xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"'
            ' xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">\n'
            "\t<gesmes:subject>Reference rates</gesmes:subject>\n"
            "\t<gesmes:Sender>\n"
            "\t\t<gesmes:name>Serbian exchange rates, base RSD</gesmes:name>\n"
            "\t</gesmes:Sender>\n"
            "\t<Cube>\n"
            '\t\t<Cube time="%s">\n'
            "%s\n"
            "\t\t</Cube>\n"
            "\t</Cube>\n"
            "</gesmes:Envelope>\n"
            % (latest.date.isoformat(), "\n".join(cubes))
        )
        return request.make_response(
            xml,
            headers=[("Content-Type", "application/xml; charset=utf-8")],
        )
