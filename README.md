# Serbian Exchange Rates for Odoo 19

Free Odoo module (`serbian_fx`, LGPL-3) bringing daily RSD exchange rates
into Odoo: the **official National Bank of Serbia list by default**, with
selectable commercial bank sources (currently **Alta Banka**) and custom
endpoints. All five published rates stored daily, the middle rate wired into
standard multicurrency accounting, full history, and a read-only API.

A companion standalone service lives in
[Coriol-is/alta-fx-api](https://github.com/Coriol-is/alta-fx-api) — the Alta
scraper without Odoo, plus an ECB `eurofxref-daily.xml` drop-in feed.

## Features

- **Daily rates** — scheduled action (07:30 server time) fetches the current
  list from the configured source: buy / middle / sell for wire transfers
  (*devize*) and buy / sell for cash (*efektiva*), per currency, with quote
  parity (e.g. JPY is quoted per 100). Idempotent upserts; every row carries
  its `source`.
- **Sources** — `nbs` (official list, default), `alta` (commercial spreads
  scraped from altabanka.rs), `custom` (any endpoint speaking this module's
  JSON contract — e.g. another Odoo database running this module). All
  Serbian sources publish the same middle rate: a bank's *srednji kurs* is
  the NBS middle (verified to the fourth decimal), so switching sources
  never changes what lands in accounting — only the stored spreads differ.
- **Accounting integration** — the middle rate is written into
  `res.currency.rate` (global, `company_id = False`). Designed for **RSD**
  company currency: `rate = unit / middle`; skipped with a warning otherwise.
- **History** — one `rs.fx.rate` record per currency per day, never deleted.
  Browse under *Accounting → Configuration → Serbian Exchange Rates*;
  manual refresh via the *Fetch rates now* button.
- **Backfill** — historical rates from the official NBS list for any period.
- **API** — public JSON and ECB-format XML endpoints.

## Install

1. Copy/symlink `serbian_fx` into your addons path (or install from the
   Odoo Apps store).
2. Activate the currencies you need in *Accounting → Configuration →
   Currencies* (only active currencies are stored).
3. Install **Serbian Exchange Rates**. Done — NBS rates flow immediately.

## Configuration (system parameters)

| Parameter | Default | Effect |
|---|---|---|
| `rs_fx.rate_source` | `nbs` | `nbs` — official NBS list via the [kurs.resenje.org](https://kurs.resenje.org) mirror. `alta` — Alta Banka commercial list scraped from altabanka.rs. `custom` — endpoint from `rs_fx.custom_url`. |
| `rs_fx.custom_url` | unset | URL returning this module's JSON contract (see below); required when source is `custom`. |
| `rs_fx.update_currency_rates` | `1` | Set `0` to keep the rates in their own table without touching `res.currency.rate`. |
| `rs_fx.ecb_url` | unset | Redirect the stock ECB provider of Automatic Currency Rates to an ECB-format feed you host (see [alta-fx-api](https://github.com/Coriol-is/alta-fx-api)). Unset = stock behaviour. |

## JSON & ECB API

Public read-only endpoints (the rates are public data):

```
GET /rs_fx/rates                                  # latest full list
GET /rs_fx/rates?currency=EUR                     # latest EUR
GET /rs_fx/rates?currency=EUR&date=2026-08-19     # EUR on/before a date
GET /rs_fx/rates?currency=EUR&history=30          # last 30 stored EUR rows
GET /rs_fx/rates/ecb                              # ECB eurofxref-daily.xml format
GET /rs_fx/rates/ecb?rate=sell&date=2026-08-19    # rate type + date
```

JSON response — this shape is also the `custom` source contract, so one
database running the module can feed others:

```json
{
  "date": "2026-08-19",
  "base": "RSD",
  "source": "serbian_fx (NBS / Alta Banka)",
  "rates": [
    {"currency": "EUR", "date": "2026-08-19", "unit": 1,
     "buy": 117.0073, "middle": 117.3594, "sell": 117.7115,
     "buy_cash": 116.5379, "sell_cash": 118.1809, "source": "nbs"}
  ]
}
```

`/rs_fx/rates/ecb` mirrors the European Central Bank `eurofxref-daily.xml`
structure (gesmes envelope, nested `Cube` elements) with **RSD as base**:
`rate` = units of quoted currency per 1 RSD (`unit / middle` — the same
value written into `res.currency.rate`). `rate=` selects
middle/buy/sell/buy_cash/sell_cash, default middle.

## Source implementation notes

- **NBS** (default): one GET per day to the public mirror
  `kurs.resenje.org/api/v1/rates/<date>`. Official buy/sell spreads;
  some currencies are quoted middle-only.
- **Alta Banka**: the bank renders its table with wpDataTables in
  server-side mode — the page holds no data, only a daily nonce. The client
  does two HTTPS requests: `GET /kursna-lista-2/` for the nonce, then a
  DataTables `POST` to `admin-ajax.php` returning the current list as JSON.
  No browser, no HTML parsing. The nonce rotates daily; a fresh one is
  fetched on every run.
- **Custom**: `GET rs_fx.custom_url`, expects the JSON contract above
  (`date`, `currency`, `middle` required per row).
- Adding a bank = one `fetch_<bank>_rates()` in
  `serbian_fx/models/fx_client.py` plus one selection entry in
  `fx_rate.py`. The client module has no Odoo imports and runs standalone:
  `python3 serbian_fx/models/fx_client.py` prints today's NBS and Alta lists.

## Historical backfill

Bank sites don't expose history (Alta's endpoint pins every response to the
latest date server-side), so backfill uses the official NBS list — which is
also the middle rate every bank publishes.

From odoo shell:

```python
from datetime import date
env["rs.fx.rate"]._backfill_history(date(2024, 1, 1))   # from date, to today
env.cr.commit()
```

Idempotent: existing rows are never overwritten; weekends resolve to the
preceding published list and dedupe naturally.

## Notes

- License: LGPL-3. Support: odoo@coriol.co.
