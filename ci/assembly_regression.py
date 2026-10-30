#!/usr/bin/env python3
"""Run the targeted media checks against the same static-ffmpeg package used by setup.

Requires static-ffmpeg==3.0 plus requests, filelock and progress==1.6.1. It downloads
only the platform's ffmpeg/ffprobe binaries into that package's environment. No ASR,
renderer, customer configuration or credentials are required.
"""
import os
from pathlib import Path
import subprocess
import sys


def main():
    from static_ffmpeg import run
    ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
    environment = dict(os.environ, STUDIO_RUN_MEDIA_TESTS='1', STUDIO_TEST_FFMPEG=ffmpeg,
                       STUDIO_TEST_FFPROBE=ffprobe, PYTHONDONTWRITEBYTECODE='1')
    version = subprocess.run([ffmpeg, '-version'], capture_output=True, text=True, encoding='utf-8', check=True)
    print(version.stdout.splitlines()[0], flush=True)
    return subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                           '-p', 'test_assembly_regression.py', '-v'],
                          cwd=Path(__file__).resolve().parents[1], env=environment).returncode


if __name__ == '__main__':
    raise SystemExit(main())
