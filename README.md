# Maja Bot

Maja is a Zulip chatbot powered by a locally hosted Ollama language model. It
can answer questions, help with programming, and randomly select a winner
from a list of names.

## Features

- AI-powered chat using Ollama
- Programming assistance
- Random name selection with `spin`
- Help messages in English and Norwegian

## Requirements

- Python 3.9 or newer
- A Zulip bot account and API key
- [Ollama](https://ollama.com/) running locally
- The `qwen2.5-coder:0.5b` Ollama model

## Installation

Clone the repository and create a virtual environment outside the repository:

```bash
git clone https://github.com/mohandtest/majabot.git
cd majabot
python3 -m venv ~/zulip-bot
source ~/zulip-bot/bin/activate
pip install -r requirements.txt
pip install --editable ".[test]"
```

Install the Ollama model:

```bash
ollama pull qwen2.5-coder:0.5b
```

Download your bot's Zulip configuration file and save it as `zuliprc` in the
repository root. This file contains API credentials and is ignored by Git;
keep it private.

## Running the bot

Start Maja in the foreground:

```bash
PYTHONPATH=./src zulip-run-bot majabot.maja --config-file ./zuliprc
```

Or use the included scripts to run it in the background:

```bash
./start.sh
./stop.sh
```

By default, `start.sh` uses `~/zulip-bot/bin/zulip-run-bot`, writes the PID to
`majabot.pid`, and writes output to `majabot.log`. You can override the paths
with `MAJABOT_VENV`, `MAJABOT_CONFIG`, `MAJABOT_PID_FILE`, and
`MAJABOT_LOG_FILE`.

Check the status and logs with:

```bash
cat majabot.pid
tail -f majabot.log
```

## Commands

Mention the bot in Zulip to interact with it.

| Command | Description |
| --- | --- |
| `@majabot help` | Show the help message |
| `@majabot hjelp` | Show the help message |
| `@majabot spin Alice, Bob, Charlie` | Select a random winner |
| `@majabot explain recursion` | Ask the AI a question |

## Configuration

Maja uses the local Ollama API at
`http://localhost:11434/api/generate` and the
`qwen2.5-coder:0.5b` model. Change these values in
[src/majabot/maja.py](src/majabot/maja.py).

## Tests

Install the test extra and run:

```bash
pip install --editable ".[test]"
python -m pytest
```

## License

Maja includes the spin-wheel bot code from the Zulip Python API project and
retains its applicable Apache License 2.0 notices. See [LICENSE](LICENSE),
[NOTICE](NOTICE), and [THIRDPARTY](THIRDPARTY).
