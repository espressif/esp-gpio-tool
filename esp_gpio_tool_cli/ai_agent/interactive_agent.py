#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""
Interactive ESP32 GPIO Assignment Agent — CLI front-end.

This module provides the command-line interface (prompts, Rich output, questionary)
for the GPIO agent. The core logic lives in agent_backend.InteractiveGPIOAgent.

Usage:
- CLI: run this module or use the main() entry point.
- GUI/Web: use agent_backend.InteractiveGPIOAgent directly (same API, no CLI deps).
"""

import asyncio
import json
import logging
import sys
import typing as t
from pathlib import Path

import questionary
import rich_click as click
from questionary import Choice
from rich.console import Console
from rich.panel import Panel

# Support running as script: python path/to/interactive_agent.py (no parent package)
try:
    from .agent_backend import InteractiveGPIOAgent
    from .agent_backend import create_mermaid_html
    from .constants import DEFAULT_CONFIDENCE_THRESHOLD
    from .constants import DEFAULT_MODEL
except ImportError:
    _cli_root = Path(__file__).resolve().parent.parent
    if str(_cli_root) not in sys.path:
        sys.path.insert(0, str(_cli_root))
    from ai_agent.agent_backend import InteractiveGPIOAgent  # type: ignore[no-redef]
    from ai_agent.agent_backend import create_mermaid_html  # type: ignore[no-redef]
    from ai_agent.constants import DEFAULT_CONFIDENCE_THRESHOLD  # type: ignore[no-redef]
    from ai_agent.constants import DEFAULT_MODEL  # type: ignore[no-redef]

logger = logging.getLogger('esp_gpio_agent')

console = Console()

# Sentinel values for clarification prompt choices
_CLARIFY_SKIP = '__skip__'
_CLARIFY_QUIT = '__quit__'
_CLARIFY_CUSTOM = '__custom__'


async def _prompt_clarification_response(question: str, suggestions: list[str]) -> str | None:
    """
    Prompt user to pick a suggestion with arrow keys, or choose custom answer / skip / quit.
    Returns the selected or entered text, or None for skip, or raises SystemExit for quit.
    """
    choices: list[Choice] = []
    for s in suggestions:
        choices.append(Choice(s, value=s))
    choices.append(Choice('✏️  Custom answer (type your own)', value=_CLARIFY_CUSTOM))
    choices.append(Choice('⏭️  Skip / use defaults', value=_CLARIFY_SKIP))
    choices.append(Choice('👋 Quit', value=_CLARIFY_QUIT))

    answer = await questionary.select(question, choices=choices, use_arrow_keys=True).ask_async()
    answer = t.cast(str, answer)
    if answer is None:
        return _CLARIFY_QUIT
    if answer == _CLARIFY_QUIT:
        raise SystemExit(0)
    if answer == _CLARIFY_SKIP:
        return None
    if answer == _CLARIFY_CUSTOM:
        custom = await questionary.text('Your answer:').ask_async()
        custom = (custom or '').strip()
        return None if not custom else custom
    return answer


def _save_diagram_to_html(diagram: str) -> None:
    """Save diagram to HTML file for web viewing."""
    filename = 'esp32_diagram.html'
    with open(filename, 'w') as f:
        f.write(create_mermaid_html(diagram))
    console.print(f'[green]🌐 Diagram saved to {filename}[/] - open in browser to view!')


async def _display_design_summary(agent: InteractiveGPIOAgent) -> None:
    """Display the design summary and optionally save to file."""
    save = await questionary.confirm('Save design to file?', default=True, qmark='💾').ask_async()
    if save:
        filename = await questionary.path('📄 Filename', default='design.json').ask_async()
        if not filename:
            filename = 'design.json'
        with open(filename, 'w') as f:
            json.dump(agent.design_state, f, indent=2)
        console.print(f'[green]✓ Design saved to {filename}[/]')


async def run_interactive_design_session(
    agent: InteractiveGPIOAgent,
    initial_requirements: str | None = None,
) -> None:
    """
    Run an interactive design session (CLI only).
    Uses the backend agent for all logic; this function handles prompts and output.
    """
    console.print(
        Panel(
            '[bold]Interactive ESP32 GPIO Assignment Agent[/]\n\n'
            "I'll help you design an ESP32 project by asking clarifying questions.\n"
            '🔧 All MCP and diagram tools are used by the agent when it decides.\n'
            'Use arrow keys to select options; choose [bold]Quit[/] to end the session.',
            title='🤖 Agent',
            border_style='cyan',
        )
    )
    console.print()

    console.print('🔌 Configuring MCP...')
    await agent.start_mcp_servers()
    console.print('[green]✅ MCP configured[/]')

    if initial_requirements:
        requirements = initial_requirements
        console.print(f'[bold cyan]📋 Initial Requirements:[/] {requirements}\n')
    else:
        requirements = await questionary.text('📝 What would you like to build with ESP32?').ask_async()
        if requirements and requirements.lower() in ['quit', 'exit']:
            console.print('👋 Goodbye!')
            raise SystemExit(0)

    agent.add_to_conversation('user_requirements', requirements)

    # Clarification loop
    while True:
        with console.status('Analysing requirements...', spinner='dots'):
            clarification = await agent.ask_clarifying_questions(requirements)

        if clarification.get('out_of_scope', False):
            message = clarification.get(
                'out_of_scope_message',
                'I can only help with ESP32 GPIO pin assignment and hardware peripheral design.',
            )
            console.print(f'[red]⛔ {message}[/]')
            return

        if not clarification.get('needs_clarification', False):
            console.print('[green]✅ Requirements are clear enough to proceed![/]')
            break

        confidence = clarification.get('confidence', 0.0)
        if confidence >= agent.confidence_threshold:
            console.print('[green]✅ Making reasonable assumptions and proceeding...[/]')
            break

        questions_to_ask: list[tuple[str, list[str]]] = []
        if clarification.get('questions'):
            for item in clarification['questions']:
                if isinstance(item, dict) and item.get('question'):
                    q = item.get('question', '').strip()
                    opts = item.get('suggestions') or []
                    suggestions_list = [str(s) for s in opts] if isinstance(opts, list) else []
                    questions_to_ask.append((q, suggestions_list))

        if not questions_to_ask:
            console.print('[yellow]No valid questions returned; proceeding with assumptions.[/]\n')
            break

        console.print(f'[dim]🎯 Confidence: {confidence:.1%} (asking because < {agent.confidence_threshold:.0%})[/]\n')

        collected: list[str] = []
        try:
            for i, (question_text, suggestions) in enumerate(questions_to_ask):
                if suggestions:
                    user_response = await _prompt_clarification_response(question_text, suggestions)
                else:
                    raw = await questionary.text(question_text).ask_async()
                    if raw and raw.lower() in ['quit', 'exit']:
                        console.print('👋 Goodbye!')
                        return
                    if not raw or raw.lower() in ['skip', 'next', '']:
                        user_response = None
                    else:
                        user_response = raw

                if user_response is None:
                    console.print('[yellow]⏭️  Using default for this question.[/]\n')
                else:
                    collected.append(user_response)
                    agent.add_to_conversation('clarification_response', user_response)
                if i < len(questions_to_ask) - 1:
                    console.print('[green]✅ Next question...[/]\n')
        except SystemExit:
            console.print('👋 Goodbye!')
            return

        if not collected:
            console.print('[yellow]⏭️  Using default assumptions for all.[/]\n')
            break

        requirements += ' | Additional info: ' + '; '.join(collected)
        console.print('[green]✅ Got it! Processing...[/]\n')

    console.print('[bold green]🚀 Starting design process with clarified requirements...[/]\n')
    # Design loop
    while True:
        design_prompt = agent.create_design_prompt(requirements=requirements)

        console.print('[bold]🤖 Agent is using MCP and diagram tools as needed...[/]\n')
        try:
            with console.status('Agent working...', spinner='dots'):
                final_answer, diagram = await agent.run_agent_design_with_mcp_tools(design_prompt)
            agent.design_state = {'summary': final_answer, 'diagram': diagram or ''}
            console.print()
            console.print(Panel(final_answer, title='🎉 DESIGN RESULT', border_style='green'))
            if diagram:
                console.print('\n[bold]📊 Architecture Diagram (Mermaid):[/]')
                console.print(diagram)
                _save_diagram_to_html(diagram)

            satisfied = await questionary.confirm(
                'Does this design satisfy your requirements?',
                default=True,
                qmark='✅',
            ).ask_async()
            if satisfied:
                await _display_design_summary(agent)
                break

            feedback = await questionary.text(
                'What would you like to change? (describe changes; or type "quit" to save current design and exit)',
                qmark='🔄',
            ).ask_async()
            if not feedback or feedback.strip().lower() in ('quit', 'exit', 'q'):
                console.print('[dim]Saving current design and exiting.[/]')
                await _display_design_summary(agent)
                break
            requirements += ' | Requested changes: ' + feedback.strip()
            console.print('[cyan]🔄 Reiterating design with your feedback...[/]\n')
        except Exception as e:
            console.print(f'[red]❌ Agent design error:[/] {e}')

            import traceback

            logger.debug('Traceback:\n%s', traceback.format_exc())
            break


async def _async_main(
    requirements: tuple[str, ...],
    verbose: bool,
    model: str,
    confidence_threshold: float,
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(levelname)s [%(name)s] %(message)s',
    )
    initial_requirements = ' '.join(requirements).strip() or None
    agent = InteractiveGPIOAgent(model=model, confidence_threshold=confidence_threshold)
    await run_interactive_design_session(agent, initial_requirements=initial_requirements)


@click.command()
@click.argument('requirements', nargs=-1)
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging.')
@click.option(
    '--model',
    '-m',
    default=DEFAULT_MODEL,
    envvar='AI_MODEL',
    help='Model to use for agent. For best results, use gpt-5-nano or better. '
    'Note that the prompts have been tweaked for the default model.',
)
@click.option(
    '--confidence-threshold',
    '-c',
    default=DEFAULT_CONFIDENCE_THRESHOLD,
    envvar='CONFIDENCE_THRESHOLD',
    help='Ask when confidence is below this (default 0.6). Higher = ask more often, fewer wrong assumptions.',
)
def main(
    requirements: tuple[str, ...],
    verbose: bool,
    model: str,
    confidence_threshold: float,
) -> None:
    """Interactive ESP32 GPIO Assignment Agent.

    Start an interactive session to design GPIO pin assignments with clarifying
    questions. Use arrow keys to select suggested answers or choose a custom reply.

    REQUIREMENTS: Optional initial requirements (e.g. "Temperature monitor with WiFi").
    If omitted, you will be prompted at startup.
    """
    # On Windows, use ProactorEventLoop so MCP stdio client subprocess works.
    # Event-loop policies are deprecated in 3.14 and removed in 3.16; loop_factory is 3.12+.
    run_kwargs: dict[str, t.Any] = {}
    if sys.platform == 'win32':
        if sys.version_info >= (3, 12):
            run_kwargs['loop_factory'] = asyncio.ProactorEventLoop
        else:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        asyncio.run(_async_main(requirements, verbose, model, confidence_threshold), **run_kwargs)
    except KeyboardInterrupt:
        console.print('\n[yellow]👋 Session interrupted. Goodbye![/]')
    except SystemExit:
        raise
    except Exception as e:
        console.print(f'[red]❌ Unexpected error:[/] {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
