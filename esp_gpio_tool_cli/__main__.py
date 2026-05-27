# SPDX-FileCopyrightText: 2024-2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
import rich_click as click
from rich import box
from rich.console import Console
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from esp_gpio_tool_cli import __version__
from esp_gpio_tool_cli.checker import run_check
from esp_gpio_tool_cli.chip import ESP
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS
from esp_gpio_tool_cli.logger import Logger


@click.group(no_args_is_help=True)
@click.version_option(__version__)
@click.option('--no-unicode', is_flag=True, help='Disable Unicode characters in the output.')
def main(no_unicode: bool = False) -> None:
    """ESP GPIO Tool CLI"""
    Logger().use_unicode(not no_unicode)


@main.command()
@click.argument('filename', type=click.Path(exists=True), required=True)
def check(filename: str) -> None:
    """Check the pin configuration from the given yaml file"""
    with open(filename, encoding='UTF-8') as file:
        user_input = file.read()
    output = run_check(user_input)
    for line in output:
        print(line)
    if 'All checks passed.' not in output:
        raise SystemExit(1)


@main.command()
def targets() -> None:
    """Print supported chip target names and SoC variants"""
    console = Console()
    table = Table(show_header=True, header_style='bold', box=box.ROUNDED)
    table.add_column('Chip', style='cyan')
    table.add_column('SoC variants', style='white')
    for chip in SUPPORTED_CHIPS:
        esp = ESP(chip)
        socs = ', '.join(str(soc) for soc in esp.soc_list) or '—'
        table.add_row(chip, socs)
    console.print(table)


@main.command(name='list-pins')
@click.argument('chip', type=click.Choice(SUPPORTED_CHIPS), required=True)
def list_pins(chip: str) -> None:
    """Print the available pins for the given chip"""
    console = Console()
    esp = ESP(chip)

    # Chip overview panel
    socs_str = ', '.join(str(soc) for soc in esp.soc_list)
    console.print(
        Panel(
            socs_str,
            title=f'[bold cyan]Chip: {esp.name}[/]',
            subtitle='SoCs',
            border_style='cyan',
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )

    # IO peripheral panel
    content = ['[bold]Functions:[/] [green]INPUT[/], [green]OUTPUT[/]']
    gpio_str = ', '.join(f'[cyan]{num}[/]' if gpio.lp or gpio.rtc else str(num) for num, gpio in esp.gpios.items())
    content.append(f'[bold]GPIOs:[/] {gpio_str}')
    content.append('[cyan dim]* Low power capable GPIOs.[/]')
    console.print(
        Panel(
            '\n'.join(content),
            title='[bold green]IO[/]',
            border_style='green',
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )

    # One panel per peripheral
    for peripheral in esp.peripherals:
        parts: list[object] = []
        if peripheral.supported_modes:
            modes_table = Table(show_header=True, header_style='bold', box=box.SIMPLE, border_style='dim')
            modes_table.add_column('Instance', style='dim')
            modes_table.add_column('Modes', style='white')
            for instance_key, modes_list in peripheral.supported_modes.items():
                default_mode = peripheral.mode.get(instance_key)
                cell = Text()
                for i, m in enumerate(modes_list):
                    m_str = str(m)
                    cell.append(m_str, style='green' if m_str == str(default_mode) else None)
                    if i < len(modes_list) - 1:
                        cell.append(', ')
                modes_table.add_row(instance_key, cell)
            parts.append(modes_table)
        pins_table = Table(show_header=True, header_style='bold', box=box.SIMPLE, border_style='dim')
        pins_table.add_column('Instance', style='dim')
        pins_table.add_column('Pins/Functions', style='white')
        for instance in peripheral.instances:
            pins = peripheral.all_pins[instance]
            required_set = set(peripheral.required_pins(instance))
            cell = Text('')
            for i, pin in enumerate(pins):
                style = None
                if pin in peripheral.assigned_pins.get(instance, []):
                    style = 'underline'
                if pin in required_set:
                    style = 'underline red' if style else 'red'
                cell.append(pin, style=style)
                if i < len(pins) - 1:
                    cell.append(', ')
            pins_table.add_row(instance, cell)
        parts.append(pins_table)
        content = Group(*parts)
        console.print(
            Panel(
                content,
                title=f'[not dim bold]{peripheral.name}[/]',
                title_align='left',
                box=box.ROUNDED,
                padding=(0, 1),
                border_style='dim yellow',
            )
        )
    console.print('[red dim]* Required pins. Note that this might depend on the default selected mode.[/]')
    console.print('[green dim]* Default selected mode.[/]')
    console.print('[underline dim]* Pins that are routed using IO MUX.[/]')


if __name__ == '__main__':
    main()
