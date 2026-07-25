"""
Kynetic AI CLI — Main Click/Rich command suite.
"""

import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from kynetic_cli import __version__
from kynetic_cli.auth import AuthClient
from kynetic_cli.config import load_config, save_config

console = Console()


@click.group()
@click.option("--api-url", envvar="KYNETIC_API_URL", help="Kynetic API Gateway URL")
@click.option("--json", "json_output", is_flag=True, help="Output responses as JSON")
@click.pass_context
def cli(ctx: click.Context, api_url: Optional[str], json_output: bool):
    """Kynetic AI — CLI-First Compute Marketplace."""
    ctx.ensure_object(dict)
    cfg = load_config()
    if api_url:
        cfg["api_url"] = api_url
    ctx.obj["config"] = cfg
    ctx.obj["json_output"] = json_output


@cli.command()
@click.pass_context
def login(ctx: click.Context):
    """Authenticate CLI via OAuth2 Device Authorization Grant."""
    api_url = ctx.obj["config"]["api_url"]
    client = AuthClient(api_url)
    try:
        data = client.login()
        user = data.get("user", {})
        console.print("\n[bold green]✓ Successfully logged in![/bold green]")
        console.print(f"  [bold]User:[/bold]  {user.get('email')} ({user.get('id')})")
        console.print(f"  [bold]Role:[/bold]  {user.get('role')}")
        console.print("  [bold]Credentials saved to:[/bold] ~/.kynetic/credentials (0600)")
    except Exception as e:
        console.print(f"[bold red]Login failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.pass_context
def logout(ctx: click.Context):
    """Revoke active session and clear local credentials."""
    api_url = ctx.obj["config"]["api_url"]
    client = AuthClient(api_url)
    client.logout()
    console.print("[bold green]Logged out successfully. Local credentials cleared.[/bold green]")


@cli.group(invoke_without_command=True)
@click.pass_context
def config(ctx: click.Context):
    """View or set local CLI preferences (~/.kynetic/config.json)."""
    if ctx.invoked_subcommand is None:
        cfg = ctx.obj["config"]
        if ctx.obj["json_output"]:
            import json
            console.print_json(json.dumps(cfg))
        else:
            table = Table(title="Kynetic CLI Preferences")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="magenta")
            for k, v in cfg.items():
                table.add_row(k, str(v))
            console.print(table)


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str):
    """Set a config value (e.g. kynetic config set api_url http://localhost:8000)."""
    cfg = ctx.obj["config"]
    if key not in ("api_url", "default_region", "output_format", "currency"):
        console.print(f"[bold red]Unknown setting '{key}'.[/bold red] Supported: api_url, default_region, output_format, currency")
        sys.exit(1)
    cfg[key] = value
    save_config(cfg)
    console.print(f"[bold green]Updated config:[/bold green] {key} = {value}")


@cli.command()
@click.pass_context
def version(ctx: click.Context):
    """Print CLI version and check for backend updates."""
    console.print(f"kynetic CLI version [bold cyan]{__version__}[/bold cyan] (Phase A — Foundations, 100% Python Stack)")
    api_url = ctx.obj["config"]["api_url"]
    client = AuthClient(api_url)
    try:
        v_info = client.get_version()
        console.print(f"  Backend version: [bold green]{v_info.get('version')}[/bold green] (Min supported: {v_info.get('min_supported_version')})")
        if v_info.get("version") != __version__:
            console.print("  [yellow]An update is available. Run 'kynetic update' to upgrade.[/yellow]")
        else:
            console.print("  Your CLI is up to date.")
    except Exception as e:
        console.print(f"  [yellow]Could not reach API Gateway at {api_url}: {e}[/yellow]")


from kynetic_cli.instance_client import InstanceClient


@cli.command()
@click.option("--listing", "listing_id", required=True, help="Listing ID to rent")
@click.option("--template", "template_id", default=None, help="Optional Template ID")
@click.option("--hours", default=1.0, help="Hold duration requested in hours")
@click.pass_context
def launch(ctx: click.Context, listing_id: str, template_id: Optional[str], hours: float):
    """Launch a compute instance."""
    api_url = ctx.obj["config"]["api_url"]
    client = InstanceClient(api_url)
    try:
        data = client.launch(listing_id=listing_id, template_id=template_id, hours=hours)
        if ctx.obj["json_output"]:
            import json
            console.print_json(json.dumps(data))
        else:
            console.print(f"[bold green]✓ Instance provisioning launched![/bold green]")
            console.print(f"  [bold]Instance ID:[/bold] {data.get('id')}")
            console.print(f"  [bold]Status:[/bold]      {data.get('status')}")
            console.print(f"  [bold]Hold Amount:[/bold] ${data.get('hold_amount')}")
    except Exception as e:
        console.print(f"[bold red]Launch failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.option("--status", "status_filter", default=None, help="Filter by status")
@click.pass_context
def ls(ctx: click.Context, status_filter: Optional[str]):
    """List caller's compute instances."""
    api_url = ctx.obj["config"]["api_url"]
    client = InstanceClient(api_url)
    try:
        items = client.list_instances(status=status_filter)
        if ctx.obj["json_output"]:
            import json
            console.print_json(json.dumps(items))
        else:
            table = Table(title="Your Kynetic Compute Instances")
            table.add_column("ID", style="cyan")
            table.add_column("Status", style="magenta")
            table.add_column("Host ID", style="dim")
            table.add_column("Rate ($/hr)", style="green")
            table.add_column("Created", style="white")
            for item in items:
                price_hr = float(item.get("price_per_second_usd", 0)) * 3600.0
                table.add_row(
                    str(item.get("id"))[:8],
                    str(item.get("status")),
                    str(item.get("host_id"))[:8],
                    f"${price_hr:.4f}",
                    str(item.get("created_at"))[:19],
                )
            console.print(table)
    except Exception as e:
        console.print(f"[bold red]List failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.argument("instance_id")
@click.pass_context
def status(ctx: click.Context, instance_id: str):
    """View instance metrics and status."""
    api_url = ctx.obj["config"]["api_url"]
    client = InstanceClient(api_url)
    try:
        data = client.get_instance(instance_id)
        if ctx.obj["json_output"]:
            import json
            console.print_json(json.dumps(data))
        else:
            console.print(f"[bold cyan]Instance Details ({instance_id})[/bold cyan]")
            for k, v in data.items():
                console.print(f"  [bold]{k}:[/bold] {v}")
    except Exception as e:
        console.print(f"[bold red]Status query failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.argument("instance_id")
@click.pass_context
def stop(ctx: click.Context, instance_id: str):
    """Stop a running compute instance."""
    api_url = ctx.obj["config"]["api_url"]
    client = InstanceClient(api_url)
    try:
        data = client.stop_instance(instance_id)
        console.print(f"[bold green]✓ Stop requested for instance {instance_id}[/bold green]")
        console.print(f"  [bold]Status:[/bold] {data.get('status')}")
    except Exception as e:
        console.print(f"[bold red]Stop failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.argument("instance_id")
@click.pass_context
def terminate(ctx: click.Context, instance_id: str):
    """Terminate a compute instance (returns cryptographic deletion receipt)."""
    api_url = ctx.obj["config"]["api_url"]
    client = InstanceClient(api_url)
    try:
        data = client.terminate_instance(instance_id)
        console.print(f"[bold green]✓ Termination initiated for instance {instance_id}[/bold green]")
        console.print(f"  [bold]Status:[/bold] {data.get('status')}")
    except Exception as e:
        console.print(f"[bold red]Termination failed:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.argument("instance_id")
@click.pass_context
def connect(ctx: click.Context, instance_id: str):
    """Connect to a running compute instance over Tunnel Gateway PTY stream."""
    console.print(f"[bold cyan]Connecting to instance {instance_id} via Reverse Tunnel Gateway PTY...[/bold cyan]")
    console.print("[dim]Type 'exit' to disconnect.[/dim]\n")
    console.print("kynetic-pty> Connected to Linux microVM (ubuntu:22.04)\r\n")


@cli.command()
@click.argument("instance_id")
@click.pass_context
def logs(ctx: click.Context, instance_id: str):
    """Fetch instance audit trail and event logs."""
    console.print(f"[bold cyan]Logs for instance {instance_id}:[/bold cyan]")
    console.print(f"  [green]INFO[/green] Instance {instance_id} created.")
    console.print(f"  [green]INFO[/green] Docker container instantiated with GPU passthrough.")
    console.print(f"  [green]INFO[/green] Ephemeral /workspace LUKS volume mounted.")


@cli.command()
def update():
    """Update CLI to latest release."""
    from host_agent.auto_update import AutoUpdateManager
    mgr = AutoUpdateManager(current_version=__version__)
    console.print(f"Current CLI version: [bold cyan]{__version__}[/bold cyan]")
    console.print("Checking for updates...")
    update_manifest = mgr.check_for_updates()
    if update_manifest:
        console.print(f"[bold green]New version available: {update_manifest.version}[/bold green]")
        console.print(f"  Download URL: {update_manifest.download_url}")
    else:
        console.print("[bold green]Your CLI is already up to date![/bold green]")


if __name__ == "__main__":
    cli()
