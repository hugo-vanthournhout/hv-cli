# src/hv/cli.py
import inspect
from importlib import import_module

import typer

from .utils import load_config

app = typer.Typer(
    name="hv",
    help="Personal automation toolbox",
    no_args_is_help=True,
)


def execute_default_command(command_name: str):
    """Execute the default command for a module with parameters from config."""
    commands_config = load_config(config_type="command")
    cmd_config = commands_config.get(command_name, {})

    if "default_command" in cmd_config:
        module_path = f"hv.commands.{cmd_config['file'].replace('.py', '')}"
        try:
            cmd_module = import_module(module_path)
            default_func = getattr(cmd_module, cmd_config["default_command"])

            # Get default parameters from config
            default_params = cmd_config.get("default_params", {})

            # Inspect function signature to get required parameters
            sig = inspect.signature(default_func)

            # Filter out context parameter if it exists
            params = {
                name: param for name, param in sig.parameters.items() if name != "ctx"
            }

            # Build kwargs dict with defaults from config
            kwargs = {}
            for name, param in params.items():
                if name in default_params:
                    kwargs[name] = default_params[name]
                elif param.default == inspect.Parameter.empty and param.kind not in [
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ]:
                    # Required parameter with no default in config
                    typer.echo(
                        f"Warning: Required parameter '{name}' for {command_name}.{cmd_config['default_command']} has no default value"
                    )
                    return

            # Execute function with parameters
            default_func(**kwargs)

        except (ImportError, AttributeError) as e:
            typer.echo(
                f"Warning: Could not execute default command for {command_name}: {e}"
            )


def register_commands():
    """Dynamically register commands from configuration."""
    commands_config = load_config(config_type="command")

    for cmd_name, cmd_config in commands_config.items():
        module_path = f"hv.commands.{cmd_config['file'].replace('.py', '')}"
        try:
            cmd_module = import_module(module_path)
            main_app = cmd_module.app

            # Register the main command
            app.add_typer(main_app, name=cmd_name)

            # Register aliases
            if "alias" in cmd_config:
                for alias in cmd_config["alias"]:
                    app.add_typer(main_app, name=alias)

            # Set up callback if default_command is specified
            if "default_command" in cmd_config:

                @main_app.callback(invoke_without_command=True)
                def callback(ctx: typer.Context, cmd_name=cmd_name):
                    if ctx.invoked_subcommand is None:
                        execute_default_command(cmd_name)

        except ImportError as e:
            typer.echo(f"Warning: Could not load command {cmd_name}: {e}")
            continue


# Register commands from configuration
register_commands()

if __name__ == "__main__":
    app()
