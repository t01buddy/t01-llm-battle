import typer
import uvicorn

app = typer.Typer(help="LLM Battle Arena — compare LLMs side by side.")


@app.command()
def serve(
    port: int = typer.Option(7700, help="Port to listen on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
) -> None:
    """Start the LLM Battle server."""
    print(f"LLM Battle Arena running at http://localhost:{port}")
    if not no_browser:
        import threading
        import webbrowser

        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run(
        "t01_llm_battle.server:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        reload=False,
    )


def main() -> None:
    app()
