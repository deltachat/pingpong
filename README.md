# Delta Chat latency measurement tool

This is a tool to measure the latency of sending the messages
using [Delta Chat core](https://github.com/deltachat/deltachat-core-rust).

## Install the Delta Chat core

The tool uses JSON-RPC Python bindings to the Delta Chat core.
To run the tool you need a `deltachat-rpc-server` installed.
You can download the binary
from the [Releases page](https://github.com/deltachat/deltachat-core-rust/releases)
of the Delta Chat core repostiory.

Make sure the binary is in the PATH by running `deltachat-rpc-server --version`:
```
$ deltachat-rpc-server --version
1.117.0
```

## Setup a development environment

The recommended way to setup a development environment
is to use a virtual Python environment.

Setup a virtual environment with the latest version
of `pip` and [setuptools](https://setuptools.pypa.io/):
```
python -m venv --clear --upgrade-deps env
```

Install the package into created environment:
```
env/bin/pip install -e .
```

Check that the program runs:
```
env/bin/python -m pingpong --help
```

## Run the measurement tool

To run the measurement tool you need to set the `DCC_NEW_TMP_EMAIL` environment variable
to the [mailadm server](https://mailadm.readthedocs.io/) URL.

After that, the simplest way is to run the measurement tool without the arguments:
```
env/bin/python -m pingpong
```

By default the tool creates two accounts.
The second account acts as an echo server and replies to each message sent from the first account.
The first account sends sends 100 messages to the second acccount, one at a time.
Each time a reply is received, it outputs the number of the received message and the delay to the standard output in a CSV format:
```
1,5.154420852661133
2,7.190616846084595
3,9.349361419677734
4,11.396785259246826
5,13.714033842086792
...
95,200.9408040046692
96,203.29984092712402
97,205.56968116760254
98,207.704181432724
99,209.8039848804474
100,212.0004162788391
```

You can redirect the output to the file to process it later:
```
$ env/bin/python -m pingpong >out.csv
```

## Process the results

There is a `stat.pl` Perl script analyzing the output file printing basic statistics,
for example:
```
$ ./stat.pl out.csv
min:    1.12097477912903
p05:    1.12548685073853
median: 1.14409327507019
p95:    1.20510101318359
max:    1.22065734863281
```

If you want to visualize the data,
install [Matplotlib](https://matplotlib.org/) to plot the results
and [pandas](https://pandas.pydata.org/) to process the collected data:
```
. env/bin/activate
pip install matplotlib pandas
```

You can then use the following Python script to plot the collected measurements as a [CDF](https://en.wikipedia.org/wiki/Cumulative_distribution_function):
```python
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from pathlib import Path

plt.figure()

for file in Path().glob("*.csv"):
    dat = pd.read_csv(file, names=["n", "time"])
    delay = list(dat["time"].values[1:] - dat["time"].values[:-1])
    plt.plot(sorted(delay), np.linspace(0, 1, len(delay)), label=file.name)

plt.ylim(ymin=0)
plt.xlim(xmin=0)
plt.xlabel("Delay, s")
plt.ylabel("CDF")
plt.grid()
plt.legend()
plt.savefig("out.png")
```

## Configure the experiment

The tool can be configured using the command line options.
To list them, run `env/bin/python -m pingpong --help`.

`--limit` configures the number of messages sent during the experment.
By default this number is 100.

`--window` configures the number of messages that can be sent at the same time.
By default this number is 1.
The experiment starts by sending a batch of this number of messages
and a new additional message is sent every time an echo response is received on the second account.
You can increase the `--window` to test how the delay increases with the load.
If you change this number you also likely want to increase the `--limit` proportionally
to ensure that the number of message batches sent during the experiment stays the same.

## Enable additional logging

`deltachat-rpc-server` supports the `RUST_LOG` variable
which can be used to enable additional logging,
for example:
```
RUST_LOG=repl=info,async_imap=trace,async_smtp=trace python -m pingpong
```
