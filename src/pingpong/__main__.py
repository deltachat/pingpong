import asyncio
import click
from . import run_bot


@click.command()
@click.option("--limit", default=100, help="Maximum number of messages to send.")
@click.option(
    "--window", default=1, help="Number of messages to send at the same time."
)
def pingpong(window, limit):
    asyncio.run(run_bot(window, limit))


if __name__ == "__main__":
    pingpong()
