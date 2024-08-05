import click
from . import run_bot


@click.command()
@click.option(
    "--num-pings", "-n", default=10, help="Number of pings to send in each ping-process"
)
@click.option(
    "--proc",
    "-p",
    default=1,
    help="Number of ping/pong processes to run concurrently (default 1). ",
)
@click.option(
    "--window",
    "-w",
    default=1,
    help="Num of simultanous pings per process (default 1)",
)
def pingpong(proc, num_pings, window):
    run_bot(proc, num_pings, window)


if __name__ == "__main__":
    pingpong()
