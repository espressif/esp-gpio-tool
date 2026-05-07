<a href="https://www.espressif.com">
    <img src="https://www.espressif.com/sites/all/themes/espressif/logo-black.svg" alt="Espressif logo" title="Espressif" align="right" height="20" />
</a>

<div align="center">
    <h1>ESP GPIO Tool</h1>
    <hr>
    <a href="https://pypi.org/project/esp-gpio-tool/">
        <img src="https://img.shields.io/pypi/v/esp-gpio-tool" alt="PyPI">
    </a>
    <a href="LICENSE">
        <img src="https://img.shields.io/pypi/l/esp-gpio-tool" alt="License">
    </a>
    <a href="https://pypi.org/project/esp-gpio-tool/">
        <img src="https://img.shields.io/pypi/pyversions/esp-gpio-tool" alt="Python Versions">
    </a>
    <hr>
</div>


**Welcome to the ESP GPIO Tool!**
This repository is a Python-based, open-source package that is used for developing applications with Espressif's SoCs.

It provides a few developer-facing tools around GPIO pin planning and validation:

- **CLI (`espins-cli`)**: validate a YAML pin assignment, and inspect chip GPIO/peripheral capabilities.
- **GUI (`espins`)**: a simple desktop UI for the checker.
- **GPIO MCP server**: a MCP server that can be used by models to access the core functions.

## Source of Truth (Datasheet/TRM)

ESP GPIO Tool is meant to **help you get started faster** and catch common configuration mistakes. It is **not** a replacement for the chip's **datasheet** and **TRM**.

- The **datasheet and TRM are authoritative**. Always verify pin capabilities, electrical characteristics, and peripheral signal routing against the official documentation.
- Do **not** build production hardware solely based on information from this tool.
- If you spot a mismatch vs datasheet/TRM, please **report it** so we can fix it.

When reporting a mismatch, include:

- Chip and tool version (`espins-cli --version` if applicable)
- What you expected vs what the tool reports (copy/paste output if possible)
- Datasheet/TRM reference (document name + section/page)
- A minimal config snippet (YAML) or CLI command that reproduces the issue

---

- [Getting Started](#getting-started)
  - [Usage](#usage)
- [Documentation](#documentation)
  - [Get List of Functions](#get-list-of-functions)
  - [GPIO Assignment Checker](#gpio-assignment-checker)
    - [AI Agent](#ai-agent)
    - [GUI](#gui)
    - [Input File](#input-file)
      - [Peripheral Mode Selection](#peripheral-mode-selection)
- [API Usage](#api-usage)
  - [Get List of GPIOs and Functions](#get-list-of-gpios-and-functions)
  - [Run Check](#run-check)
- [CHANGELOG](#changelog)
- [License](#license)
- [Contributing](#contributing)

---

## Getting Started

### Usage

Clone the repository and install the Python package

  ```sh
  pip install .
  ```

---

## Documentation

ESP GPIO tool supports checking of pin assignment using a CLI and a simple GUI.

Supported chips (targets currently shipped in `esp_gpio_tool_cli/targets/`):

- `esp32`
- `esp32c2`
- `esp32c3`
- `esp32c6`
- `esp32h2`
- `esp32p4`
- `esp32s2`
- `esp32s3`

### AI Agent

ESP GPIO tool has also experimental implementation of interactive AI Agent that should help better understand user requirements and suggest a pin assignment. We also support [MCP server](https://modelcontextprotocol.io/docs/getting-started/intro) for easier integration of tool into any agent. For more details see agent [README.md](esp_gpio_tool_cli/ai_agent/README.md)

### Get List of Functions

Getting a list of all possible functions might help with writing the function names correctly. Since there are some differences in names across the chips and also between datasheets and ESP-IDF. The following command will provide all functions available for the selected chip, split by peripherals.

```sh
espins-cli list-pins esp32
```

### GPIO Assignment Checker

The tool will check your pin assignment for completeness, correctness and potential collisions with pre-defined peripherals for debugging etc.

Example:

```sh
python -m esp_gpio_tool_cli check myconfig.yaml
```

or

```sh
espins-cli check myconfig.yaml
```

For details regarding the format of the input file please refer to the Input file section.

#### GUI

The GUI version of a user input for the `GPIO Assignment Checker` can be used.

> [!NOTE]
> If you want to use GUI for checker, install Python `Tkinter`.

Debian-based Linux (Ubuntu, Debian, etc.)

```sh
sudo apt-get install python3-tk
```

macOS

```sh
brew install python-tk
```

Windows - if not installed use the Python installer to modify the installation and check the `tcl/tk` and IDLE (or similar) option to be included in the installation.

To invoke the GUI following command can be used:

```sh
python -m esp_gpio_tool
```

or

```sh
espins
```

#### Input File

The input file is expected to be in the YAML format. The file is expected to have a `chip` keyword in the header of the file. Without this header, the tool will assume the configuration file is for ESP32.

The body of the file should contain your assignment of the GPIOs. A pin number is used as a key and a function as a value. Duplicated keys are not allowed by the YAML format but the value can be a single function or an array. However, it is not recommended to use the pin for multiple functions.

There is also an optional key `soc` to specify which SoC is going to be used. This parameter can help to better define limitations of selected SoC, like not connected pins, in-package Flash/PSRAM that occupies some pins etc. The value is MPN (Manufacturer Part Number) which can be found on the package itself or in the [Product Selector](https://products.espressif.com/#/product-selector).

Example:

```yaml
chip: esp32
soc: ESP32-PICO-V3

0: TOUCH0
3: [LEDC_HS_SIG_OUT0, LEDC_HS_SIG_OUT1, RMT_SIG_IN0]
```

##### Peripheral Mode Selection

Some peripherals support changing modes of operation. The mode you select may require a different subset of the peripheral's pins. This helps the tool understand your needs and adjust its checks accordingly.

To see a list of supported modes, check the datasheet of your selected chip. Alternatively, you can check the definition in the `esp_gpio_tool/targets/` folder. Here, you'll find your selected chip and can get a list of supported modes based on the peripheral.

If you select a mode that the peripheral does not support, the checker will not consider the mode change. Instead, it will continue in its default state and provide a list of supported modes.

Here's an example of a config file where the Quad mode of HSPI is selected:

```yaml
chip: esp32

peripheral:
  SPI:
    HSPI: Quad SPI

2:  HSPIWP
4:  HSPIHD
12: HSPIQ
13: HSPID
14: HSPICLK
15: HSPICS0
```

## API Usage

This is a high level look at the public API, meaning this section will focus more on providing examples for common functionality. For more details on all available methods and properties, please refer to docstrings in the code itself.

Please note that only functions listed below are part of the public API and all other functions are subject to change with any release.

### Get List of GPIOs and Functions

```py
# Get list of supported chips
from esp_gpio_tool_cli.chip import SUPPORTED_CHIPS
print(SUPPORTED_CHIPS) # This includes a list of names of chips without dash (e.g. esp32s3)

from esp_gpio_tool_cli.chip import ESP
# Create ESP class
esp = ESP("esp32")
# Optionally set MPN of chip - some have missing pins or even some extra were added between revisions
esp.set_soc("ESP32-PICO-D4")
# To get all possible MPN run
print(esp.soc_list)

# This will return dictionary of `Pin` classes with GPIO number as key.
print(esp.gpios)

# Get list of all GPIO pins
gpio_list = esp.get_gpio_list()
# To get list with power-domain, unwrap the dict of GPIO pins, e.g. "GPIO1 - VDD3P3_RTC"
gpio_list = [str(g) for g in esp.gpios.values()]

# Get list of peripherals
print(esp.peripherals)
# Get all pins for e.g. ADC (the key here is class name in peripheral.py)
print(esp.get_peripheral("ADC").all_pins)
```

### Run Check

You can either run checker on already existing YAML filename or pass config as dictionary. For more details how to create a config please refer to [Input File](#input-file) section.

```py
from esp_gpio_tool_cli.checker import run_check

config = {
  "chip": "esp32",
  0: "TOUCH1",
  3: ["LEDC_HS_SIG_OUT0", "LEDC_HS_SIG_OUT1", "RMT_SIG_IN0"],
}
out = run_check(config)
# Output is provided as a list of messages
print(out)
```

---

## CHANGELOG

- The [`CHANGELOG.md`](CHANGELOG.md) file.

## License

This document and the attached source code are released as Free Software under Apache License Version 2 or later. See the accompanying [LICENSE](LICENSE) file for a copy.

## Contributing

📘 If you are interested in contributing to this project, see the [Project Contributing Guide](CONTRIBUTING.md).
