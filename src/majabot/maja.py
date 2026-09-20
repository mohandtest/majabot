import logging
import re
from typing import Any, Dict, Final

import requests

from .spin_wheel import SpinWheelHandler
from zulip_bots.lib import AbstractBotHandler


class MajaHandler:
    """
    Maja chat bot backed by a local Ollama model.
    """

    OLLAMA_URL: Final = "http://localhost:11434/api/generate"
    MODEL: Final = "qwen2.5-coder:0.5b"

    def __init__(self) -> None:
        self.spin_wheel_bot = SpinWheelHandler()

    def usage(self) -> str:
        return """
**Maja Bot**

Chat with Maja by mentioning the bot.

Commands:
• `spin [name1, name2, ...]` - Pick a random winner from names
• `help` or `hjelp` - Show this message

Examples:
• `@majabot spin Alice, Bob, Charlie`
• `@majabot How do I parse JSON in Python?`
• `@majabot write a bash script to back up logs`
            """

    def handle_message(self, message: Dict[str, Any], bot_handler: AbstractBotHandler) -> None:
        content = str(message.get("content", "")).strip()
        prompt = self.extract_prompt(content, bot_handler.identity().mention)

        if prompt == "" or prompt.lower() in {"help", "hjelp"}:
            bot_handler.send_reply(message, self.usage())
            return

        parts = prompt.split(None, 1)
        command = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        if command == "spin":
            self.handle_spin(message, bot_handler, args)
            return

        bot_handler.send_reply(message, self.generate(prompt))

    def extract_prompt(self, content: str, bot_mention: str) -> str:
        # Zulip mention format, e.g. @**majabot**
        content = content.replace(bot_mention, "", 1).strip()
        # Plain mention fallback, e.g. @majabot
        content = re.sub(r"^@\w+\s+", "", content).strip()
        return content

    def generate(self, prompt: str) -> str:
        payload = {"model": self.MODEL, "prompt": prompt, "stream": False}

        try:
            response = requests.post(self.OLLAMA_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException:
            logging.exception("Failed to reach Ollama generate endpoint")
            return (
                "I could not reach the local model at "
                "`http://localhost:11434/api/generate`. "
                "Please make sure Ollama is running."
            )
        except ValueError:
            logging.exception("Ollama returned a non-JSON response")
            return "I got an invalid response from the local model service."

        generated = data.get("response")
        if not isinstance(generated, str) or generated.strip() == "":
            return "The model did not return any response text."

        return generated.strip()

    def handle_spin(self, message: Dict[str, Any], bot_handler: AbstractBotHandler, args: str) -> None:
        if not args:
            bot_handler.send_reply(
                message,
                "Please provide names to spin. Example: `spin Alice, Bob, Charlie`",
            )
            return

        spin_message = dict(message)
        spin_message["content"] = args
        self.spin_wheel_bot.handle_message(spin_message, bot_handler)


handler_class = MajaHandler
