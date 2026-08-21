# -*- coding: utf-8 -*-
{
    "name": "Serbian Exchange Rates",
    "summary": "Daily RSD exchange rates: official NBS list by default, "
               "commercial bank lists (Alta Banka) optional",
    "version": "19.0.3.0.1",
    "category": "Accounting",
    "license": "LGPL-3",
    "author": "Coriolis Lab",
    "website": "https://github.com/Coriol-is/rs-fxrate-odoo",
    "support": "odoo@coriol.co",
    # First entry is the store cover: the Apps grid and product page render
    # it in a strict 2:1 box with background-size: cover, so anything not
    # 2:1 gets centre-cropped.
    "images": [
        "static/description/cover.png",
        "static/description/banner.png",
    ],
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/rs_fx_params.xml",
        "data/ir_cron.xml",
        "views/fx_rate_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
