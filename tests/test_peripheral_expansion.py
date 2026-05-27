# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Peripheral placeholder expansion behavior."""

from esp_gpio_tool_cli.peripheral import ADC
from esp_gpio_tool_cli.peripheral import LCDCAM
from esp_gpio_tool_cli.peripheral import LEDC
from esp_gpio_tool_cli.peripheral import PARLIO
from esp_gpio_tool_cli.peripheral import SDIO
from esp_gpio_tool_cli.peripheral import SPI
from esp_gpio_tool_cli.peripheral import UART


def test_adc_expands_instance_then_channel_placeholders() -> None:
    adc = ADC(count=2, assigned_pins=['ADC{count}_CH{{channel}}'], channels={'1': 2, '2': 3})

    assert adc.assigned_pins == {
        '1': ['ADC1_CH0', 'ADC1_CH1'],
        '2': ['ADC2_CH0', 'ADC2_CH1', 'ADC2_CH2'],
    }


def test_uart_routes_digit_literals_and_expands_instance_placeholders() -> None:
    uart = UART(
        count=3,
        assigned_pins=['U{count}TXD'],
        universal_pins=['U0DTR', 'U2DSR'],
    )

    assert uart.assigned_pins == {
        '0': ['U0TXD'],
        '1': ['U1TXD'],
        '2': ['U2TXD'],
    }
    assert uart.universal_pins == {
        '0': ['U0DTR'],
        '1': [],
        '2': ['U2DSR'],
    }


def test_spi_routes_subname_literals_without_digit_prefix_leakage() -> None:
    spi = SPI(
        count=3,
        assigned_pins=['SPID', 'FSPID', 'SPI3D'],
        subname=['SPI', 'FSPI', 'SPI3'],
    )

    assert spi.assigned_pins == {
        'SPI': ['SPID'],
        'FSPI': ['FSPID'],
        'SPI3': ['SPI3D'],
    }


def test_ledc_expands_named_instances_and_broadcasts_literals() -> None:
    ledc = LEDC(
        count=2,
        universal_pins=['LEDC_{subname}_SIG_OUT{{channel}}', 'LEDC_CLK'],
        subname=['HS', 'LS'],
        channels=2,
    )

    assert ledc.universal_pins == {
        'HS': ['LEDC_HS_SIG_OUT0', 'LEDC_HS_SIG_OUT1', 'LEDC_CLK'],
        'LS': ['LEDC_LS_SIG_OUT0', 'LEDC_LS_SIG_OUT1', 'LEDC_CLK'],
    }


def test_lcdcam_expands_subname_literals_and_channels() -> None:
    lcdcam = LCDCAM(
        count=1,
        universal_pins=['{subname}_PCLK', 'LCD_CD', 'CAM_CLK', '{subname}_DATA{{channel}}'],
        subname=['LCD', 'CAM'],
        channels={'LCD': 3, 'CAM': 2},
        modes={
            'LCD': ['24 bit - Master TX Mode'],
            'CAM': ['16 bit - Slave RX Mode'],
        },
    )

    assert lcdcam.universal_pins == {
        'LCD': ['LCD_PCLK', 'LCD_CD', 'LCD_DATA0', 'LCD_DATA1', 'LCD_DATA2'],
        'CAM': ['CAM_PCLK', 'CAM_CLK', 'CAM_DATA0', 'CAM_DATA1'],
    }


def test_parlio_expands_all_data_width_pins_and_filters_by_mode() -> None:
    parlio = PARLIO(
        count=1,
        universal_pins=['PARL_TX_CLK_IN', 'PARL_TX_DATA{data_width}'],
        data_width=[1, 2, 4],
    )

    assert parlio.all_pins['0'] == [
        'PARL_TX_CLK_IN',
        'PARL_TX_DATA0',
        'PARL_TX_DATA1',
        'PARL_TX_DATA2',
        'PARL_TX_DATA3',
    ]
    assert parlio.universal_pins['0'] == ['PARL_TX_CLK_IN', 'PARL_TX_DATA0']

    parlio.set_mode('0', '4')
    assert parlio.universal_pins['0'] == [
        'PARL_TX_CLK_IN',
        'PARL_TX_DATA0',
        'PARL_TX_DATA1',
        'PARL_TX_DATA2',
        'PARL_TX_DATA3',
    ]


def test_sdio_expands_all_data_width_pins_and_filters_by_mode() -> None:
    sdio = SDIO(
        count=1,
        assigned_pins=['SDIO{count}_CLK', 'SDIO{count}_DATA{{data_width}}'],
        data_width={'0': [1, 4]},
    )

    assert sdio.all_pins['0'] == ['SDIO0_CLK', 'SDIO0_DATA0', 'SDIO0_DATA1', 'SDIO0_DATA2', 'SDIO0_DATA3']
    assert sdio.assigned_pins['0'] == ['SDIO0_CLK', 'SDIO0_DATA0']

    sdio.set_mode('0', '4')
    assert sdio.assigned_pins['0'] == ['SDIO0_CLK', 'SDIO0_DATA0', 'SDIO0_DATA1', 'SDIO0_DATA2', 'SDIO0_DATA3']
