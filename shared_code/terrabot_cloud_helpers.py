from __future__ import annotations

# Central shared environment catalog. terrabot_service_core remains the owner of
# the live repository lookup and generation workflow; this file centralizes the
# stable repository/environment mapping so Teams and other callers can reuse it.
AWS_NONPROD = {
    "dev": "terraform/dev_aws/dev", "minidev": "terraform/dev_aws/minidev",
    "bolt": "terraform/dev_aws/bolt", "bolt_dr": "terraform/dev_aws/bolt_dr",
    "bolt_sqlstaging": "terraform/dev_aws/bolt_sqlstaging", "dev_devops": "terraform/dev_aws/dev_devops",
    "dev_sqlstaging": "terraform/dev_aws/dev_sqlstaging", "global": "terraform/dev_aws/global",
    "minidev_sqlstaging": "terraform/dev_aws/minidev_sqlstaging", "observe": "terraform/dev_aws/observe",
}
AWS_PROD = {
    "ca3": "terraform/prod_aws/ca3", "ca3_dr": "terraform/prod_aws/ca3_dr", "devops": "terraform/prod_aws/devops",
    "eu1": "terraform/prod_aws/eu1", "eu1_dr": "terraform/prod_aws/eu1_dr", "eu2": "terraform/prod_aws/eu2", "eu2_dr": "terraform/prod_aws/eu2_dr",
    "global": "terraform/prod_aws/global", "observe": "terraform/prod_aws/observe", "sqlstaging": "terraform/prod_aws/sqlstaging",
    "sqlstaging_ca": "terraform/prod_aws/sqlstaging_ca", "sqlstaging_eu": "terraform/prod_aws/sqlstaging_eu", "sqlstaging_eu2": "terraform/prod_aws/sqlstaging_eu2",
    "sqlstaging_us4": "terraform/prod_aws/sqlstaging_us4", "sqlstaging_west": "terraform/prod_aws/sqlstaging_west",
    "us1": "terraform/prod_aws/us1", "us1_dr": "terraform/prod_aws/us1_dr", "us2": "terraform/prod_aws/us2", "us2_dr": "terraform/prod_aws/us2_dr",
    "us3": "terraform/prod_aws/us3", "us3_dr": "terraform/prod_aws/us3_dr", "us4": "terraform/prod_aws/us4", "us4_dr": "terraform/prod_aws/us4_dr",
    "root/global": "terraform/root/global",
}
AZURE_NONPROD = {
    "npr-int": "vars/npr/npr-int", "npr-stg": "vars/npr/npr-stg", "sbx-infra": "vars/sbx/sbx-infra",
}
AZURE_PROD = {
    "prd-ca4": "vars/prd/prd-ca4", "prd-eu3": "vars/prd/prd-eu3", "prd-us5": "vars/prd/prd-us5", "prd-us6": "vars/prd/prd-us6",
}
AZURE_ALIASES = {"sandbox": "sbx-infra", "sbx": "sbx-infra", "npr-staging": "npr-stg", "ca4": "prd-ca4", "eu3": "prd-eu3", "us5": "prd-us5", "us6": "prd-us6"}
