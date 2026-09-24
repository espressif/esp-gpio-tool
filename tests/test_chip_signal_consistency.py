# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Every signal advertised in a pin's `functions` must be assignable through a peripheral."""

import pytest

from esp_gpio_tool_cli.chip import ESP
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS

# Signals listed on a pin but not backed by any peripheral instance, so `check` rejects them.
# Tracked in a follow-up task; names must be removed once the chip definitions are corrected.
KNOWN_ORPHANS: dict[str, set[str]] = {
    'esp32': {
        'EMAC_CLK_OUT_180',
        'SDHOST_STROBE_1',
    },
    'esp32s3': {
        # No SUBSPI instance exists yet; see the `# TODO SUBSPI` in esp32s3.yaml
        'SUBSPICS0',
        'SUBSPICS1',
        'SUBSPICLK',
        'SUBSPICLK_DIFF',
        'SUBSPID',
        'SUBSPIHD',
        'SUBSPIQ',
        'SUBSPIWP',
        # Differential clock output is not modelled by the SPI peripheral
        'SPICLK_DIFF',
        # Only USB_OTG_RCV is declared by the peripherals
        'USB_RCV',
    },
}


def find_orphans(esp: ESP) -> dict[tuple[int, str], str]:
    """Map each unreachable (pin, signal) pair to the reason it cannot be assigned."""
    orphans = {}
    for number, pin in esp.gpios.items():
        for function in pin.functions:
            try:
                peripheral = esp.get_peripheral_from_function(function)
            except ValueError:
                orphans[(number, function)] = 'no matching peripheral'
                continue
            if not any(function in peripheral.all_pins.get(i, []) for i in peripheral.instances):
                orphans[(number, function)] = f'not in {peripheral.name}.all_pins'
    return orphans


@pytest.mark.parametrize('chip', SUPPORTED_CHIPS)
def test_every_pin_function_is_reachable(chip: str) -> None:
    orphans = find_orphans(ESP(chip))
    unexpected = sorted(
        (number, function, reason)
        for (number, function), reason in orphans.items()
        if function not in KNOWN_ORPHANS.get(chip, set())
    )
    assert not unexpected, f'{chip}: unreachable pin functions: {unexpected}'


@pytest.mark.parametrize('chip', sorted(KNOWN_ORPHANS))
def test_known_orphans_are_still_orphaned(chip: str) -> None:
    """Fixed signals have to be dropped from KNOWN_ORPHANS so the list cannot go stale."""
    orphan_signals = {function for _, function in find_orphans(ESP(chip))}
    reachable = sorted(KNOWN_ORPHANS[chip] - orphan_signals)
    assert not reachable, f'{chip}: now reachable, remove from KNOWN_ORPHANS: {reachable}'
