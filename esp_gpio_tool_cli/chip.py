# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import os
import re
import sys
from functools import cached_property
from itertools import chain

import yaml

from esp_gpio_tool_cli.logger import Logger
from esp_gpio_tool_cli.peripheral import *  # noqa: F403
from esp_gpio_tool_cli.peripheral import BasePeripheral
from esp_gpio_tool_cli.pin import Pin

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'targets/')
SUPPORTED_CHIPS = sorted(
    filename.removesuffix('.yaml') for filename in os.listdir(CONFIG_DIR) if filename.endswith('.yaml')
)

logger = Logger()

# MCPWM generator outputs (A/B per channel); excludes SYNC/FLT/CAP which are not servo-style PWM.
_MCPWM_PWM_OUT_FN_RE = re.compile(r'^MCPWM\d+_OUT\d+[AB]$')


def load_config(target: str) -> dict[str, dict]:
    """Load config from yaml file"""
    target = os.path.join(CONFIG_DIR, f'{target}.yaml')
    with open(target, encoding='UTF-8') as stream:
        try:
            return yaml.safe_load(stream)  # type: ignore
        except yaml.YAMLError as exc:
            raise SystemExit(exc) from exc


class SOC:
    mpn: str  # Manufacturer Part Number
    reserved_pins: list[int]
    not_connected_pins: list[int]

    def __init__(self, mpn: str, reserved_pins: list[int] = None, not_connected: list[int] = None) -> None:
        self.mpn = mpn
        self.reserved_pins = reserved_pins or []
        self.not_connected_pins = not_connected or []

    def __str__(self) -> str:
        return self.mpn

    def __repr__(self) -> str:
        return f'<SOC: {self.mpn}>'


class ESP:
    gpios: dict[int, Pin]
    peripherals: list[BasePeripheral]
    soc_list: list[SOC]
    selected_soc: SOC | None

    def __init__(self, name: str) -> None:
        self.name = name
        self.config = load_config(name)
        self.load_pins()
        self.load_peripherals()
        self.load_socs()
        self.selected_soc = None

    @cached_property
    def features(self) -> dict:
        """Return chip features useful for chip selection (CPU, memory, connectivity, etc.)"""
        return self.config.get('features', {})

    @property
    def assigned_pins(self) -> list[Pin]:
        """Return pins that have been assigned a function"""
        return [pin for pin in self.gpios.values() if pin.assigned_functions]

    @property
    def free_pins(self) -> list[Pin]:
        """Return pins that have not been assigned a function"""
        return [pin for pin in self.gpios.values() if not pin.assigned_functions]

    @property
    def used_peripherals(self) -> list[BasePeripheral]:
        """Return peripherals that have been used"""
        return [peripheral for peripheral in self.peripherals if any(peripheral.used.values())]

    @cached_property
    def reassignable_peripherals_regex(self) -> str:
        """Return regex for common prefixes of peripherals that can be reassigned"""
        prefix_list = [peripheral.common_prefix for peripheral in self.peripherals if peripheral.reassignable]
        return rf'({"|".join(prefix_list)})'

    def _str_to_class(self, name: str) -> type[BasePeripheral]:
        """Convert name to class; defaults to `BasePeripheral` if class not found"""
        return getattr(sys.modules[__name__], name, BasePeripheral)

    def load_pins(self) -> None:
        """Load pins from config"""
        self.gpios = {number: Pin(pin=number, **data) for number, data in self.config['gpio'].items()}

    def load_peripherals(self) -> None:
        """Load peripherals from config"""
        self.peripherals = [self._str_to_class(peri)(**data) for peri, data in self.config['peripheral'].items()]

    def load_socs(self) -> None:
        """Load supported SoCs from config"""
        soc_list = self.config.get('soc', {})
        self.soc_list = [SOC(mpn, **data) for mpn, data in soc_list.items()]

    def set_soc(self, soc_mpn: str) -> None:
        """Set used SoC and update available pins"""
        for soc_class in self.soc_list:
            if soc_class.mpn == soc_mpn:
                soc = soc_class
                break
        else:
            raise SystemExit(
                f'Error: SoC "{soc_mpn}" is not supported variant of {self.name}. '
                f'Supported SoCs: {", ".join([x.mpn for x in self.soc_list])}'
            )

        if self.selected_soc == soc:
            return
        # reload pins to its default state
        self.load_pins()
        # set reserved pins
        for pin in soc.reserved_pins:
            self.gpios[pin].assign_function('Flash/PSRAM')
        # set not connected pins
        for pin in soc.not_connected_pins:
            self.gpios.pop(pin)
        self.selected_soc = soc

    def get_peripheral(self, name: str) -> BasePeripheral:
        """Return peripheral with the given name"""
        for peripheral in self.peripherals:
            if peripheral.name == name or peripheral.__class__.__name__ == name:
                return peripheral
        raise ValueError(f'Peripheral {name} not found in peripherals for {self.name}.')

    def get_peripheral_from_function(self, function: str) -> BasePeripheral:
        """Return peripheral that uses the function"""
        for peripheral in self.peripherals:
            if re.match(rf'^{peripheral.common_prefix}', function):
                return peripheral
        raise ValueError(f'Function {function} not found in peripherals for {self.name}.')

    def get_gpio_list(self) -> list[int]:
        """Return list of GPIOs for the chip as list of integers"""
        return list(self.gpios.keys())

    def list_pins_by_function(self, function: str) -> list[Pin]:
        """Return list of pins that can be assigned to the function. Mainly used for filtering 'assigned_pins'"""
        pins = []
        universal_periph = re.match(self.reassignable_peripherals_regex, function)
        # TODO: this is not filtering for cases like I2S_CLK on ESP32, which has to be assigned to CLK_OUT* pin
        # But this limitation will be caught later in `assign_function` method
        if not universal_periph:
            # peripheral does not support reassignment; filter out pins based on 'assigned_pins'
            for pin in self.gpios.values():
                if function in pin.functions:
                    pins.append(pin)
        if not pins:
            # no restriction on function; return all pins
            pins = self.free_pins
        return pins

    def check(self) -> None:
        """Check if required pins by each used peripheral are assigned"""
        assigned_functions = list(chain.from_iterable([pin.assigned_functions for pin in self.assigned_pins]))
        for peripheral in self.used_peripherals:
            peripheral.check_required_pins(assigned_functions)


def get_peripheral_instance_counts(esp: ESP) -> dict[str, int]:
    """Number of independent controller instances per peripheral type (e.g. SPI blocks, UART ports).

    This is ``len(instances)`` from the pin tool model — e.g. three SPI blocks vs one LEDC block with many PWM channels.
    For PWM channel totals use :func:`get_pwm_output_capacity` instead.
    """
    return {p.__class__.__name__: len(p.instances) for p in esp.peripherals}


def get_pwm_output_capacity(esp: ESP) -> dict[str, int]:
    """Count on-chip PWM-style signals usable for independent outputs (e.g. servos).

    Sums LEDC ``SIG_OUT`` functions across instances and MCPWM ``OUTnA``/``OUTnB`` outputs.
    """
    ledc = 0
    mcpwm = 0
    for p in esp.peripherals:
        cls_name = p.__class__.__name__
        if cls_name == 'LEDC':
            for flist in p.universal_pins.values():
                ledc += sum(1 for f in flist if 'SIG_OUT' in f)
        elif cls_name == 'MCPWM':
            for flist in p.universal_pins.values():
                mcpwm += sum(1 for f in flist if _MCPWM_PWM_OUT_FN_RE.match(f))
    return {
        'ledc_pwm_outputs': ledc,
        'mcpwm_pwm_outputs': mcpwm,
        'max_independent_pwm_outputs': ledc + mcpwm,
    }
