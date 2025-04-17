# src/hv/commands/gcloud.py
import json
import os
import subprocess
from typing import List

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


def get_internal_project_id(nro: str) -> str:
    """Generate the internal project ID for a given NRO."""
    return f"gp-{nro}-data-internal"


@app.command(name="policy_id", help="List all policy tags IDs for specified NROs")
@app.command(name="policy_tags")
def policy_id(
    nro: List[str] = typer.Option(
        None, "--nro", "-n", help="NRO to process (can be specified multiple times)"
    ),
    output_format: str = typer.Option(
        "dbt", "--format", "-f", help="Output format: dbt, json, or raw"
    ),
    location: str = typer.Option(
        "europe-west1", "--location", "-l", help="GCloud location for policy tags"
    ),
):
    """Get policy tag IDs from GCloud BigQuery for specified NROs."""
    variables_config = load_config("variables")
    default_nros = variables_config.get("gitlab", {}).get("default_nros", [])
    
    # Use provided NROs or default from config
    nros_to_process = nro if nro else default_nros
    
    # Set authentication
    set_gcloud_auth()
    
    all_policy_tags = {}
    
    for nro in nros_to_process:
        project_id = get_internal_project_id(nro)
        print(f"[blue]Fetching policy tags for {nro} (project: {project_id})[/blue]")
        
        try:
            # Run gcloud command to list policy tags
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
                taxonomy.get("displayName", "")
                taxonomy_id = taxonomy.get("name", "")
                
                # Get policy tags within the taxonomy
                policy_cmd = [
                    "gcloud", "data-catalog", "taxonomies", "policy-tags", "list",
                    f"--taxonomy={taxonomy_id}",
                    f"--location={location}",
                    "--format=json"
                ]
                
                policy_result = subprocess.run(policy_cmd, capture_output=True, text=True, check=True)
                policy_tags = json.loads(policy_result.stdout)
                
                for tag in policy_tags:
                    tag_name = tag.get("displayName", "")
                    tag_id = tag.get("name", "").split("/")[-1]
                    
                    # Store the tag in the format nro_policy_tags[tag_name] = tag_id
                    nro_policy_tags[tag_name] = tag_id
            
            all_policy_tags[nro] = nro_policy_tags
            
        except subprocess.CalledProcessError as e:
            print(f"[red]Error fetching policy tags for {nro}: {e.stderr}[/red]")
        except Exception as e:
            print(f"[red]Error for {nro}: {str(e)}[/red]")
    
    # Output the results
    if output_format == "dbt":
        print("\n[green]Policy Tag IDs in DBT format:[/green]")
        print("=" * 80)
        for nro, tags in all_policy_tags.items():
            print(f"\n[blue]{nro.upper()}:[/blue]")
            for tag_name, tag_id in tags.items():
                print(f"  {tag_name}: {tag_id}")
    
    elif output_format == "json":
        print("\n[green]Policy Tag IDs in JSON format:[/green]")
        print(json.dumps(all_policy_tags, indent=2))
    
    elif output_format == "raw":
        print("\n[green]Raw Policy Tag IDs:[/green]")
        print(all_policy_tags)
    
    return all_policy_tags


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
    
    for nro in nros_to_process:
        print(f"\n[blue]Projects for NRO: {nro}[/blue]")
        print("-" * 60)
        
        # Show the three main project types
        print(f"gp-{nro}-data-internal")
        print(f"gp-{nro}-data-marts")
        print(f"gp-{nro}-data-raw")
        
        # Additional project types
        for type_ in default_types:
            print(f"gp-{nro}-data-platform-{type_}")


if __name__ == "__main__":
    app()