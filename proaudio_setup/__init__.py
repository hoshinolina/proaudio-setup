# SPDX-FileCopyrightText: 2026-present Hoshino Lina <lina@lina.yt>
#
# SPDX-License-Identifier: MIT

from .modules import irqs, kernel, user

ALL_MODULES = [
    kernel,
    irqs,
    user,
]
