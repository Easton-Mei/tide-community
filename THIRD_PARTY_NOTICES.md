# Third-party components and data

Tide Community core uses the Python standard library only. Python is separately installed by the user and is not redistributed in this release.

## Hermes Agent (optional, not bundled)

- Upstream: https://github.com/NousResearch/hermes-agent
- License: MIT, Copyright (c) 2025 Nous Research.
- Pinned installer revision: `c4b2beea778ceca1462b91282589338b5e80781f`.
- The optional installer obtains upstream source and its dependencies in `.tools/`. Their respective licenses remain applicable. No upstream source, runtime, login data or model credentials are included in the Tide release archive.
- Hermes license: https://github.com/NousResearch/hermes-agent/blob/c4b2beea778ceca1462b91282589338b5e80781f/LICENSE

## Public information sources

Company names, ticker symbols and feed URLs identify external sources; they do not imply affiliation or endorsement. Sources include company newsrooms, SEC EDGAR and Yahoo Finance public chart snapshots.

This software license covers Tide code and its original documentation, not third-party news text, market data or redistribution rights. The release contains only fictional example content, not a copied historical news database. Users fetch sources directly for their own use and must follow applicable source terms and access limits.

- SEC developer resources: https://www.sec.gov/about/developer-resources
- SEC fair access guidance: https://www.sec.gov/about/webmaster-frequently-asked-questions
- Yahoo terms: https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html

## Model providers

Users choose their own OpenAI-compatible service. Tide includes no API quota or model subscription. Model processing sends relevant report/task content to the configured provider. Provider pricing, policies and data handling apply separately.
