# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
from typing import cast

import pytest
from click import Command
from click.testing import CliRunner

from esp_gpio_tool_cli.__main__ import main as espins_cli
from esp_gpio_tool_cli.checker import run_check
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS
from esp_gpio_tool_cli.logger import Logger

Logger().use_unicode(False)


def run(config: str) -> list[str]:
    """Run the checker with the given config and log returned file"""
    out = run_check(config)
    # newline to separate the output from test name
    print('\n' + '\n'.join(out))
    return out


def test_missing_chip() -> None:
    config = """
    36: ADC1_CH0
    37: ADC1_CH1
    """
    out = run(config)
    assert 'Warning: Chip name not found in input file. Assuming ESP32.' in out


def test_invalid_chip() -> None:
    config = """
    chip: foo
    0: ADC1_CH0
    1: ADC1_CH1
    """
    with pytest.raises(SystemExit) as exc_info:
        run(config)
    assert exc_info.value.args[0] == f"Error: Invalid chip: 'foo'. Supported chips: {SUPPORTED_CHIPS}."


@pytest.mark.parametrize('chip', SUPPORTED_CHIPS)
def test_duplicate_pin(chip: str) -> None:
    config = f"""
    chip: {chip}
    0: ADC1_CH0
    0: TOUCH1
    """
    with pytest.raises(SystemExit) as exc_info:
        run(config)
    assert exc_info.value.args[0] == "Error: Invalid format: Duplicate '0' key found in YAML."


def test_valid_config() -> None:
    config = """
    chip: esp32
    36: ADC1_CH0
    37: ADC1_CH1
    """
    result = run(config)
    assert 'All checks passed.' in result


def test_valid_config_multiple_functions() -> None:
    config = """
    chip: esp32
    36: ADC1_CH0
    3: [LEDC_HS_SIG_OUT0, LEDC_HS_SIG_OUT1, RMT_SIG_IN0]
    """
    result = run(config)
    assert (
        'Warning: Pin 3 has been used multiple times, reusing pins is not recommended. '
        'Assigned functions: LEDC_HS_SIG_OUT0, LEDC_HS_SIG_OUT1, RMT_SIG_IN0' in result
    )


def test_invalid_pin_format() -> None:
    config = """
    chip: esp32
    0: INVALID_FUNCTION
    """
    out = run(config)
    assert 'Error: Function INVALID_FUNCTION not found in peripherals for esp32.' in out


def test_wrong_pin_function() -> None:
    config = """
    chip: esp32
    0: ADC1_CH0
    """
    out = run(config)
    assert 'Error: Pin 0 does not support function ADC1_CH0.' in out


def test_nonexisting_pin() -> None:
    config = """
    chip: esp32
    24: ADC1_CH0
    """
    out = run(config)
    assert 'Error: Pin 24 not found for esp32.' in out


def test_wrong_function_correct_prefix() -> None:
    config = """
    chip: esp32
    36: ADC1_FOO
    """
    out = run(config)
    assert 'Error: Function ADC1_FOO not found in peripheral ADC.' in out


def test_output_notsupported() -> None:
    config = """
    chip: esp32
    36: OUTPUT
    """
    out = run(config)
    assert 'Error: Pin 36 does not support output mode.' in out


def test_I2S_clk() -> None:
    config = """
    chip: esp32
    21: I2S0_CLK
    22: I2S0_WS
    23: I2S0_SD
    """
    out = run(config)
    assert 'Error: Pin 21 does not support CLK_OUT, which is required for I2S0_CLK.' in out


def test_SPI_modes() -> None:
    config = """
    chip: esp32

    peripheral:
        SPI:
            HSPI: QSPI

    2:  HSPIWP
    4:  HSPIHD
    12: HSPIQ
    13: HSPID
    14: HSPICLK
    15: HSPICS0
    """
    out = run(config)
    assert 'Error' not in out


@pytest.mark.parametrize('mode', ['1', '4'])
def test_SDIO_mode(mode: str) -> None:
    config = f"""
    chip: esp32

    peripheral:
        SDIO:
            0: {mode}

    6:  SDIO0_CLK
    7:  SDIO0_DATA0
    8:  SDIO0_DATA1
    9:  SDIO0_DATA2
    10: SDIO0_DATA3
    11: SDIO0_CMD
    """
    out = '\n'.join(run(config))
    assert 'Error' not in out


def test_SDIO_mode_missing_pins() -> None:
    config = """
    chip: esp32

    peripheral:
        SDIO:
            0: 4

    6:  SDIO0_CLK
    7:  SDIO0_DATA0
    11: SDIO0_CMD
    """
    out = '\n'.join(run(config))
    for pin in ['SDIO0_DATA1', 'SDIO0_DATA2', 'SDIO0_DATA3']:
        assert f'Error: Required function {pin} from peripheral SDIO is not assigned to any pin.' in out


def test_soc_not_found() -> None:
    config = """
    chip: esp32
    soc: foo
    """
    with pytest.raises(SystemExit) as exc_info:
        run(config)
    assert 'Error: SoC "foo" is not supported variant of esp32. Supported SoCs: ' in exc_info.value.args[0]


@pytest.mark.parametrize('soc, nc_pins', [('ESP32-PICO-V3', [16, 17, 18, 23]), ('ESP32-D0WD-V3', [20])])
def test_soc_filter_gpios(soc: str, nc_pins: list[int]) -> None:
    config = f"""
    chip: esp32
    soc: {soc}
    """
    for pin in nc_pins:
        config += f'\n    {pin}: ADC1_CH0'
    out = run(config)
    for pin in nc_pins:
        assert f'Error: Pin {pin} not found for esp32({soc}).' in out


def test_flash_pin_reuse() -> None:
    config = """
    chip: esp32
    soc: ESP32-PICO-V3
    6: U1CTS
    """
    out = run(config)
    assert (
        'Warning: Pin 6 has been used multiple times, reusing pins is not recommended. '
        'Assigned functions: FLASH/PSRAM, U1CTS' in out
    )


def test_sdmmc() -> None:
    config = """
    chip: esp32s3
    peripheral:
        SDMMC:
            1: 4
    0: SDHOST_CCLK_1
    1: SDHOST_CCMD_1
    2: SDHOST_CDATA_10
    3: SDHOST_CDATA_11
    4: SDHOST_CDATA_12
    5: SDHOST_CDATA_13
    """
    out = run(config)
    assert 'Error' not in ''.join(out)
    for idx, pin in enumerate(['CCMD_1', 'CDATA_10', 'CDATA_11', 'CDATA_12', 'CDATA_13']):
        assert f'Note: Function SDHOST_{pin} requires 10k pull-up resistor on pin GPIO{idx + 1}.' in out


def test_reuse_debug_pins() -> None:
    config = """
    chip: esp32s3
    19: OUTPUT  # USB_D+
    39: OUTPUT  # MTCK (JTAG)
    43: OUTPUT  # U0TXD (Serial)
    """
    out = '\n'.join(run(config))
    assert 'Error' not in out
    assert 'Warning: Pin 19 is reserved for JTAG debugging or USB.' in out
    assert 'Warning: Pin 39 is reserved for JTAG debugging or USB.' in out
    assert 'Warning: Pin 43 is reserved for serial debug/programming.' in out


def test_allow_one_way_uart() -> None:
    config = """
    chip: esp32
    1: U0RXD
    """
    out = '\n'.join(run(config))
    assert 'Error' not in out
    assert (
        'Note: U0TXD is missing. The chip will be able to only receive data via UART in the current configuration.'
        in out
    )


def test_uart_no_rx_tx() -> None:
    """Assing only DTR and expect error for missing RXD or TXD"""
    config = """
    chip: esp32
    1: U0DTR
    """
    out = '\n'.join(run(config))
    assert 'Error: U0RXD or U0TXD is required for UART0.' in out


def test_allow_one_way_spi() -> None:
    config = """
    chip: esp32
    1: HSPIQ
    2: HSPICLK
    """
    out = '\n'.join(run(config))
    assert 'Error' not in out
    assert 'Note: HSPID is required for Full Duplex Single SPI mode.' in out


def test_spi_no_q_d() -> None:
    config = """
    chip: esp32
    1: HSPICLK
    """
    out = '\n'.join(run(config))
    assert 'Error: HSPIQ or HSPID is required for Single SPI mode.' in out


def test_lcd_24bit_master_tx() -> None:
    """Test LCD with 24-bit Master TX Mode"""
    config = """
    chip: esp32p4
    peripheral:
        LCDCAM:
            LCD: 24 bit - Master TX Mode
    16: LCD_PCLK
    17: LCD_CD
    18: LCD_CS
    19: LCD_VSYNC
    20: LCD_HSYNC
    21: LCD_DE
    """
    # Add 24 data pins (LCD has 24 channels)
    for i in range(24):
        config += f'\n    {22 + i}: LCD_DATA{i}'
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_cam_16bit_slave_rx() -> None:
    """Test CAM with 16-bit Slave RX Mode"""
    config = """
    chip: esp32p4
    peripheral:
        LCDCAM:
            CAM: 16 bit - Slave RX Mode
    16: CAM_PCLK
    17: CAM_VSYNC
    18: CAM_HSYNC
    19: CAM_DE
    """
    # Add 16 data pins (CAM has 16 channels)
    for i in range(16):
        config += f'\n    {20 + i}: CAM_DATA{i}'
    result = run(config)
    assert 'Error' not in '\n'.join(result)


@pytest.mark.parametrize('data_width', ['1', '2', '4', '8', '16'])
def test_parlio_data_width(data_width: str) -> None:
    """Test PARLIO with different data widths (TX-only mode)"""
    config = f"""
    chip: esp32p4
    peripheral:
        PARLIO:
            0: {data_width}
    16: PARL_TX_CLK_IN
    17: PARL_TX_CLK_OUT
    """
    # Add data pins based on width (pins are DATA0, DATA1, etc.)
    for i in range(int(data_width)):
        config += f'\n    {18 + i}: PARL_TX_DATA{i}'
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_parlio_rx_only() -> None:
    """Test PARLIO in RX-only mode"""
    config = """
    chip: esp32p4
    peripheral:
        PARLIO:
            0: 4
    16: PARL_RX_CLK_IN
    17: PARL_RX_CLK_OUT
    18: PARL_RX_DATA0
    19: PARL_RX_DATA1
    20: PARL_RX_DATA2
    21: PARL_RX_DATA3
    """
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_parlio_duplex() -> None:
    """Test PARLIO in duplex mode (both TX and RX)"""
    config = """
    chip: esp32p4
    peripheral:
        PARLIO:
            0: 4
    16: PARL_TX_CLK_IN
    17: PARL_TX_CLK_OUT
    18: PARL_TX_DATA0
    19: PARL_TX_DATA1
    20: PARL_TX_DATA2
    21: PARL_TX_DATA3
    22: PARL_RX_CLK_IN
    23: PARL_RX_CLK_OUT
    24: PARL_RX_DATA0
    25: PARL_RX_DATA1
    26: PARL_RX_DATA2
    27: PARL_RX_DATA3
    """
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_parlio_no_direction() -> None:
    """Test PARLIO error when no TX or RX pins are assigned"""
    config = """
    chip: esp32p4
    peripheral:
        PARLIO:
            0: 4
    16: PARL_TX_CLK_OUT
    """
    out = '\n'.join(run(config))
    assert 'Error: At least one PARL_TX_DATA pin is required when using TX mode for PARLIO.' in out


def test_esp32_emac_rmii_external_clk() -> None:
    """Test valid EMAC RMII external CLK mode configuration"""
    config = """
    chip: esp32
    peripheral:
        EMAC:
            0: RMII external CLK
    0: EMAC_TX_CLK
    21: EMAC_TX_EN
    19: EMAC_TXD0
    22: EMAC_TXD1
    27: EMAC_RX_DV
    25: EMAC_RXD0
    26: EMAC_RXD1
    12: EMAC_MDC
    15: EMAC_MDIO
    """
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_esp32_emac_rmii_internal_clk() -> None:
    """Test valid EMAC RMII internal CLK mode configuration"""
    config = """
    chip: esp32
    peripheral:
        EMAC:
            0: RMII internal CLK
    0: EMAC_TX_CLK
    21: EMAC_TX_EN
    19: EMAC_TXD0
    22: EMAC_TXD1
    27: EMAC_RX_DV
    25: EMAC_RXD0
    26: EMAC_RXD1
    16: EMAC_CLK_OUT
    12: EMAC_MDC
    15: EMAC_MDIO
    """
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_esp32_emac_mii_valid() -> None:
    """Test valid EMAC MII mode configuration"""
    config = """
    chip: esp32
    peripheral:
        EMAC:
            0: MII
    0: EMAC_TX_CLK
    5: EMAC_RX_CLK
    21: EMAC_TX_EN
    19: EMAC_TXD0
    22: EMAC_TXD1
    14: EMAC_TXD2
    12: EMAC_TXD3
    13: EMAC_RX_ER
    27: EMAC_RX_DV
    25: EMAC_RXD0
    26: EMAC_RXD1
    1: EMAC_RXD2
    15: EMAC_RXD3
    4: EMAC_TX_ER
    16: EMAC_MDC
    17: EMAC_MDIO
    18: EMAC_CRS
    20: EMAC_COL
    """
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_esp32_emac_mii_with_universal_pins() -> None:
    """Test EMAC MII mode with universal pins (MDC, MDIO, CRS, COL)"""
    config = """
    chip: esp32
    peripheral:
        EMAC:
            0: MII
    0: EMAC_TX_CLK
    5: EMAC_RX_CLK
    21: EMAC_TX_EN
    19: EMAC_TXD0
    22: EMAC_TXD1
    14: EMAC_TXD2
    12: EMAC_TXD3
    13: EMAC_RX_ER
    27: EMAC_RX_DV
    25: EMAC_RXD0
    26: EMAC_RXD1
    1: EMAC_RXD2
    15: EMAC_RXD3
    4: EMAC_TX_ER
    2: EMAC_MDC
    3: EMAC_MDIO
    7: EMAC_CRS
    8: EMAC_COL
    """
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_esp32_emac_rmii_internal_clk_missing_clk_out() -> None:
    """Test EMAC RMII internal CLK mode without CLK_OUT pin"""
    config = """
    chip: esp32
    peripheral:
        EMAC:
            0: RMII internal CLK
    0: EMAC_TX_CLK
    21: EMAC_TX_EN
    19: EMAC_TXD0
    22: EMAC_TXD1
    27: EMAC_RX_DV
    25: EMAC_RXD0
    26: EMAC_RXD1
    2: EMAC_MDC
    3: EMAC_MDIO
    """
    out = '\n'.join(run(config))
    assert 'Error: Required function EMAC_CLK_OUT from peripheral EMAC is not assigned to any pin.' in out


def test_esp32_emac_rmii_wrong_data_pin() -> None:
    """ESP32 RMII with wrong data pin assignment"""
    config = """
    chip: esp32
    peripheral:
        EMAC:
            0: RMII external CLK
    0: EMAC_TX_CLK
    21: EMAC_TX_EN
    4: EMAC_TXD0
    22: EMAC_TXD1
    27: EMAC_RX_DV
    25: EMAC_RXD0
    26: EMAC_RXD1
    """
    out = '\n'.join(run(config))
    assert 'Error: Pin 4 does not support function EMAC_TXD0.' in out


def test_esp32_emac_mii_missing_mdc_mdio() -> None:
    """ESP32 MII mode missing MDC/MDIO - error case from documentation"""
    config = """
    chip: esp32
    peripheral:
        EMAC:
            0: MII
    0: EMAC_TX_CLK
    5: EMAC_RX_CLK
    21: EMAC_TX_EN
    19: EMAC_TXD0
    22: EMAC_TXD1
    14: EMAC_TXD2
    12: EMAC_TXD3
    13: EMAC_RX_ER
    27: EMAC_RX_DV
    25: EMAC_RXD0
    26: EMAC_RXD1
    1: EMAC_RXD2
    15: EMAC_RXD3
    4: EMAC_TX_ER
    """
    out = '\n'.join(run(config))
    # MDC and MDIO are required for PHY management
    assert 'Error: Required function EMAC_MDC from peripheral EMAC is not assigned to any pin.' in out
    assert 'Error: Required function EMAC_MDIO from peripheral EMAC is not assigned to any pin.' in out


def test_esp32p4_emac_rmii_valid() -> None:
    """Test valid EMAC RMII mode configuration"""
    config = """
    chip: esp32p4
    peripheral:
        EMAC:
            0: RMII external CLK
    28: EMAC_RX_DV
    29: EMAC_RXD0
    30: EMAC_RXD1
    33: EMAC_TX_EN
    34: EMAC_TXD0
    35: EMAC_TXD1
    32: EMAC_RMII_CLK
    15: EMAC_MDIO
    14: EMAC_MDC
    """
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_esp32p4_emac_mii_valid() -> None:
    """Test valid EMAC MII mode configuration"""
    config = """
    chip: esp32p4
    peripheral:
        EMAC:
            0: MII
    28: EMAC_RX_DV
    29: EMAC_RXD0
    30: EMAC_RXD1
    31: EMAC_RX_ER
    33: EMAC_TX_EN
    34: EMAC_TXD0
    35: EMAC_TXD1
    36: EMAC_TX_ER
    32: EMAC_TX_CLK
    17: EMAC_RX_CLK
    18: EMAC_TXD2
    19: EMAC_TXD3
    20: EMAC_RXD2
    21: EMAC_RXD3
    12: EMAC_MDC
    15: EMAC_MDIO
    14: EMAC_CRS
    13: EMAC_COL
    """
    result = run(config)
    assert 'Error' not in '\n'.join(result)


def test_esp32p4_emac_rmii_missing_pins() -> None:
    """Test EMAC RMII mode with missing required pins"""
    config = """
    chip: esp32p4
    peripheral:
        EMAC:
            0: RMII external CLK
    28: EMAC_RX_DV
    29: EMAC_RXD0
    33: EMAC_TX_EN
    """
    out = '\n'.join(run(config))
    # Should complain about missing required pins
    for pin in ['EMAC_MDIO', 'EMAC_MDC', 'EMAC_RMII_CLK', 'EMAC_RXD1', 'EMAC_TXD0', 'EMAC_TXD1']:
        assert f'Error: Required function {pin} from peripheral EMAC is not assigned to any pin.' in out


def test_esp32p4_emac_mii_missing_pins() -> None:
    """Test EMAC MII mode with missing required pins"""
    config = """
    chip: esp32p4
    peripheral:
        EMAC:
            0: MII
    28: EMAC_RX_DV
    29: EMAC_RXD0
    30: EMAC_RXD1
    33: EMAC_TX_EN
    34: EMAC_TXD0
    35: EMAC_TXD1
    """
    out = '\n'.join(run(config))
    # Should complain about missing MII-specific pins
    for pin in ['EMAC_RX_CLK', 'EMAC_TXD2', 'EMAC_TXD3', 'EMAC_RXD2', 'EMAC_RXD3']:
        assert f'Error: Required function {pin} from peripheral EMAC is not assigned to any pin.' in out


def test_esp32p4_emac_invalid_mode() -> None:
    """Test EMAC with invalid mode"""
    config = """
    chip: esp32p4
    peripheral:
        EMAC:
            0: InvalidMode
    """
    out = run(config)
    assert 'Error: Mode InvalidMode is not supported for EMAC 0.' in ''.join(out)


def test_esp32p4_emac_rmii_internal_clk_loopback() -> None:
    """ESP32-P4 RMII with internal 50 MHz clock and loopback"""
    config = """
    chip: esp32p4
    peripheral:
        EMAC:
            0: RMII internal CLK
    23: EMAC_REF_50M_CLK
    32: EMAC_RMII_CLK
    40: EMAC_TX_EN
    41: EMAC_TXD0
    42: EMAC_TXD1
    45: EMAC_RX_DV
    46: EMAC_RXD0
    47: EMAC_RXD1
    48: EMAC_RX_ER
    16: EMAC_MDC
    17: EMAC_MDIO
    """
    result = '\n'.join(run(config))
    assert (
        'Note: REF_50M_CLK has to be looped back on PCB to EMAC_RMII_CLK when using RMII with internal clock.' in result
    )
    assert 'Error' not in result


def test_esp32p4_emac_rmii_invalid_ref_clk_pin() -> None:
    """ESP32-P4 RMII with invalid REF_CLK pin"""
    config = """
    chip: esp32p4
    peripheral:
        EMAC:
            0: RMII external CLK
    33: EMAC_RMII_CLK
    40: EMAC_TX_EN
    34: EMAC_TXD0
    35: EMAC_TXD1
    28: EMAC_RX_DV
    29: EMAC_RXD0
    30: EMAC_RXD1
    31: EMAC_RX_ER
    """
    out = '\n'.join(run(config))
    # EMAC_RMII_CLK can only be on GPIO32, GPIO44, or GPIO50; GPIO33 is not allowed
    assert 'Error: Pin 33 does not support function EMAC_RMII_CLK.' in out


def test_targets() -> None:
    """Test the targets command"""
    runner = CliRunner()
    result = runner.invoke(cast(Command, espins_cli), ['targets'])
    assert result.exit_code == 0
    for chip in SUPPORTED_CHIPS:
        assert chip in result.output
