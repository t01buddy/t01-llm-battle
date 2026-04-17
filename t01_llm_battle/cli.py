import typer

app = typer.Typer(help="LLM Battle Arena — compare LLMs side by side.")


@app.command()
def serve(
    port: int = typer.Option(7700, help="Port to listen on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
) -> None:
    """Start the LLM Battle server."""
    typer.echo(f"Starting server on port {port}...")


def main() -> None:
    app()
