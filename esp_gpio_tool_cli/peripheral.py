# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import re
from typing import Any

from esp_gpio_tool_cli.logger import Logger
from esp_gpio_tool_cli.pin import Pin

logger = Logger()


class BasePeripheral:
    count: int
    optional_pins: dict[str, list[str]]
    common_prefix: str  # I2C1_SCL, I2C1_SDA -> I2C
    used: dict[str, bool]

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        self.common_prefix = kwargs.get('common_prefix', self.name)
        # number of peripheral instances
        self.count = count

        # wildcard generation settings
        self.start_cnt = kwargs.get('start_cnt', 0)
        # names of instances, by default use counter from `start_cnt` to `count`
        self.instances: list[str] = kwargs.get(
            'instances', [str(i) for i in range(self.start_cnt, self.count + self.start_cnt)]
        )
        # keyword to replace in wildcard pins
        self._replace_keyword = kwargs.get('_replace_keyword', 'count')
        self.used = {i: False for i in self.instances}

        # convert wildcard pins to actual pins
        self._assigned_pins = self.unwrap_pins(assigned_pins)
        self._universal_pins = self.unwrap_pins(universal_pins)
        self.optional_pins = {}

        # peripheral modes in selected peripherals
        self.supported_modes: dict[str, list[str | int]] = {}  # {"HSPI": ["Single SPI, "Dual SPI", "Quad SPI"]}
        self.mode: dict[str, str | int] = {}  # {"HSPI": "Single SPI", "VSPI": "Quad SPI"}
        self.mode_label: str | None = None  # Used only if mode is not self descriptive enough (for GUI mostly)

        self.reassignable = False  # if assigned pins can be reassigned to any pin with GPIO matrix

    def __str__(self) -> str:
        return f'{self.name}(assigned_pins={self.assigned_pins}, universal_pins={self.universal_pins})'

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        """IO MUX signals/functions that are assigned to specific pins"""
        return self._assigned_pins

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        """GPIO matrix signals/functions that can be reassigned to any pin"""
        return self._universal_pins

    @property
    def all_pins(self) -> dict[str, list[str]]:
        """Return all assigned and universal pins"""
        return {i: self._assigned_pins.get(i, []) + self._universal_pins.get(i, []) for i in self.instances}

    @property
    def filtered_pins(self) -> dict[str, list[str]]:
        """Return all assigned and universal pins, filtered by selected mode"""
        return {i: self.assigned_pins.get(i, []) + self.universal_pins.get(i, []) for i in self.instances}

    @property
    def used_instances(self) -> list[str]:
        """Return all used instances"""
        return [i for i in self.instances if self.used[i]]

    def use(self, function: str, pin: Pin) -> None:
        """Check the pin if it can be used for this function and mark peripheral as used"""
        for instance in self.instances:
            if function in self.all_pins.get(instance, []):
                self.used[instance] = True
                self.check_pin_function(instance, function, pin)
                return
        raise ValueError(f'Function {function} not found in peripheral {self.name}.')

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        """Check if the pin supports the function and if it can be used as input/output"""
        if function in self.assigned_pins.get(instance, []):
            if function not in pin.functions:
                raise ValueError(f'Pin {pin.pin} does not support function {function}.')
        # TODO add check for input/output capabilities of the pin

    def check_required_pins(self, assigned_functions: list[str]) -> None:
        """Check if all required pins are assigned"""
        for instance in self.used_instances:
            required_pins = self.required_pins(instance)
            for pin in required_pins:
                if pin not in assigned_functions:
                    logger.error(f'Required function {pin} from peripheral {self.name} is not assigned to any pin.')

    def required_pins(self, instance: str) -> list[str]:
        """Return all required pins for a peripheral instance"""
        if instance not in self.instances:
            raise ValueError(f'Instance {instance} not found.')
        return list(set(self.filtered_pins.get(instance, [])) - set(self.optional_pins.get(instance, [])))

    def _literal_pin_instances(self, pin: str) -> list[str]:
        """Return instance keys for a literal pin without an instance placeholder."""
        if r'\d' in self.common_prefix:
            # if common prefix contains digit, use it as instance number
            instance = re.search(r'\d', pin)
            if instance:
                return [instance.group()]
        return [str(self.start_cnt)]

    def _expand_numbered_placeholder(
        self,
        pins: dict[str, list[str]],
        placeholder: str,
        counts: int | dict[str, int],
    ) -> dict[str, list[str]]:
        """Expand placeholders like `{channel}` or `{data_width}` per instance."""
        if not counts:
            return pins

        output: dict[str, list[str]] = {}
        token = f'{{{placeholder}}}'
        for instance, instance_pins in pins.items():
            output[instance] = []
            count = counts[instance] if isinstance(counts, dict) else counts
            for pin in instance_pins:
                if token in pin:
                    output[instance].extend([pin.format(**{placeholder: str(i)}) for i in range(count)])
                else:
                    output[instance].append(pin)
        return output

    def _expand_data_width_pins(self, pins: dict[str, list[str]]) -> dict[str, list[str]]:
        """Expand `{data_width}` up to the maximum supported mode per instance."""
        widths = {instance: int(max(self.supported_modes.get(instance, [1]))) for instance in self.instances}
        return self._expand_numbered_placeholder(pins, 'data_width', widths)

    def unwrap_pins(self, pins: list[str] | None) -> dict[str, list[str]]:
        """Convert wildcard pins to actual pins, e.g.
        - DAC_{count} -> {1: [DAC_1], 2: [DAC_2]]
        - {subname}_PCLK -> {LCD: [LCD_PCLK], CAM: [CAM_PCLK]]
        - [U1TX, U2TX] -> {1: [U1TX], 2: [U2TX]}
        """
        output: dict[str, list[str]] = {}
        if pins is not None:
            # prepare output dict with empty lists per peripheral instance
            output = {i: [] for i in self.instances}
            placeholder = f'{{{self._replace_keyword}}}'
            for pin in pins:
                if placeholder in pin:
                    for instance in self.instances:
                        # replace wildcard with counter of peripheral instance
                        output[instance].append(pin.format(**{self._replace_keyword: str(instance)}))
                else:
                    for instance in self._literal_pin_instances(pin):
                        output[instance].append(pin)
        return output

    def unwrap_channels(self, channels: int | dict[str, int], pins: dict[str, list[str]]) -> dict[str, list[str]]:
        """Convert wildcard channels to actual channels"""
        return self._expand_numbered_placeholder(pins, 'channel', channels)

    def set_mode(self, instance: str, mode: str) -> None:
        """Set mode of interface communication"""
        if instance not in self.instances:
            raise ValueError(f'Instance {instance} not found. Supported instances: {self.instances}')
        supported_modes = [str(i) for i in self.supported_modes.get(instance, [])]
        if not supported_modes:
            raise ValueError(f'Peripheral {self.name} {instance} does not support any modes.')
        mode = str(mode)
        if mode not in supported_modes:
            raise ValueError(
                f'Mode {mode} is not supported for {self.name} {instance}. '
                f'Supported modes: {self.supported_modes[instance]}'
            )
        self.mode[instance] = mode


class LowPowerBase(BasePeripheral):
    """Base class for low power peripherals"""

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        if not (pin.lp or pin.rtc):
            raise ValueError(f'Pin {pin.pin} is not a low power pin.')
        super().check_pin_function(instance, function, pin)


class ADC(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1)
        channels = kwargs.get('channels', 10)
        if isinstance(channels, int):
            self.channels = {i: channels for i in self.instances}
        else:
            self.channels = channels
        self._assigned_pins = self.unwrap_channels(self.channels, self._assigned_pins)
        self.optional_pins = self.assigned_pins  # all pins are optional

    def use(self, function: str, pin: Pin) -> None:
        """Check ADC specific limitations"""
        if function.startswith('ADC2') and not self.used['2']:
            logger.warn('ADC2 cannot be used in combination with Wi-Fi.')
        super().use(function, pin)


class DAC(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1)
        self.optional_pins = self.assigned_pins  # all pins are optional


class SPI(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(
            count,
            assigned_pins,
            universal_pins,
            instances=kwargs.get('subname'),
            _replace_keyword='subname',
            common_prefix=r'.?SPI',
        )
        modes: list | dict = kwargs.get('modes', [])
        # modes can be set in list format if same for all the sub-peripherals or in dict to specify exactly
        if isinstance(modes, list):
            self.supported_modes = {i: modes for i in self.instances}
        elif isinstance(modes, dict):
            self.supported_modes = modes
        self.mode = {i: 'Single SPI' for i in self.instances}
        self.reassignable = True
        opt_filter = re.compile(r'.?SPI\d?(CS\d|DQS)').match
        self.optional_pins = {
            key: list(filter(opt_filter, pins + self._universal_pins.get(key, [])))
            for key, pins in self._assigned_pins.items()
        }
        # In Single SPI mode, make SPIQ and SPID optional as there can be a 3 wire one-way or half-duplex SPI connection
        for instance in self.instances:
            if self.mode[instance] == 'Single SPI':
                self.optional_pins[instance].extend(
                    [pin for pin in self.all_pins[instance] if re.match(r'.?SPI\d?(Q|D)', pin)]
                )

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        return self._filter_pins(self._assigned_pins)

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        return self._filter_pins(self._universal_pins)

    def _filter_pins(self, pins: dict[str, list[str]]) -> dict[str, list[str]]:
        """Filter pins based on the selected mode"""
        out = {}
        if pins:
            for instance in self.instances:
                if self.mode[instance] in ['Single SPI', 'Dual SPI']:
                    regex = re.compile(r'.?SPI\d?(CS\d?|CLK|Q|D)$')
                    out[instance] = [p for p in pins[instance] if regex.match(p)]
                elif self.mode[instance] in ['Quad SPI', 'QPI']:
                    out[instance] = list(
                        filter(lambda x: not (x.endswith(('DQS', 'IO4', 'IO5', 'IO6', 'IO7'))), pins[instance])
                    )
                elif self.mode[instance] in ['Octal SPI', 'OPI']:
                    out[instance] = pins[instance]  # no filtering needed
        return out

    def _literal_pin_instances(self, pin: str) -> list[str]:
        # For SPI instance match SPID but not SPI3D.
        return [str(instance) for instance in self.instances if re.match(rf'{instance}(?!\d).*', pin)]

    def use(self, function: str, pin: Pin) -> None:
        """Check SPI specific limitations; first SPI instance is usually reserved for flash memory and PSRAM"""
        is_esp32 = 'HSPI' in self.instances  # hack: easiest way to check if this class belongs to ESP32 chip
        if re.match(r'SPI(?!\d).*', function) and not self.used['SPI'] and not is_esp32:
            # not true for ESP32, so we skip this warning
            logger.warn(
                'SPI is reserved for flash memory or PSRAM and cannot be used for general purposes. '
                f'Please use {", ".join(self.instances[1:])} instead.'
            )
        super().use(function, pin)

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        """Check if the pin supports the function and if it can be used as input/output"""
        # Pin assignment can be reassigned to any pin with GPIO matrix so ignore checks here
        try:
            super().check_pin_function(instance, function, pin)
        except ValueError:
            logger.note(
                f"{function} of {instance} was assigned to it's non-default pin using GPIO matrix, "
                'which will lead to slower transfer speeds and clock frequencies only up to 40 MHz.'
            )

    def check_required_pins(self, assigned_functions: list[str]) -> None:
        super().check_required_pins(assigned_functions)
        for instance in self.used_instances:
            if self.mode[instance] == 'Single SPI':
                # Check for SPIQ and SPID with possible prefixes (e.g., FSPIQ, FSPID, etc.)
                has_spiq = f'{instance}Q' in assigned_functions
                has_spid = f'{instance}D' in assigned_functions
                if not has_spiq and not has_spid:
                    logger.error(
                        f'{instance}Q or {instance}D is required for Single SPI mode. '
                        f'Please assign at least one of them to {instance}.'
                    )
                elif not has_spiq:
                    logger.note(f'{instance}Q is required for Full Duplex Single SPI mode.')
                elif not has_spid:
                    logger.note(f'{instance}D is required for Full Duplex Single SPI mode.')


class LPSPI(LowPowerBase):
    """Low power SPI peripheral"""

    name = 'Low power SPI'

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix='LP_SPI')


class I2C(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)


class LPI2C(LowPowerBase):
    """Low Power I2C peripheral"""

    name = 'Low power I2C'

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix='LP_I2C')


class I3C(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)


class I2S(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins)

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        if function.endswith('_CLK') and function in self.assigned_pins.get(instance, []):
            if not any(fun.startswith('CLK_OUT') for fun in pin.functions):
                raise ValueError(f'Pin {pin.pin} does not support CLK_OUT, which is required for {function}.')
            return
        super().check_pin_function(instance, function, pin)


class LPI2S(LowPowerBase):
    """Low power I2S peripheral"""

    name = 'Low power I2S'

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix='LP_I2S')


class TOUCH(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = self.assigned_pins  # all pins are optional


class UART(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix=r'U\d.')
        self.optional_pins = self.all_pins  # all pins are optional, as we allow one way UART connections
        self.reassignable = True

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        """Check if the pin supports the function and if it can be used as input/output"""
        # Pin assignment can be reassigned to any pin with GPIO matrix so ignore checks here
        try:
            super().check_pin_function(instance, function, pin)
        except ValueError:
            logger.note(
                f"{function} of {instance} was assigned to it's non-default pin using GPIO matrix. "
                'It is recomanded to use pins from IO MUX if you need very high UART baud rates (over 40 MHz).'
            )

    def check_required_pins(self, assigned_functions: list[str]) -> None:
        super().check_required_pins(assigned_functions)
        for instance in self.used_instances:
            has_rx = f'U{instance}RXD' in assigned_functions
            has_tx = f'U{instance}TXD' in assigned_functions
            if not has_rx and not has_tx:
                # make sure that at least one of RX or TX is assigned if any optional pins are assigned
                logger.error(
                    f'U{instance}RXD or U{instance}TXD is required for UART{instance}. '
                    f'Please assign at least one of them.'
                )
            elif not has_rx:
                logger.note(
                    f'U{instance}RXD is missing. The chip will be able to only transmit data via UART '
                    'in the current configuration.'
                )
            elif not has_tx:
                logger.note(
                    f'U{instance}TXD is missing. The chip will be able to only receive data via UART '
                    'in the current configuration.'
                )


class LPUART(LowPowerBase):
    """Low power UART peripheral"""

    name = 'Low power UART'

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix='LP_UART')
        self.optional_pins = self.all_pins  # all pins are optional, as we allow one way UART connections


class SDIO(BasePeripheral):
    """SDIO slave peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix='SDIO', **kwargs)
        self.supported_modes = kwargs.get('data_width', {str(i): [1] for i in self.instances})
        self.mode = {str(i): 1 for i in self.instances}
        self.mode_label = 'Data width'
        self._assigned_pins = self._unwrap_data_pins()

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        """Dynamic getter for assigned pins, based on data width of the peripheral instance"""
        pins = {}
        for instance in self.instances:
            width: int = int(self.mode.get(instance, 0)) - 1
            regex = re.compile(rf'SDIO\d_(CLK|CMD|DATA[0-{width}])')
            pins[instance] = [pin for pin in self._assigned_pins[instance] if regex.match(pin)]
        return pins

    def _unwrap_data_pins(self) -> dict[str, list[str]]:
        return self._expand_data_width_pins(self._assigned_pins)

    def set_mode(self, instance: str, mode: str) -> None:
        super().set_mode(instance, mode)
        self.mode[instance] = int(mode)


class SDMMC(BasePeripheral):
    """SD/SDIO/MMC host controller peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1, common_prefix=r'SDHOST_.*_\d', **kwargs)
        self.supported_modes = kwargs.get('data_width', {str(i): [1] for i in self.instances})
        self.mode = {str(i): 1 for i in self.instances}
        self.mode_label = 'Data width'
        self._universal_pins = self._unwrap_data_pins(self._universal_pins)
        if self._assigned_pins:
            self._assigned_pins = self._unwrap_data_pins(self._assigned_pins)
        self.optional_pins = self.unwrap_pins(
            [
                'SDHOST_RST_{count}',
                'SDHOST_CARD_WRITE_PRT_{count}',
                'SDHOST_CARD_DETECT_{count}',
                'SDHOST_DATA_STROBE_{count}',
                'SDHOST_CARD_INT_{count}',
                'SDHOST_CCMD_OD_PULLUP_EN_{count}',
            ]
        )

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        """Dynamic getter for universal pins, based on data width of the peripheral instance"""
        pins = {}
        for instance in self.instances:
            width: int = int(self.mode.get(instance, 0)) - 1
            regex = re.compile(rf'.+(CDATA_\d[0-{width}]|CCLK|CCMD|CARD|STROBE|RST|SDIO).*')
            pins[instance] = [pin for pin in self._universal_pins[instance] if regex.match(pin)]
        return pins

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        """Dynamic getter for assigned pins, based on data width of the peripheral instance"""
        pins = {}
        if self._assigned_pins:
            for instance in self.instances:
                width: int = int(self.mode.get(instance, 0)) - 1
                regex = re.compile(rf'.+(CDATA_\d[0-{width}]|CCLK|CCMD|CARD|STROBE|RST|SDIO).*')
                pins[instance] = [pin for pin in self._assigned_pins[instance] if regex.match(pin)]
        return pins

    def _unwrap_data_pins(self, orig_pins: dict[str, list[str]]) -> dict[str, list[str]]:
        return self._expand_data_width_pins(orig_pins)

    def set_mode(self, instance: str, mode: str) -> None:
        super().set_mode(instance, mode)
        self.mode[instance] = int(mode)

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        if re.match(r'SDHOST_(CDATA|CCMD)_\d+', function) is not None:
            logger.note(f'Function {function} requires 10k pull-up resistor on pin GPIO{pin.pin}.')
        return super().check_pin_function(instance, function, pin)


class RMT(BasePeripheral):
    """Remote Control Transceiver peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = self.universal_pins  # all pins are optional, based on usage


class LEDC(BasePeripheral):
    """LED PWM peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(
            count,
            assigned_pins,
            universal_pins,
            instances=kwargs.get('subname', ['LS']),
            _replace_keyword='subname',
            **kwargs,
        )
        self._universal_pins = self.unwrap_channels(kwargs.get('channels', 0), self._universal_pins)
        self.optional_pins = self.universal_pins  # all pins are optional

    def _literal_pin_instances(self, pin: str) -> list[str]:
        """Single low-speed block uses instance 'LS', not '0', so literals map to named instances."""
        return list(self.instances)


class MCPWM(BasePeripheral):
    """Motor Control PWM peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self._universal_pins = self.unwrap_channels(kwargs.get('channels', 0), self._universal_pins)
        self.optional_pins = self.universal_pins  # all pins are optional


class PCNT(BasePeripheral):
    """Pulse Counter peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self._universal_pins = self.unwrap_channels(kwargs.get('channels', 0), self._universal_pins)
        self._used_pins: list[str] = []

    def required_pins(self, instance: str) -> list[str]:
        """Return all required pins for a peripheral instance"""
        if instance not in self.instances:
            raise ValueError(f'Instance {instance} not found.')

        required_signals = set(self._used_pins)
        for signal in self._used_pins:
            # if SIG is used the corresponding CTRL signal is also required (same channel and instance) and vice versa
            match = re.match(rf'(PCNT_(SIG|CTRL)_CH\d+_IN{instance})', signal)
            if match:
                base_signal = match.group(1)
                if 'SIG' in base_signal:
                    pair_signal = base_signal.replace('SIG', 'CTRL')
                else:
                    pair_signal = base_signal.replace('CTRL', 'SIG')
                required_signals.add(pair_signal)

        return list(required_signals)

    def use(self, function: str, pin: Pin) -> None:
        self._used_pins.append(function)
        return super().use(function, pin)


class JTAG(BasePeripheral):
    """JTAG peripheral"""


class EMAC(BasePeripheral):
    """Ethernet MAC peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.supported_modes = {'0': kwargs.get('modes', [])}
        self.set_mode('0', 'RMII external CLK')

    @property
    def assigned_pins(self) -> dict[str, list[str]]:
        # shared pins for RMII and MII
        pins = ['TX_EN', 'TXD0', 'TXD1', 'RX_DV', 'RXD0', 'RXD1']
        if self.mode['0'] == 'RMII internal CLK':
            if 'EMAC_CLK_OUT' in self._assigned_pins['0']:  # esp32
                pins.append('CLK_OUT')
            else:  # esp32p4; REF_50M_CLK is output and has to be looped back to RMII_CLK
                pins.extend(['REF_50M_CLK', 'RMII_CLK'])
        elif self.mode['0'] == 'RMII external CLK':
            # input clock pin
            if 'EMAC_TX_CLK' in self._assigned_pins['0']:  # esp32
                pins.append('TX_CLK')
            else:  # esp32p4
                pins.append('RMII_CLK')
        elif self.mode['0'] == 'MII':
            # MII is still not supported by ESP-IDF, but we allow it in case someone wants to implement a driver
            # additional pins needed for MII; on esp32 MII pins are using MUX, but on esp32p4 they use matrix
            if 'EMAC_RXD2' in self._assigned_pins['0']:
                pins.extend(['TX_CLK', 'RX_CLK', 'TXD2', 'TXD3', 'RX_ER', 'RXD2', 'RXD3', 'TX_ER'])
        # sort pins so similar pins are after each other; mainly for additional TX and RX in MII
        pins.sort()
        # add prefixes to the pins, for better naming in the config
        return {'0': [f'EMAC_{i}' for i in pins]}

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        pins = ['MDC', 'MDIO']
        if self.mode['0'] == 'MII':
            pins.extend(['COL', 'CRS'])
            # additional pins needed for MII; on esp32 MII pins are using MUX, but on esp32p4 they use matrix
            if 'EMAC_RXD2' in self._universal_pins['0']:
                pins.extend(['RX_CLK', 'TX_CLK', 'TXD2', 'TXD3', 'RX_ER', 'RXD2', 'RXD3', 'TX_ER'])
        return {'0': [f'EMAC_{i}' for i in pins]}

    def check_pin_function(self, instance: str, function: str, pin: Pin) -> None:
        if function == 'EMAC_CLK_OUT':
            # Note: CLK_OUT1 is experimental and on ESP32 is shared with RX_CLK signal on the same GPIO
            if not any(fun in ['CLK_OUT1', 'EMAC_CLK_OUT', 'EMAC_CLK_OUT_180'] for fun in pin.functions):
                raise ValueError(f'Pin {pin.pin} does not support clock out, which is required for {function}.')
        if function == 'EMAC_REF_50M_CLK':
            logger.note(
                'REF_50M_CLK has to be looped back on PCB to EMAC_RMII_CLK when using RMII with internal clock.'
            )
        if function in ['EMAC_MDC', 'EMAC_MDIO', 'EMAC_CRS', 'EMAC_COL']:
            # check if GPIO supports output
            if not pin.is_output:
                raise ValueError(f'Pin {pin.pin} does not support output, which is required for {function}.')
        if function in ['EMAC_MDIO']:
            if not pin.is_input:
                raise ValueError(f'Pin {pin.pin} does not support input, which is required for {function}.')
        super().check_pin_function(instance, function, pin)

    def set_mode(self, instance: str, mode: str) -> None:
        super().set_mode(instance, mode)
        # TODO: We might make MDC and MDIO optional in the future with warning if not used
        if mode == 'MII':
            self.optional_pins = {'0': ['EMAC_TX_ER']}
        else:
            self.optional_pins = {'0': []}


class CLKOUT(BasePeripheral):
    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, start_cnt=1, common_prefix='CLK_OUT', **kwargs)
        self.optional_pins = self.assigned_pins  # all pins are optional


class TWAI(BasePeripheral):
    """Two-Wire Automotive Interface peripheral (CAN)"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, **kwargs)
        self.optional_pins = {i: ['TWAI_BUS_OFF_ON', 'TWAI_CLKOUT'] for i in self.instances}


class XTAL32K(BasePeripheral):
    """32 kHz crystal oscillator peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix='XTAL_32K_', **kwargs)
        # based on usage, pins can be optional
        self.optional_pins = self.assigned_pins  # all pins are optional


class USBOTG(BasePeripheral):
    """USB OTG Full-Speed peripheral"""

    name = 'USB OTG Full-Speed'

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix=r'USB_OTG', **kwargs)
        required_values = ['USB_OTG_D-', 'USB_OTG_D+']
        pins_0 = self.assigned_pins.get('0') or []
        self.optional_pins = {'0': [val for val in pins_0 if val not in required_values]}
        # TODO: On esp32p4, this can be exchanged with USBSERIALJTAG peripheral, but efuse has to be burn


class USBSERIALJTAG(BasePeripheral):
    """USB Serial/JTAG peripheral"""

    name = 'USB Serial/JTAG'

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix=r'USB(?!_OTG).', **kwargs)
        required_values = ['USB_D-', 'USB_D+']
        pins_0 = self.assigned_pins.get('0') or []
        self.optional_pins = {'0': [val for val in pins_0 if val not in required_values]}


class LCDCAM(BasePeripheral):
    """LCD and Camera Controller peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(
            count,
            assigned_pins,
            universal_pins,
            instances=kwargs.get('subname'),
            _replace_keyword='subname',
            common_prefix=r'LCD|CAM',
        )
        # modes can be set in list format if same for all the sub-peripherals or in dict to specify exactly
        modes: list | dict = kwargs.get('modes', [])
        if isinstance(modes, list):
            self.supported_modes = {i: modes for i in self.instances}
        elif isinstance(modes, dict):
            self.supported_modes = modes
        self.mode = {i: self.supported_modes[i][0] for i in self.instances}
        self._universal_pins = self.unwrap_channels(kwargs.get('channels', 16), self._universal_pins)

    def _literal_pin_instances(self, pin: str) -> list[str]:
        return [str(instance) for instance in self.instances if instance in pin]

    def unwrap_channels(self, channels: dict[str, int] | int, pins: dict[str, list[str]]) -> dict[str, list[str]]:
        """Convert wildcard channels to actual channels, e.g.
        {subname}_DATA{{channel}} -> {LCD: [LCD_DATA0, LCD_DATA1... ]}
        """
        return self._expand_numbered_placeholder(pins, 'channel', channels)

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        pins = {}
        for instance in self.instances:
            if '8 bit' in str(self.mode[instance]):
                pins[instance] = list(
                    filter(
                        lambda x: not x.endswith(tuple(str(x) for x in range(8, 24))),
                        self._universal_pins[instance],
                    )
                )
            elif '16 bit' in str(self.mode[instance]):
                pins[instance] = list(
                    filter(
                        lambda x: not x.endswith(tuple(str(x) for x in range(16, 24))),
                        self._universal_pins[instance],
                    )
                )
            elif '24 bit' in str(self.mode[instance]):
                pins[instance] = self._universal_pins[instance]
        return pins

    def set_mode(self, instance: str, mode: str) -> None:
        super().set_mode(instance, mode)
        if instance == 'CAM':
            if 'Slave' in mode:
                self.optional_pins[instance] = ['CAM_CLK']
            else:
                self.optional_pins[instance] = []

    def check_required_pins(self, assigned_functions: list[str]) -> None:
        super().check_required_pins(assigned_functions)
        for instance in self.used_instances:
            if instance == 'CAM':
                if 'CAM_CLK' in assigned_functions and 'Slave' in str(self.mode[instance]):
                    logger.warn('CAM_CLK is not used in Slave mode for CAM.')
            elif instance == 'LCD':
                # TODO: Consider printing warnings for using pins for mixed modes
                if any(f in assigned_functions for f in ['LCD_H_SYNC', 'LCD_V_SYNC', 'LCD_H_ENABLE']):
                    if not all(f in assigned_functions for f in ['LCD_H_SYNC', 'LCD_V_SYNC', 'LCD_H_ENABLE']):
                        logger.error(
                            'LCD_H_SYNC, LCD_V_SYNC, and LCD_H_ENABLE are required '
                            'when using parallel RGB mode for LCD.'
                        )
                elif any(f in assigned_functions for f in ['LCD_CD', 'LCD_CS']):
                    if not all(f in assigned_functions for f in ['LCD_CD', 'LCD_CS']):
                        logger.error('LCD_CD and LCD_CS are required when using 8080 / MOTO6800 mode for LCD.')


class PARLIO(BasePeripheral):
    """Parallel IO peripheral"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix='PARL', **kwargs)
        self.supported_modes = {'0': kwargs.get('data_width', [1])}
        self.mode = {str(i): 1 for i in self.instances}
        self.mode_label = 'Data width'
        self._universal_pins = self._unwrap_data_pins()
        # All TX and RX pins are initially optional - they become required based on usage
        # This allows TX-only, RX-only, or duplex modes
        self.optional_pins = self.all_pins

    @property
    def universal_pins(self) -> dict[str, list[str]]:
        """Dynamic getter for universal pins, based on data width of the peripheral instance"""
        pins = {}
        for instance in self.instances:
            width: int = int(self.mode.get(instance, 0)) - 1
            if width > 10:  # change regex for double digit data channels
                regex = re.compile(rf'PARL_(RX|TX)_(CLK.*|DATA([0-9]|1[0-{width - 10}]))$')
            else:
                regex = re.compile(rf'PARL_(RX|TX)_(CLK.*|DATA[0-{width}])$')
            pins[instance] = [pin for pin in self._universal_pins[instance] if regex.match(pin)]
        return pins

    def _unwrap_data_pins(self) -> dict[str, list[str]]:
        return self._expand_data_width_pins(self._universal_pins)

    def set_mode(self, instance: str, mode: str) -> None:
        super().set_mode(instance, mode)
        self.mode[instance] = int(mode)

    def check_required_pins(self, assigned_functions: list[str]) -> None:
        """Check required pins based on TX/RX usage"""
        super().check_required_pins(assigned_functions)
        for instance in self.used_instances:
            # Check which direction is being used
            has_tx = any(f.startswith('PARL_TX_') for f in assigned_functions)
            has_rx = any(f.startswith('PARL_RX_') for f in assigned_functions)

            if not has_tx and not has_rx:
                logger.error(
                    'PARLIO requires at least TX or RX pins to be assigned. Please assign at least one of them.'
                )
                continue

            # Check TX requirements if TX is used
            if has_tx:
                tx_data_pins = [f for f in assigned_functions if f.startswith('PARL_TX_DATA')]
                if not tx_data_pins:
                    logger.error('At least one PARL_TX_DATA pin is required when using TX mode for PARLIO.')
                if len(tx_data_pins) != self.mode[instance]:
                    logger.error(
                        f'Number of PARL_TX_DATA ({len(tx_data_pins)}) pins must match '
                        f'the data width ({self.mode[instance]}) for PARLIO.'
                    )

            # Check RX requirements if RX is used
            if has_rx:
                rx_data_pins = [f for f in assigned_functions if f.startswith('PARL_RX_DATA')]
                if not rx_data_pins:
                    logger.error('At least one PARL_RX_DATA pin is required when using RX mode for PARLIO.')
                if len(rx_data_pins) != self.mode[instance]:
                    logger.error(
                        f'Number of PARL_RX_DATA ({len(rx_data_pins)}) pins must match '
                        f'the data width ({self.mode[instance]}) for PARLIO.'
                    )


class ANACOMP(BasePeripheral):
    """Analog PAD Voltage Comparator"""

    def __init__(
        self, count: int, assigned_pins: list[str] = None, universal_pins: list[str] = None, **kwargs: Any
    ) -> None:
        super().__init__(count, assigned_pins, universal_pins, common_prefix=r'ANA_COMP\d', **kwargs)
        # ANA_COMPx_PAD0 is optional reference (internal one can be used to replace)
        self.optional_pins = {i: [f'ANA_COMP{i}_PAD0'] for i in self.instances}
