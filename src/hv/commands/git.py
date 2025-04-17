# typer cmd : hv git check-commits (correct wrong commit), hv git reset-history, hv git sync, hv git squash (squash all commits from branch into one)
import re
import subprocess
from functools import wraps
from typing import List, Tuple

import typer
from rich import print

app = typer.Typer(name="git", help="Git operations")


def git_command_handler(func):
    """Decorator to handle git command execution and errors."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except subprocess.CalledProcessError as e:
            print(f"[red]Git command failed: {e.stderr}[/red]")
            raise typer.Exit(1) from e
        except Exception as e:
            print(f"[red]Operation failed: {str(e)}[/red]")
            raise typer.Exit(1) from e

    return wrapper


def run_git(command: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and return the output."""
    return subprocess.run(
        ["git"] + command, check=check, capture_output=True, text=True
    )


def get_branch_commits(base_branch: str = "main") -> List[Tuple[str, str]]:
    """Get all commits on current branch compared to base branch."""
    result = run_git(["log", "--reverse", f"{base_branch}..HEAD", "--format=%H %s"])
    return [
        tuple(line.split(" ", 1)) for line in result.stdout.splitlines() if line.strip()
    ]


COMMIT_PATTERNS = [r"^(feat|fix|chore)(\(.*?\))?:\s"]


def is_conventional_commit(message: str) -> bool:
    """Check if commit message follows conventional commits format."""
    return any(re.match(pattern, message) for pattern in COMMIT_PATTERNS)


def confirm_action(prompt: str, default: bool = False) -> bool:
    """Utility function for user confirmation."""
    return typer.confirm(prompt, default=default)


@app.command(name="check-commits")
@git_command_handler
def check_conventional_commits(
    base_branch: str = typer.Option("main", help="Base branch to compare against"),
):
    """Check and fix commits that don't follow conventional commits format."""
    run_git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    invalid_commits = [
        (hash_, msg)
        for hash_, msg in get_branch_commits(base_branch)
        if not is_conventional_commit(msg)
    ]

    if not invalid_commits:
        print("[green]All commits follow conventional format[/green]")
        return

    print("\n[yellow]Found commits not following conventional format:[/yellow]")
    for hash_, message in invalid_commits:
        print(f"[red]{hash_[:8]}[/red] {message}")

    if not confirm_action("\nWould you like to fix these commits?"):
        return

    for hash_, message in invalid_commits:
        new_message = (
            f"fix: {message.strip()}"
            if not is_conventional_commit(message)
            else message
        )

        if confirm_action(f"\nAmend commit {hash_[:8]} with message: {new_message}?"):
            print(f"[blue]Current: {message}\nNew: {new_message}[/blue]")
            run_git(
                [
                    "-c",
                    "sequence.editor=:",
                    "rebase",
                    "-i",
                    "--exec",
                    f'git commit --amend -m "{new_message}" --no-edit',
                    f"{hash_}^",
                ]
            )
            print(f"[green]Successfully amended commit {hash_[:8]}[/green]")


@app.command(
    name="reset-history", help="Reset git history with a single initial commit."
)
@app.command(name="rh")
@git_command_handler
def reset_history():
    """Reset git history with a single initial commit."""
    print("[red]WARNING: This will irreversibly delete all commit history![/red]")

    if not all(
        [
            confirm_action("\nAre you absolutely sure you want to continue?", False),
            confirm_action("\nLast chance! This cannot be undone. Continue?", False),
        ]
    ):
        print("[yellow]Operation cancelled[/yellow]")
        return

    new_hash = run_git(
        ["commit-tree", "HEAD^{tree}", "-m", "chore(all): initial commit"]
    ).stdout.strip()
    run_git(["reset", new_hash])
    print("[green]Successfully reset git history[/green]")


@app.command(name="sync", help="Sync with main branch (checkout and pull rebase).")
@git_command_handler
def sync():
    """Sync with main branch."""
    run_git(["checkout", "main"])
    run_git(["pull", "--rebase"])
    print("[green]Successfully synced with main branch[/green]")


@app.command(name="squash", help="Squash all commits from current branch into one")
@git_command_handler
def squash(
    message: str = typer.Option(
        None, "--message", "-m", help="Commit message for the squashed commit"
    ),
    base_branch: str = typer.Option("main", help="Base branch to compare against"),
):
    """Squash all commits from current branch into one commit."""
    current_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

    if current_branch == base_branch:
        print(f"[red]Cannot squash when on {base_branch} branch[/red]")
        raise typer.Exit(1) from None

    commits = get_branch_commits(base_branch)
    if not commits:
        print("[yellow]No commits to squash[/yellow]")
        return

    # If no message provided, prompt user with last commit message as default
    if not message:
        last_commit_message = commits[-1][1]
        message = typer.prompt(
            "\nEnter commit message", default=last_commit_message, type=str
        )

    # Ensure message follows conventional commit format
    if not is_conventional_commit(message):
        if confirm_action(
            "\nMessage doesn't follow conventional format. Add 'fix:' prefix?"
        ):
            message = f"fix: {message}"

    # Get the point where the branch diverged from base
    merge_base = run_git(["merge-base", base_branch, "HEAD"]).stdout.strip()

    if not confirm_action(
        f"\nThis will squash {len(commits)} commits into one. Continue?"
    ):
        print("[yellow]Operation cancelled[/yellow]")
        return

    # Perform soft reset to the merge base
    run_git(["reset", "--soft", merge_base])

    # Create the new commit
    run_git(["commit", "-m", message])
    print(f"[green]Successfully squashed {len(commits)} commits into one[/green]")


if __name__ == "__main__":
    app()
