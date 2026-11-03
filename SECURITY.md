# Security and privacy

This application is a local single-user tool, not a hosted multi-user service. Do not expose its port to the internet.

Never attach `data/secrets.json`, `.env`, Hermes sessions, model authentication files, or private runtime databases to an issue. Report security problems privately through GitHub's security reporting facility when available; otherwise contact the maintainer without including exploit secrets in public issues.

The optional Agent uses local terminal/file tools with your OS user's privileges. An isolated Hermes profile prevents accidental configuration sharing but is not an OS sandbox. Use a dedicated OS account/container for stronger isolation.
