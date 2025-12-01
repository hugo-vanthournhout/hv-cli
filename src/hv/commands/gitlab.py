# typer cmd : hv gitlab renovate, hv gitlab reviews
import asyncio
from functools import lru_cache
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
import typer
from rich import print

from hv.utils import get_credential, load_config

app = typer.Typer(name="gitlab", help="GitLab operations")


def get_config():
    """Get GitLab configuration from variables.yaml."""
    config = load_config("variables")
    return config.get("gitlab", {})


def get_project_paths(
    nros: List[str] = None, types: List[str] = None, base_path: str = None
) -> List[str]:
    """Generate all possible project paths based on NROs and types."""
    config = get_config()
    nros = nros or config.get("default_nros", [])
    types = types or config.get("default_types", [])
    base_path = base_path or config.get("default_base_path", "")
    template = config.get("project_name_template")

    return [
        f"{base_path}/{nro}/{template.format(nro=nro, type=type_)}"
        for nro in nros
        for type_ in types
    ]


@lru_cache(
    maxsize=None
)  # None means unlimited cache size since project IDs rarely change
def get_project_id(project_path: str) -> Optional[int]:
    """Get project ID from project path."""
    config = get_config()
    gitlab_url = config.get("default_gitlab_url")
    token = get_credential("gitlab", "token")
    if not token:
        raise typer.Exit("GitLab token not found in credentials.yaml") from None

    headers = {"PRIVATE-TOKEN": token}
    encoded_path = quote(project_path, safe="")
    url = f"{gitlab_url}/api/v4/projects/{encoded_path}"

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["id"]
    return None


def _fetch_project_mrs(project_path: str, gitlab_url: str, headers: Dict) -> List[Dict]:
    """Fetch MRs for a single project (sync helper for async execution)."""
    project_id = get_project_id(project_path)
    if not project_id:
        print(f"[yellow]Could not find project: {project_path}[/yellow]")
        return []

    mrs_url = f"{gitlab_url}/api/v4/projects/{project_id}/merge_requests?state=opened"
    response = requests.get(mrs_url, headers=headers)

    if response.status_code == 200:
        mrs = [
            mr
            for mr in response.json()
            if mr["source_branch"].startswith("issue-renovate-")
        ]
        for mr in mrs:
            mr["project_path"] = project_path
        return mrs
    else:
        print(f"[red]Failed to get MRs for project: {project_path}[/red]")
        return []


async def get_renovate_mrs(project_paths: List[str]) -> List[Dict]:
    """Fetch all open Merge Requests created by Renovate across specified project paths."""
    config = get_config()
    gitlab_url = config.get("default_gitlab_url")
    token = get_credential("gitlab", "token")
    if not token:
        raise typer.Exit("GitLab token not found in credentials.yaml") from None

    headers = {"PRIVATE-TOKEN": token}
    loop = asyncio.get_event_loop()

    # Fetch all projects concurrently
    tasks = [
        loop.run_in_executor(None, _fetch_project_mrs, path, gitlab_url, headers)
        for path in project_paths
    ]
    results = await asyncio.gather(*tasks)

    # Flatten results
    renovate_mrs = []
    for mrs in results:
        renovate_mrs.extend(mrs)

    return renovate_mrs


def get_review_mrs() -> List[Dict]:
    """Fetch all open Merge Requests where user is a reviewer."""
    config = get_config()
    gitlab_url = config.get("default_gitlab_url")
    default_reviewer_path = config.get("default_reviewer_path")
    reviewer_username = config.get("default_reviewer_username")
    token = get_credential("gitlab", "token")

    if not token:
        raise typer.Exit("GitLab token not found in credentials.yaml") from None

    headers = {"PRIVATE-TOKEN": token}
    url = f"{gitlab_url}/api/v4/merge_requests?scope=all&state=opened&reviewer_username={reviewer_username}"

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"[red]Failed to get MRs: {response.text}[/red]")
        return []

    # Filter MRs based on project path and exclude Renovate MRs
    mrs = [
        mr
        for mr in response.json()
        if (
            mr["target_project_id"]
            and not mr["source_branch"].startswith("issue-renovate-")
            and default_reviewer_path in mr["references"]["full"]
        )
    ]

    return mrs


def merge_mr(project_id: int, mr_iid: int, title: str) -> bool:
    """Merge a specific MR and print result."""
    config = get_config()
    gitlab_url = config.get("default_gitlab_url")
    token = get_credential("gitlab", "token")
    if not token:
        raise typer.Exit("GitLab token not found in credentials.yaml") from None

    headers = {"PRIVATE-TOKEN": token}
    merge_url = (
        f"{gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/merge"
    )

    response = requests.put(merge_url, headers=headers)

    if response.status_code == 200:
        print(f"[green]Merged[/green] [{project_id}] {title}")
        return True

    try:
        error_msg = response.json().get("message", f"HTTP {response.status_code}")
    except Exception:
        error_msg = f"HTTP {response.status_code}"

    print(f"[red]{error_msg}[/red] [{project_id}] {title}")
    return False


def approve_mr_if_not_yet(project_id: int, mr_iid: int) -> bool:
    """Approve a specific MR if not already approved by current user."""
    config = get_config()
    gitlab_url = config.get("default_gitlab_url")
    token = get_credential("gitlab", "token")
    if not token:
        raise typer.Exit("GitLab token not found in credentials.yaml") from None

    headers = {"PRIVATE-TOKEN": token}

    # Check current approvals
    approvals_url = (
        f"{gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/approvals"
    )
    response = requests.get(approvals_url, headers=headers)
    if response.status_code != 200:
        return False

    # Check if already approved by current user
    approvals = response.json()
    if approvals.get("approved"):
        return True

    # Approve the MR
    approve_url = (
        f"{gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/approve"
    )
    response = requests.post(approve_url, headers=headers)
    return response.status_code == 201


async def process_mr(mr: Dict) -> bool:
    """Process a single MR: approve and merge. Returns success."""
    loop = asyncio.get_event_loop()
    title = mr["title"]
    project_id = mr["project_id"]
    mr_iid = mr["iid"]

    # Approve first
    await loop.run_in_executor(None, approve_mr_if_not_yet, project_id, mr_iid)

    # Then merge
    return await loop.run_in_executor(None, merge_mr, project_id, mr_iid, title)


async def process_all_mrs(mrs: List[Dict]) -> tuple[int, int]:
    """Process all MRs concurrently. Returns (success_count, total)."""
    tasks = [process_mr(mr) for mr in mrs]
    results = await asyncio.gather(*tasks)
    return sum(results), len(mrs)


def display_mrs(mrs: List[Dict]):
    """Display MRs in a formatted way, grouped by project."""
    if not mrs:
        print("[yellow]No open Renovate merge requests found[/yellow]")
        return

    projects_mrs = {}
    for mr in mrs:
        project_path = mr["project_path"]
        if project_path not in projects_mrs:
            projects_mrs[project_path] = []
        projects_mrs[project_path].append(mr)

    total_mrs = 0
    print("\n[blue]Found Renovate Merge Requests:[/blue]")
    print("=" * 80)

    for project_path, project_mrs in projects_mrs.items():
        print(f"\n[green]Project: {project_path}[/green]")
        print("-" * 80)
        for i, mr in enumerate(project_mrs, 1):
            print(f"{total_mrs + i}. {mr['title']}")
            print(f"   [link={mr['web_url']}]URL here[/link]")
        total_mrs += len(project_mrs)

    print(f"\n[blue]Total MRs found: {total_mrs}[/blue]")


def display_review_mrs(mrs: List[Dict]):
    """Display MRs where user is a reviewer in a formatted way."""
    if not mrs:
        print("[yellow]No open merge requests found where you are a reviewer[/yellow]")
        return

    print("\n[blue]Merge Requests to Review:[/blue]")
    print("=" * 80)

    for i, mr in enumerate(mrs, 1):
        print(f"\n{i}. [green]{mr['title']}[/green]")
        print(f"   Project: {mr['references']['full']}")
        print(f"   Author: {mr['author']['name']}")
        print(f"   [link={mr['web_url']}]URL here[/link]")

    print(f"\n[blue]Total MRs to review: {len(mrs)}[/blue]")


@app.command(name="renovate", help="Manage Renovate merge requests")
@app.command(name="ren")
def renovate_command(
    dry_run: bool = typer.Option(
        True,
        "--execute/--dry-run",
        help="Execute merges or just show what would be merged",
    ),
    nro: List[str] = typer.Option(
        None, "--nro", "-n", help="NRO to process (can be specified multiple times)"
    ),
    type: List[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Project type to process (can be specified multiple times)",
    ),
):
    """Manage and merge Renovate merge requests across projects."""
    # config = get_config()
    print("[blue]Load all mr, can take up to a minute[/blue]")
    project_paths = get_project_paths(nro, type)
    # print(project_paths)
    mrs = asyncio.run(get_renovate_mrs(project_paths))

    display_mrs(mrs)

    if not mrs:
        return

    # if dry_run:
    #     print("\n[yellow]Dry run mode - no merges will be performed[/yellow]")
    #     print("Run with --execute to perform merges")
    #     return

    if not typer.confirm("\nWould you like to merge these MRs?"):
        print("[yellow]Operation cancelled[/yellow]")
        return

    success_count, total = asyncio.run(process_all_mrs(mrs))
    print(f"\n[blue]Merged {success_count} out of {total} merge requests[/blue]")


@app.command(name="reviews", help="List merge requests where you are a reviewer")
@app.command(name="rev")
def list_reviews():
    """List all open merge requests where you are a reviewer."""
    try:
        mrs = get_review_mrs()
        display_review_mrs(mrs)
    except Exception as e:
        print(f"[red]Error listing reviews: {str(e)}[/red]")
        raise typer.Exit(1) from e


@app.command(name="cache", help="Show cache statistics and manage cache")
def cache_command(
    clear: bool = typer.Option(
        False, "--clear", "-c", help="Clear the project ID cache"
    ),
):
    """Show cache statistics or clear the cache."""
    if clear:
        get_project_id.cache_clear()
        print("[green]Cache cleared successfully[/green]")

    cache_info = get_project_id.cache_info()
    print("\n[blue]Cache Statistics:[/blue]")
    print(f"Hits: {cache_info.hits}")
    print(f"Misses: {cache_info.misses}")
    print(f"Current size: {cache_info.currsize}")


if __name__ == "__main__":
    app()
