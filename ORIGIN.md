# Codex edition provenance

This is the separately maintained Codex edition of https://github.com/tenfoldmarc/studio-plugin.
Claude feature version: **2.7.1**.
Source commit: `79932055fff1efed64c08bb334abf4651751380f`. The original Claude repository was read only during this port.
The same source version and commit are bundled in `video-studio/upstream.json`.

Codex and Claude use the same product feature version. A matching number is a tracking convention:
it does not replace checking the source changes and testing the corresponding workflows.
Advance the shared feature version only after the relevant changes have been ported and checked.

Keep Codex-specific installation, updater and state adaptations in this repository. Keep shared
renderer/research fixes deliberate and reviewed. Do not configure pushes to the Claude repository.
