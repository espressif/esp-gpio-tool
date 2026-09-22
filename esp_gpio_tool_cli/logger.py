# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0

from typing import ClassVar


class Logger:
    output: list[str]
    instance: ClassVar['Logger | None'] = None

    def __new__(cls) -> 'Logger':
        """Singleton class to log messages"""
        if cls.instance is None:
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self) -> None:
        if getattr(self, '_initialized', False):
            return
        self.output = []
        self._unicode = True
        self._initialized = True

    @classmethod
    def _del(cls) -> None:
        cls.instance = None

    def use_unicode(self, value: bool) -> None:
        """Set whether to use Unicode characters in the output"""
        self._unicode = value

    def error(self, message: str) -> None:
        """Add an error to the log"""
        emoji = '\U0000274c ' if self._unicode else ''
        self.output.append(f'{emoji}Error: {message}')

    def warn(self, message: str) -> None:
        """Add a warning to the log"""
        emoji = '\U000026a0 ' if self._unicode else ''
        self.output.append(f'{emoji}Warning: {message}')

    def note(self, message: str) -> None:
        """Add a note to the log"""
        emoji = '\U0001f4a1 ' if self._unicode else ''
        self.output.append(f'{emoji}Note: {message}')

    def get_output(self) -> list[str]:
        """Return the output and clear the log"""
        out = self.output or ['All checks passed.']
        self.output = []
        return out
