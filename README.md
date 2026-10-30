# Creator Studio for Codex

Film your clips, then ask Codex to edit them. Includes the existing editing engine, caption styles,
effects, named editing styles, reference-video analysis and style recreation, video-to-carousel workflows,
carousel rendering, and posting helpers. The video and carousel workflows are bundled together.

For buyers of Creator Studio. Walkthrough and support: https://portal.tenfoldmarketing.com
This edition runs locally in Codex desktop or Codex CLI. The Claude editions are separate products/repos.

## Install once

Give Codex the following prompt (the account must have access to any private repository):

> Install Creator Studio for Codex from https://github.com/tenfoldmarc/studio-plugin-codex.
> Read its README, register its Git-backed marketplace, install the plugin and verify the installed manifest.
> Keep the source tracking main so I can request future updates.

Or run these native commands in Terminal or PowerShell, one line at a time:

```bash
codex plugin marketplace add tenfoldmarc/studio-plugin-codex --ref main
codex plugin add video-studio@creator-studio-codex
```

Then start a new Codex chat and say **"Set up Creator Studio."**
If the desktop has not discovered the new plugins, restart the app and start a new chat.

Prerequisites: a current Codex desktop/CLI, Git, and authenticated Git access for private repositories.
The installer uses the native `codex plugin` commands available in Codex CLI 0.143.0 and later compatible releases.
If `codex` is not on PATH, Codex can use its bundled executable or you can install the CLI from
https://developers.openai.com/codex/cli. The editing setup obtains its own Python/Node/ffmpeg as needed.
GitHub access is separate from signing in to Codex or connecting its GitHub app: local Git must be able to clone
the private repositories, using a credential manager or SSH. Do not paste access tokens into chat.

An optional `install.py` helper is included for an already downloaded checkout and a working Python 3.9+:
`python install.py` installs this product ;
`python install.py --all` installs both, Creator Studio first. Never run downloaded code from an untrusted source.

## Use it

- "Edit these clips in my saved style."
- "Study this video link and recreate its editing style on my footage."
- "Turn my last reel into a carousel."
- "Make a carousel about [topic]."

The reference workflow downloads accessible videos, reads frame/contact sheets, motion strips and transcripts,
and compares the resulting look. For links that require a login or cannot be downloaded, supply the video file.
External services such as Apify or posting providers may need the customer's own connection and usage credits.

## Updates: just tell Codex

> Update the video studio plugin and the script studio plugin.

You can also say **"Update the video studio plugin"** or **"Update Script Studio"** separately.
The loaded skill recognizes these requests, refreshes the official source, installs the package and verifies
the installed manifest. Both requested installed plugins are attempted even if one update fails. No editing
setup or model download is needed just to update a plugin. The updater never installs a missing paid add-on
unless the user actually requested installation.

Start one new chat after the updates to load the new instructions. This is an on-demand update; a Git push
does not silently replace the instructions in an already running chat. A daily check during normal use can
offer releases, and a failed/offline check leaves editing available.

Native fallback for both installed products:

```bash
codex plugin marketplace upgrade creator-studio-codex
codex plugin add video-studio@creator-studio-codex
codex plugin marketplace upgrade script-studio-codex
codex plugin add script-studio@script-studio-codex
```

Codex may use a versioned cache or a cache called `local`; the updater uses the registered cache key and
reads the actual release from `plugin.json`. The helper checks private releases using authenticated Git, not unauthenticated raw URLs.

## Your data

Codex settings use `video-studio-codex` and `script-studio-codex` per-user data directories:
macOS `~/Library/Application Support/`, Windows `%LOCALAPPDATA%/`, Linux `${XDG_DATA_HOME:-~/.local/share}/`.
Styles, carousel looks, voice profiles, research, credentials and downloaded tools live outside the plugin cache.
Updates replace plugin code and leave those folders and project outputs in place. Existing Claude settings are
not imported or modified automatically. `VIDEO_STUDIO_STATE` / `SCRIPT_STUDIO_STATE` can select explicit data folders.

## Ship a release

1. Develop on a branch and run the automated checks.
2. Update `video-studio/plugin.json` and `video-studio/.codex-plugin/plugin.json` to the same higher `X.Y.Z` version.
3. Add the same version to `whats-new.json` and commit the complete release.
4. Merge into `main` and push this Codex repository. Customers' next update request installs that release.

Use `python -m unittest discover -s tests` for package/updater checks. Creator Studio also retains the inherited
cross-platform media end-to-end workflow. Local install/update smoke checks are separate from real-video quality
and Windows testing; passing packaging tests alone does not establish editing quality on every machine.

Private distribution: give each buyer access to every repository included in their purchase. Removing GitHub
access prevents future downloads/updates; it does not erase already downloaded files. No license key is bundled.

© Ten Fold Marketing. For buyers under the terms agreed at purchase. Not affiliated with or endorsed by OpenAI.
