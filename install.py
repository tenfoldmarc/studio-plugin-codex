#!/usr/bin/env python3
"""Install Creator Studio for Codex from the official tracked repositories.

Run with --all to install both Studios. Requires a working Python 3.9+, Git and Codex CLI.
The README also has native commands that require no Python.
"""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / 'video-studio/skills/video-studio/scripts'))
import update

if __name__ == '__main__':
    raise SystemExit(update.main(['--install'] + sys.argv[1:]))
