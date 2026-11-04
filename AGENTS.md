# Tide Community contributor instructions

This is the standalone public project. Never read or modify a user's other Tide/Hermes installations.
Runtime files (data, reports, logs, config/*.json, .tools) are private and must never be committed or bundled.
Use the standard library for core features. Keep UI assets local, with no build step/CDN/tracking.
Agent operation instructions: agent/AGENT.md. This file is for code contributors.
Validate with `python3 -m unittest discover -s tests -v` and a clean temporary TIDE_HOME.
Build releases using `python3 scripts/build_release.py`; never zip the working directory directly.
Do not claim Windows, model-provider, live-delivery or market-data verification without actual evidence.

Local delivery hygiene: keep the designated handoff directory limited to the current complete ZIP, one user-facing usage note, and its SHA256SUMS.txt. Use build_release.py --name Tide-Community for a stable local filename. Consolidate documentation updates into the full package; do not accumulate patch folders or duplicate extracted copies. Store QA tools, screenshots and install logs under ignored .local-work/, outside the handoff directory. Before removing an extracted copy, verify it has no user changes.
