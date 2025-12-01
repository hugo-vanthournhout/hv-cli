# typer cmd : hv ai process_and_claude, hv ai print_project, hv ai claude, hv ai dbt
import fnmatch
import os
import platform
import subprocess
import webbrowser
from pathlib import Path
from typing import List, Optional

import typer
from rich import print

from hv.utils import load_config

app = typer.Typer(
    name="ai",
    help="AI-related tools and utilities",
)


def expand_home_path(path: str) -> str:
    """Expand ~ to home directory in path."""
    return os.path.expanduser(path)


def should_ignore_file(file_path: str, ignore_patterns: List[str]) -> bool:
    """Check if file should be ignored based on patterns."""
    for pattern in ignore_patterns:
        pattern = expand_home_path(pattern)
        if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(
            os.path.basename(file_path), pattern
        ):
            return True
        parts = Path(file_path).parts
        for i in range(len(parts)):
            subpath = str(Path(*parts[0 : i + 1]))
            if fnmatch.fnmatch(subpath, pattern):
                return True
    return False


def is_text_file(file_path: str, text_extensions: List[str]) -> bool:
    """Check if file is likely a text file based on extension."""
    return Path(file_path).suffix.lower() in text_extensions


def get_priority_files(folder: Path) -> List[Path]:
    """Get README.md and pyproject.toml if they exist."""
    priority_files = []
    readme = folder / "README.md"
    pyproject = folder / "pyproject.toml"

    if readme.exists():
        priority_files.append(readme)
    if pyproject.exists():
        priority_files.append(pyproject)

    return priority_files


def process_project(
    folders: List[Path],
    output_file: Path,
    output_to_cli: bool,
    ignore_patterns: List[str],
) -> None:
    """Process project files and output content."""
    config = load_config("variables")
    ai_config = config.get("ai", {})

    warning_paths = [expand_home_path(p) for p in ai_config.get("warning_paths", [])]
    default_ignore_patterns = ai_config.get("ignore_patterns", [])
    text_extensions = ai_config.get("text_extensions", [])

    all_ignore_patterns = default_ignore_patterns.copy()
    if ignore_patterns:
        all_ignore_patterns.extend(ignore_patterns)

    for folder in folders:
        abs_path = str(folder.resolve())
        for warning_path in warning_paths:
            warning_path = expand_home_path(warning_path)
            if abs_path.startswith(warning_path):
                print(
                    f"[yellow]Warning: Processing sensitive path: {abs_path}[/yellow]"
                )
                if not typer.confirm("Do you want to continue?"):
                    raise typer.Abort() from None

    output_content = []

    for folder in folders:
        folder_path = folder.resolve()
        if not folder_path.exists():
            print(f"[red]Error: Folder not found: {folder}[/red]")
            continue

        priority_files = get_priority_files(folder_path)
        for file_path in priority_files:
            try:
                rel_path = file_path.relative_to(folder_path)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                file_header = f"*# {rel_path}*"
                output_content.extend([file_header, content, ""])
            except Exception as e:
                print(f"[red]Error reading {rel_path}: {e}[/red]")

        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = Path(root) / file

                if file_path in priority_files:
                    continue

                try:
                    rel_path = file_path.relative_to(folder_path)
                except ValueError:
                    continue

                if should_ignore_file(str(rel_path), all_ignore_patterns):
                    continue

                if not is_text_file(file_path.name, text_extensions):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    file_header = f"*# {rel_path}*"
                    output_content.extend([file_header, content, ""])
                except Exception as e:
                    print(f"[red]Error reading {rel_path}: {e}[/red]")

    final_output = "\n".join(output_content)

    if output_to_cli:
        print(final_output)
    else:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(final_output)
            print(f"[green]Project content written to: {output_file}[/green]")
        except Exception as e:
            print(f"[red]Error writing to output file: {e}[/red]")


@app.command(name="process_and_claude", help="Process project and open Claude chat")
@app.command(name="pc")
def process_and_claude(
    folders: List[str] = typer.Option(
        ["."],  # Accept strings instead of Path objects
        help="Folders to process",
        exists=True,
        dir_okay=True,
        file_okay=False,
    ),
    override_prompt: Optional[str] = typer.Option(
        None, help="Override default prompt from config"
    ),
):
    """Process project and open Claude chat."""
    config = load_config("variables")
    ai_config = config.get("ai", {})

    # Convert string paths to Path objects
    folder_paths = [Path(f) for f in folders]
    output_file = Path(ai_config.get("output_file", "ai_full_project.txt"))
    default_prompt = override_prompt or ai_config.get("default_prompt", "")

    try:
        print_project(
            folders=folder_paths,
            output_file=output_file,
            output_to_cli=False,
            ignore_patterns=None,
        )

        if output_file.exists():
            claude_chat(input_file=output_file, prompt=default_prompt, copy_mode="both")
        else:
            print("[red]Error: Failed to generate project file[/red]")
            raise typer.Exit(1) from None

    except Exception as e:
        print(f"[red]Error in default workflow: {e}[/red]")
        raise typer.Exit(1) from e


@app.command(name="print_project", help="Print project files for AI analysis")
@app.command(name="pp")
def print_project(
    folders: List[Path] = typer.Argument(
        None,
        help="Folders to process (default: current directory)",
        exists=True,
        dir_okay=True,
        file_okay=False,
    ),
    output_file: Path = typer.Option(None, help="Output file path"),
    output_to_cli: bool = typer.Option(
        False, help="Print output to CLI instead of file"
    ),
    ignore_patterns: Optional[List[str]] = typer.Option(
        None, help="Additional patterns to ignore"
    ),
):
    """Print project files in a format suitable for AI analysis."""
    config = load_config("variables")
    ai_config = config.get("ai", {})

    output_file = output_file or Path(
        ai_config.get("output_file", "ai_full_project.txt")
    )
    folders = folders or [Path(".")]

    process_project(folders, output_file, output_to_cli, ignore_patterns or [])


@app.command(name="claude", help="Open Claude chat with project context")
@app.command(name="c")
def claude_chat(
    input_file: Path = typer.Option(
        None, help="Input file to send to Claude", exists=True
    ),
    prompt: str = typer.Option(None, help="Custom prompt for Claude"),
    copy_mode: str = typer.Option(
        "both", help="What to copy to clipboard: 'prompt', 'file', or 'both'"
    ),
):
    """Open a new Claude chat."""
    config = load_config("variables")
    ai_config = config.get("ai", {})

    input_file = input_file or Path(ai_config.get("output_file", "ai_full_project.txt"))
    prompt = prompt or ai_config.get("default_prompt", "")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            file_content = f.read()

        if copy_mode == "prompt":
            clipboard_content = f"{prompt}\n\n<userStyle>Normal</userStyle>"
        elif copy_mode == "file":
            clipboard_content = f"<document>\n<source>{input_file}</source>\n<document_content>\n{file_content}\n</document_content>\n</document>\n\n<userStyle>Normal</userStyle>"
        elif copy_mode == "both":
            clipboard_content = f"<document>\n<source>{input_file}</source>\n<document_content>\n{file_content}\n</document_content>\n</document>\n\n{prompt}\n\n<userStyle>Normal</userStyle>"
        else:
            clipboard_content = f"{prompt}\n\n<userStyle>Normal</userStyle>"

        if platform.system() == "Darwin":
            try:
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                process.communicate(clipboard_content.encode("utf-8"))
                print("[green]Content copied to clipboard[/green]")
            except subprocess.SubprocessError as e:
                print(f"[red]Error copying to clipboard: {e}[/red]")
                raise typer.Exit(1) from e
        else:
            print("[yellow]Clipboard functionality only supported on macOS[/yellow]")
            print(
                f"[blue]Here's your content to copy manually:[/blue]\n{clipboard_content}"
            )

        if platform.system() == "Darwin":
            try:
                subprocess.run(
                    ["open", "-a", "Brave Browser", "https://claude.ai/chats"]
                )
            except subprocess.SubprocessError:
                print(
                    "[yellow]Could not open Brave Browser, falling back to default browser[/yellow]"
                )
                webbrowser.open("https://claude.ai/chats")
        else:
            webbrowser.open("https://claude.ai/chats")

        print("[green]Opening Claude chat...[/green]")
        print("[yellow]Instructions:[/yellow]")
        print(f"1. Content copied to clipboard ({copy_mode})")
        print("2. Wait for Claude.ai to load")
        print("3. Create a new chat")
        print("4. Paste (Cmd+V) the copied content")

    except Exception as e:
        print(f"[red]Error opening Claude chat: {e}[/red]")
        raise typer.Exit(1) from e


def get_dbt_files(folder: Path) -> List[Path]:
    """Get essential DBT files, focusing on models, macros, and analyses."""
    dbt_paths = []
    essential_dirs = ["models", "macros", "analyses"]
    essential_extensions = [".sql", ".yml", ".yaml"]

    for root, _, files in os.walk(folder):
        root_path = Path(root)
        skip = False
        # Skip dbt_packages directory
        for exclude_dir in [".venv", "target", "dbt_packages"]:
            if exclude_dir in str(root_path):
                # print(f"[yellow]Skipping {exclude_dir}[/yellow]")
                skip = True
                break
        if skip:
            continue
        # Only process if we're in a relevant DBT directory
        if any(d in str(root_path) for d in essential_dirs):
            for file in files:
                file_path = root_path / file
                if file_path.suffix in essential_extensions:
                    dbt_paths.append(file_path)

    return dbt_paths


@app.command(name="dbt", help="Process DBT project files for AI analysis")
def process_dbt(
    folders: List[str] = typer.Option(
        ["."],
        help="DBT project folders to process",
        exists=True,
        dir_okay=True,
        file_okay=False,
    ),
    output_file: Path = typer.Option(None, help="Output file path"),
    output_to_cli: bool = typer.Option(
        False, help="Print output to CLI instead of file"
    ),
    override_prompt: Optional[str] = typer.Option(
        None, help="Override default prompt from config"
    ),
):
    """Process DBT project files and prepare them for AI analysis."""
    config = load_config("variables")
    ai_config = config.get("ai", {})

    folder_paths = [Path(f) for f in folders]
    output_file = output_file or Path(
        ai_config.get("output_file", "ai_full_project.txt")
    )
    default_prompt = override_prompt or ai_config.get("default_prompt", "")

    output_content = []

    for folder in folder_paths:
        if not folder.exists():
            print(f"[red]Error: Folder not found: {folder}[/red]")
            continue

        dbt_files = get_dbt_files(folder)

        for file_path in sorted(dbt_files):
            try:
                rel_path = file_path.relative_to(folder)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                file_header = f"*# {rel_path}*"
                output_content.extend([file_header, content, ""])
            except Exception as e:
                print(f"[red]Error reading {rel_path}: {e}[/red]")

    final_output = "\n".join(output_content)

    if output_to_cli:
        print(final_output)
    else:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(final_output)
            print(f"[green]DBT content written to: {output_file}[/green]")

            # Open Claude if files were processed successfully
            claude_chat(input_file=output_file, prompt=default_prompt, copy_mode="both")
        except Exception as e:
            print(f"[red]Error writing to output file: {e}[/red]")
            raise typer.Exit(1) from e
