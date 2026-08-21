# -*- coding: utf-8 -*-
import logging
import time
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import fx_client

_logger = logging.getLogger(__name__)

# source code -> (label, fetcher). Adding a bank = one fetcher in
# fx_client.py plus one entry here ('custom' is handled separately because
# it needs the configured URL).
SOURCES = [
    ("nbs", "NBS (official)"),
    ("alta", "Alta Banka"),
    ("custom", "Custom endpoint"),
]


class RsFxRate(models.Model):
    _name = "rs.fx.rate"
    _description = "Serbian Exchange Rate"
    _order = "date desc, currency_id"
    _rec_name = "currency_id"

    date = fields.Date(required=True, index=True)
    currency_id = fields.Many2one("res.currency", required=True, index=True)
    unit = fields.Integer(
        default=1,
        help="Number of currency units the rates are quoted for (parity).",
    )
    buy = fields.Float("Buy (devize)", digits=(12, 4))
    middle = fields.Float("Middle", digits=(12, 4))
    sell = fields.Float("Sell (devize)", digits=(12, 4))
    buy_cash = fields.Float("Buy (efektiva)", digits=(12, 4))
    sell_cash = fields.Float("Sell (efektiva)", digits=(12, 4))
    source = fields.Selection(
        SOURCES,
        default="nbs",
        required=True,
        help="'nbs': official NBS list — middle rate plus official spreads. "
             "'alta': Alta Banka commercial list scraped from altabanka.rs. "
             "'custom': endpoint configured in rs_fx.custom_url.",
    )

    _date_currency_uniq = models.Constraint(
        "UNIQUE(date, currency_id)",
        "Only one exchange rate per currency per day.",
    )

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _get_param(self, name, default=None):
        return self.env["ir.config_parameter"].sudo().get_param(name, default)

    def action_fetch_rates(self):
        """Manual trigger (list view button).

        Reports the outcome with a notification rather than a UserError: an
        exception escaping an RPC call rolls the cursor back, which would
        discard the rows this very call just refreshed.
        """
        written = self._fetch_rates()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if written else "warning",
                "message": (
                    _("%s exchange rates written.", written) if written
                    else _("The rate source returned nothing to store.")
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    @api.model
    def _cron_fetch_rates(self):
        """Daily cron entry point; logs instead of raising."""
        try:
            self._fetch_rates()
        except Exception:
            _logger.exception("Serbian FX: rate fetch failed")

    @api.model
    def _fetch_rates(self):
        """Fetch the latest rate list from the configured source, upsert
        rs.fx.rate rows and (unless disabled) the middle rate into
        res.currency.rate.

        Source is chosen by the system parameter rs_fx.rate_source:
        'nbs' (default), 'alta', or 'custom' (URL in rs_fx.custom_url).

        Returns the number of rs.fx.rate rows written (created or updated).
        """
        source = self._get_param("rs_fx.rate_source", "nbs")
        if source == "alta":
            rates = fx_client.fetch_alta_rates()
        elif source == "custom":
            url = self._get_param("rs_fx.custom_url")
            if not url:
                raise UserError(_(
                    "rs_fx.rate_source is 'custom' but rs_fx.custom_url "
                    "is not set."
                ))
            rates = fx_client.fetch_custom_rates(url)
        else:
            source = "nbs"
            rates = fx_client.fetch_nbs_day(fields.Date.context_today(self))
        if not rates:
            _logger.warning("Serbian FX: source '%s' returned no rates", source)
            return 0
        _logger.info(
            "Serbian FX: fetched %s rates for %s from %s",
            len(rates), rates[0]["date"], source,
        )

        currencies = {
            currency.name: currency
            for currency in self.env["res.currency"].search([])
        }
        written = 0
        for rate in rates:
            currency = currencies.get(rate["currency"])
            if currency is None:
                continue
            values = {
                "unit": rate["unit"],
                "buy": rate["buy"],
                "middle": rate["middle"],
                "sell": rate["sell"],
                "buy_cash": rate["buy_cash"],
                "sell_cash": rate["sell_cash"],
                "source": source,
            }
            existing = self.search(
                [("date", "=", rate["date"]), ("currency_id", "=", currency.id)],
                limit=1,
            )
            if existing:
                existing.write(values)
            else:
                self.create(
                    {"date": rate["date"], "currency_id": currency.id, **values}
                )
            written += 1
            self._update_currency_rate(currency, rate)
        return written

    # ------------------------------------------------------------------
    # Historical backfill
    # ------------------------------------------------------------------

    @api.model
    def _backfill_history(self, date_from, date_to=None):
        """One-off backfill of historical rates from the official NBS list
        (the only source with public history). Only currencies active in
        res.currency are stored; existing rows are never overwritten.

        Run from odoo shell:

            env['rs.fx.rate']._backfill_history(date(2024, 1, 1))
            env.cr.commit()

        Returns the number of rs.fx.rate rows created.
        """
        date_to = date_to or fields.Date.context_today(self)
        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        currencies = {
            currency.name: currency
            for currency in self.env["res.currency"].search([])
        }
        existing = {
            (record.date, record.currency_id.id)
            for record in self.search([
                ("date", ">=", date_from), ("date", "<=", date_to),
            ])
        }
        session = fx_client.requests.Session()
        created = 0
        seen = set()
        day = date_from
        while day <= date_to:
            try:
                rates = fx_client.fetch_nbs_day(day, session=session)
            except Exception:
                _logger.exception("NBS backfill: fetch failed for %s", day)
                day += timedelta(days=1)
                continue
            for rate in rates:
                currency = currencies.get(rate["currency"])
                if currency is None:
                    continue
                key = (rate["date"], currency.id)
                if key in seen or key in existing:
                    continue
                seen.add(key)
                if rate["date"] < date_from or rate["date"] > date_to:
                    continue
                self.create({
                    "date": rate["date"],
                    "currency_id": currency.id,
                    "unit": rate["unit"],
                    "buy": rate["buy"],
                    "middle": rate["middle"],
                    "sell": rate["sell"],
                    "buy_cash": rate["buy_cash"],
                    "sell_cash": rate["sell_cash"],
                    "source": "nbs",
                })
                created += 1
                self._update_currency_rate(currency, rate)
            day += timedelta(days=1)
            time.sleep(0.1)  # be polite to the mirror
        _logger.info(
            "NBS backfill: created %s rows for %s..%s", created, date_from, date_to
        )
        return created

    # ------------------------------------------------------------------
    # res.currency.rate integration
    # ------------------------------------------------------------------

    def _update_currency_rate(self, currency, rate):
        """Write the middle rate into the standard res.currency.rate.

        Odoo semantics with an RSD company currency: rate = amount of foreign
        currency per 1 RSD, i.e. unit / middle (middle is RSD per `unit`
        units of the currency).

        Disable with system parameter rs_fx.update_currency_rates = 0.
        """
        enabled = self._get_param("rs_fx.update_currency_rates", "1")
        if enabled in ("0", "False", "false"):
            return
        if not rate["middle"]:
            return

        company_currency = self.env.company.currency_id
        if company_currency.name != "RSD":
            _logger.warning(
                "Serbian FX: company currency is %s, not RSD — "
                "skipping res.currency.rate update", company_currency.name,
            )
            return
        if currency == company_currency:
            return

        # res.currency.rate is only writable by administrators, while the
        # fetch runs with accounting rights (list-view button, cron): sudo
        # just this model, not the whole fetch.
        CurrencyRate = self.env["res.currency.rate"].sudo()
        values = {"rate": rate["unit"] / rate["middle"]}
        existing = CurrencyRate.search(
            [
                ("currency_id", "=", currency.id),
                ("name", "=", rate["date"]),
                ("company_id", "=", False),
            ],
            limit=1,
        )
        if existing:
            existing.write(values)
        else:
            CurrencyRate.create(
                {
                    "currency_id": currency.id,
                    "name": rate["date"],
                    "company_id": False,
                    **values,
                }
            )
