# typer cmd : hv asana my-tasks, hv asana all-tasks, hv asana update-status
from typing import Dict, List

import requests
import typer
from rich import print
from rich.table import Table

from hv.utils import get_credential, load_config

app = typer.Typer(name="asana", help="Asana task management operations")


def get_config():
    config = load_config("variables")
    return config.get("asana", {})


def get_headers() -> Dict[str, str]:
    token = get_credential("asana", "token")
    if not token:
        raise typer.Exit("Asana token not found in credentials.yaml") from None
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def get_tasks(
    project_gid: str, assignee_gid: str = None, include_done: bool = True
) -> List[Dict]:
    """
    Get tasks from Asana project.

    Args:
        project_gid: Project ID
        assignee_gid: Optional assignee filter
        include_done: Whether to include tasks in 'Done' section
    """
    config = get_config()
    api_base_url = config.get("api_base_url", "https://app.asana.com/api/1.0")
    headers = get_headers()
    url = f"{api_base_url}/projects/{project_gid}/tasks"

    params = {
        "opt_fields": "name,completed,due_on,assignee.name,assignee.gid,memberships.project.gid,memberships.section.name,notes",
        "completed_since": "now",
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"[red]Error: {response.status_code} - {response.text}[/red]")
        raise typer.Exit(1) from None

    tasks = response.json().get("data", [])
    filtered_tasks = []
    for task in tasks:
        # Skip completed tasks
        if task.get("completed"):
            continue

        # Apply assignee filter
        if assignee_gid and (
            not task.get("assignee") or task["assignee"].get("gid") != assignee_gid
        ):
            continue

        # Apply done section filter
        if not include_done and is_task_in_done_section(task, project_gid):
            continue

        filtered_tasks.append(task)

    return filtered_tasks


def is_task_in_done_section(task: Dict, project_gid: str) -> bool:
    """Check if task is in Done section."""
    config = get_config()
    section_mapping = config.get("section_mapping", {})
    done_section_name = section_mapping.get("d", "Done")

    memberships = task.get("memberships", [])
    for membership in memberships:
        if (
            membership.get("project", {}).get("gid") == project_gid
            and membership.get("section", {}).get("name") == done_section_name
        ):
            return True
    return False


@app.command(name="my-tasks")
def list_my_tasks(
    include_done: bool = typer.Option(
        False, "--include-done", "-d", help="Include tasks in Done section"
    ),
):
    """List my tasks in the project"""
    config = get_config()
    project_gid = config.get("default_project_gid")
    assignee_gid = config.get("default_assignee_gid")

    try:
        tasks = get_tasks(project_gid, assignee_gid, include_done=include_done)
        display_tasks(tasks, project_gid, show_assignee=False)
    except Exception as e:
        print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1) from e


@app.command(name="all-tasks")
def list_all_tasks():
    """List all tasks in the project"""
    config = get_config()
    project_gid = config.get("default_project_gid")

    try:
        tasks = get_tasks(project_gid)
        display_tasks(tasks, project_gid)
    except Exception as e:
        print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1) from e


def display_tasks(tasks: List[Dict], project_gid: str, show_assignee: bool = True):
    """Display tasks in a formatted table."""
    if not tasks:
        print("[yellow]No tasks found[/yellow]")
        return

    table = Table(show_header=True)
    table.add_column("Section")
    table.add_column("Name")
    table.add_column("Due Date")
    if show_assignee:
        table.add_column("Assignee")

    for task in tasks:
        memberships = task.get("memberships", [])
        section = get_section_in_project(memberships, project_gid)
        name = task.get("name", "No name")
        due_date = task.get("due_on", "No due date")

        if show_assignee:
            assignee = task.get("assignee")
            assignee_name = (
                assignee.get("name", "Unassigned") if assignee else "Unassigned"
            )
            table.add_row(section, name, due_date, assignee_name)
        else:
            table.add_row(section, name, due_date)

    print(table)


def get_section_in_project(memberships: List[Dict], project_gid: str) -> str:
    """Get section name for a task in a specific project."""
    if not memberships:
        return "No section"

    for membership in memberships:
        project = membership.get("project", {})
        if project.get("gid") == project_gid:
            section = membership.get("section")
            if section:
                return section.get("name", "No section")
    return "No section"


@app.command(name="update-status")
@app.command(name="update")
@app.command(name="us")
def update_task_status(
    include_done: bool = typer.Option(
        False, "--include-done", "-d", help="Include tasks in Done section"
    ),
):
    """Update task status and add comments interactively."""
    config = get_config()
    project_gid = config.get("default_project_gid")
    assignee_gid = config.get("default_assignee_gid")
    section_mapping = config.get("section_mapping", {})
    api_base_url = config.get("api_base_url")

    tasks = get_tasks(project_gid, assignee_gid, include_done=include_done)
    headers = get_headers()

    print("\n[yellow]Section shortcuts:[/yellow]")
    for shortcut, section in section_mapping.items():
        print(f"{shortcut:<3} - {section}")
    print("n  - No change")

    for task in tasks:
        name = task.get("name", "Unnamed task")
        description = task.get("notes", "").strip()
        print(f"\n[blue]Task: {name}[/blue]")
        if description:
            print("\n[cyan]Description:[/cyan]")
            print(description)

        gitlab_link = typer.prompt("GitLab MR link [n]", default="n")
        if gitlab_link.lower() != "n":
            comment_text = typer.prompt("Additional comment [n]", default="n")
            comment = f"GitLab MR: {gitlab_link}"
            if comment_text.lower() != "n":
                comment += f"\n{comment_text}"

            comment_url = f"{api_base_url}/tasks/{task['gid']}/stories"
            requests.post(
                comment_url, headers=headers, json={"data": {"text": comment}}
            )

        status = typer.prompt("Move to section? (td/p/r/b/d/n)", default="n").lower()

        if status != "n" and status in section_mapping:
            section_name = section_mapping[status]
            project_sections_url = f"{api_base_url}/projects/{project_gid}/sections"
            sections_response = requests.get(project_sections_url, headers=headers)

            if sections_response.status_code == 200:
                sections = sections_response.json().get("data", [])
                target_section = next(
                    (s for s in sections if s["name"] == section_name), None
                )

                if target_section:
                    move_url = (
                        f"{api_base_url}/sections/{target_section['gid']}/addTask"
                    )
                    response = requests.post(
                        move_url, headers=headers, json={"data": {"task": task["gid"]}}
                    )

                    if response.status_code == 200:
                        print(f"[green]Moved task to {section_name}[/green]")
                    else:
                        print(f"[red]Failed to move task: {response.text}[/red]")
