# typer cmd : hv slack msg, hv slack go
import subprocess

import typer
from rich import print

from hv.utils import load_config

app = typer.Typer(name="slack", help="Slack operations")


def run_script(script: str):
    """Run AppleScript and handle errors."""
    try:
        subprocess.run(["osascript", "-e", script])
        return True
    except subprocess.SubprocessError as e:
        print(f"[red]Error: {e}[/red]")
        return False


def get_config():
    """Get Slack configuration from variables.yaml."""
    return load_config("variables").get("slack", {})


@app.command(name="msg", help="Send message to user")
@app.command(name="m")
def message(
    text: str = typer.Argument(...),
    user: str = typer.Option(
        None, "--user", "-u", help="User to message"
    ),
):
    config = get_config()
    user = user or config.get("default_user")
    script = f"""
    tell application "Slack"
        activate
        tell application "System Events"
            keystroke "k" using command down
            delay 0.5
            keystroke "@{user}"
            delay 0.5
            key code 36
            delay 0.5
            keystroke "{text}"
            delay 0.2
            keystroke return
        end tell
    end tell"""
    if run_script(script):
        print("[green]Message sent[/green]")


@app.command(name="go", help="Go to channel")
@app.command(name="g")
def goto_channel(channel: str = typer.Argument(...)):
    config = load_config("variables").get("slack", {})
    channel_name = config.get("channels", {}).get(channel, channel)
    script = f"""
    tell application "Slack"
        activate
        tell application "System Events"
            keystroke "k" using command down
            delay 0.1
            keystroke "#{channel_name}"
            delay 0.1
            key code 36
        end tell
    end tell"""
    if run_script(script):
        print(f"[green]Navigated to #{channel_name}[/green]")
