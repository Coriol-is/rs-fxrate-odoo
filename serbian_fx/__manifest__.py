# -*- coding: utf-8 -*-
{
    "name": "Serbian Exchange Rates",
    "summary": "Daily RSD exchange rates: official NBS list by default, "
               "commercial bank lists (Alta Banka) optional",
    "version": "19.0.2.0.0",
    "category": "Accounting",
    "license": "LGPL-3",
    "author": "Coriolis Lab",
    "website": "https://github.com/Coriol-is/serbian-fx-odoo",
    "support": "odoo@coriol.co",
    "images": ["static/description/banner.png"],
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/fx_rate_views.xml",
    ],
    "installable": True,
    "application": False,
}
