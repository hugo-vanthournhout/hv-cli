# typer cmd : hv zoom meeting, hv zoom daily
import platform
import subprocess
import webbrowser

import typer

from hv.utils import get_credential, load_config

app = typer.Typer(name="zoom", help="Zoom meeting operations")


def get_config():
    """Get Zoom configuration from variables.yaml."""
    config = load_config("variables")
    return config.get("zoom", {})


def get_meeting_url(meeting_name: str = "daily") -> str:
    """Get Zoom meeting URL from credentials."""
    config = get_config()
    domain = config.get("domain", "zoom.us")
    meeting_data = get_credential("zoom", meeting_name)
    if not meeting_data:
        raise typer.Exit(f"Meeting '{meeting_name}' not found in credentials") from None
    return f"https://{domain}/j/{meeting_data['id']}?pwd={meeting_data['password']}"


def join_meeting(url: str):
    """Join a Zoom meeting using native app or browser."""
    if platform.system() == "Darwin":
        try:
            subprocess.run(["open", "-a", "zoom.us", url])
        except subprocess.SubprocessError:
            webbrowser.open(url)
    else:
        webbrowser.open(url)


@app.command(name="meeting")
@app.command(name="m")
def join_specific_meeting(
    meeting_name: str = typer.Option(
        "daily", "--meeting", "-m", help="Name of the meeting to join"
    ),
):
    """Join a specific Zoom meeting."""
    url = get_meeting_url(meeting_name)
    join_meeting(url)


@app.command(name="daily")
def join_daily():
    """Join the daily Zoom meeting."""
    url = get_meeting_url("daily")
    join_meeting(url)
