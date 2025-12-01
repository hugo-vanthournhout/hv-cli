# src/hv/commands/gcloud.py
import asyncio
import json
import os
import subprocess
import yaml
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich import print

from hv.utils import get_credential, load_config

app = typer.Typer(name="gcloud", help="Google Cloud operations")


def get_config():
    """Get GCloud configuration from variables.yaml."""
    config = load_config("variables")
    return config.get("gcloud", {})


def set_gcloud_auth():
    """Set GCloud authentication using credentials file."""
    credentials_file = get_credential("gcloud", "credentials_file")
    if not credentials_file:
        raise typer.Exit("GCloud credentials file not found in credentials.yaml") from None
    
    # Replace $HOME with actual home path if needed
    if "$HOME" in credentials_file:
        credentials_file = credentials_file.replace("$HOME", os.path.expanduser("~"))
    
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_file


def get_project_id(nro: str, project_type: str) -> str:
    """Generate the project ID for a given NRO and type."""
    config = get_config()
    prefix = config.get("project_prefix")
    template = config.get("project_template")
    return template.format(prefix=prefix, nro=nro, type=project_type)


def get_internal_project_id(nro: str) -> str:
    """Generate the internal project ID for a given NRO."""
    config = get_config()
    policy_type = config.get("policy_tag_project_type")
    return get_project_id(nro, policy_type)


def _fetch_nro_policy_tags(nro: str, location: str) -> tuple[str, Dict, Optional[str]]:
    """Fetch policy tags for a single NRO. Returns (nro, policy_tags, error)."""
    project_id = get_internal_project_id(nro)

    try:
        # Run gcloud command to list taxonomies
        cmd = [
            "gcloud", "data-catalog", "taxonomies", "list",
            f"--project={project_id}",
            f"--location={location}",
            "--format=json"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        taxonomies = json.loads(result.stdout)

        nro_policy_tags = {}

        for taxonomy in taxonomies:
            taxonomy_display_name = taxonomy.get("displayName", "").lower()
            taxonomy_display_name = taxonomy_display_name.replace(f"-{nro}", "")
            taxonomy_id = taxonomy.get("name", "").split("/")[-1]

            if taxonomy_display_name not in nro_policy_tags:
                nro_policy_tags[taxonomy_display_name] = {}

            # Get policy tags within the taxonomy
            policy_cmd = [
                "gcloud", "data-catalog", "taxonomies", "policy-tags", "list",
                f"--taxonomy={taxonomy.get('name', '')}",
                f"--location={location}",
                "--format=json"
            ]

            policy_result = subprocess.run(policy_cmd, capture_output=True, text=True, check=True)
            policy_tags = json.loads(policy_result.stdout)

            for tag in policy_tags:
                tag_name = tag.get("displayName", "")
                tag_id = tag.get("name", "").split("/")[-1]
                clean_project_id = project_id.replace("-dev", "")
                full_path = f"projects/{clean_project_id}/locations/{location}/taxonomies/{taxonomy_id}/policyTags/{tag_id}"
                nro_policy_tags[taxonomy_display_name][tag_name] = full_path

        return (nro, nro_policy_tags, None)

    except subprocess.CalledProcessError as e:
        return (nro, {}, f"Error fetching policy tags: {e.stderr}")
    except Exception as e:
        return (nro, {}, f"Error: {str(e)}")


async def _fetch_all_policy_tags(nros: List[str], location: str) -> Dict:
    """Fetch policy tags for all NROs concurrently."""
    loop = asyncio.get_event_loop()

    tasks = [
        loop.run_in_executor(None, _fetch_nro_policy_tags, nro, location)
        for nro in nros
    ]
    results = await asyncio.gather(*tasks)

    all_policy_tags = {}
    for nro, tags, error in results:
        if error:
            print(f"[red]{error} for {nro}[/red]")
        else:
            print(f"[green]Fetched policy tags for {nro}[/green]")
            all_policy_tags[nro] = tags

    return all_policy_tags


@app.command(name="policy_id", help="List all policy tags with full paths for specified NROs")
@app.command(name="policy_tags")
def policy_id(
    nro: List[str] = typer.Option(
        None, "--nro", "-n", help="NRO to process (can be specified multiple times)"
    ),
    output_format: str = typer.Option(
        "json", "--format", "-f", help="Output format: json, yaml, or raw"
    ),
    location: str = typer.Option(
        None, "--location", "-l", help="GCloud location for policy tags"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Save output to a file"
    ),
):
    """Get policy tag IDs from GCloud BigQuery for specified NROs."""
    variables_config = load_config("variables")
    gcloud_config = get_config()
    default_nros = variables_config.get("gitlab", {}).get("default_nros", [])

    # Use provided location or default from config
    if not isinstance(location, str) or not location:
        location = gcloud_config.get("default_location")

    # Use provided NROs or default from config
    nros_to_process = nro if nro else default_nros

    # Set authentication
    set_gcloud_auth()

    print(f"[blue]Fetching policy tags for {len(nros_to_process)} NROs...[/blue]")
    all_policy_tags = asyncio.run(_fetch_all_policy_tags(nros_to_process, location))

    # Output the results
    output_content = None

    if output_format == "json":
        output_content = json.dumps(all_policy_tags, indent=4)
        print("\n[green]Policy Tag IDs in JSON format:[/green]")
        print(output_content)

    elif output_format == "yaml":
        output_content = yaml.dump(all_policy_tags, default_flow_style=False, sort_keys=False)
        print("\n[green]Policy Tag IDs in YAML format:[/green]")
        print(output_content)

    elif output_format == "raw":
        output_content = str(all_policy_tags)
        print("\n[green]Raw Policy Tag IDs:[/green]")
        print(output_content)

    elif output_format == "dbt":
        # DBT-compatible format: nested YAML structure for schema.yml
        dbt_structure = {}
        for nro, taxonomies in all_policy_tags.items():
            dbt_structure[nro] = {}
            for taxonomy_name, tags in taxonomies.items():
                for tag_name, tag_path in tags.items():
                    # Create a flat key for easy lookup in DBT
                    key = f"{taxonomy_name}_{tag_name}".lower().replace("-", "_")
                    dbt_structure[nro][key] = tag_path
        output_content = yaml.dump(dbt_structure, default_flow_style=False, sort_keys=False)
        print("\n[green]Policy Tag IDs in DBT format:[/green]")
        print(output_content)

    # Save to file if output_file is specified
    if output_file and output_content:
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w') as f:
                f.write(output_content)
            print(f"\n[green]Output saved to: {output_file}[/green]")
        except Exception as e:
            print(f"\n[red]Error saving to file: {str(e)}[/red]")


@app.command(name="projects", help="List GCloud projects for a specified NRO")
def list_projects(
    nro: List[str] = typer.Option(
        None, "--nro", "-n", help="NRO to process (can be specified multiple times)"
    ),
):
    """List all GCloud projects for specified NROs."""
    variables_config = load_config("variables")
    default_nros = variables_config.get("gitlab", {}).get("default_nros", [])
    default_types = variables_config.get("gitlab", {}).get("default_types", [])
    
    # Use provided NROs or default from config
    nros_to_process = nro if nro else default_nros
    
    # Set authentication
    set_gcloud_auth()
    
    gcloud_config = get_config()
    project_types = gcloud_config.get("project_types")

    for nro in nros_to_process:
        print(f"\n[blue]Projects for NRO: {nro}[/blue]")
        print("-" * 60)

        # Show project types from config
        for type_ in project_types:
            print(get_project_id(nro, type_))

        # Additional project types (platform types)
        for type_ in default_types:
            print(get_project_id(nro, f"platform-{type_}"))


if __name__ == "__main__":
    app()