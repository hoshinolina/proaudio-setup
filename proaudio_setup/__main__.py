# SPDX-FileCopyrightText: 2026-present Hoshino Lina <lina@lina.yt>
#
# SPDX-License-Identifier: MIT
import sys, fcntl

if __name__ == "__main__":
    from proaudio_setup.cli import proaudio_setup

    sys.exit(proaudio_setup())
