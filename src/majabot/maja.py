import logging
import re
from collections import deque
from typing import Any, Deque, Dict, Final, Tuple

import requests

from .spin_wheel import SpinWheelHandler
from zulip_bots.lib import AbstractBotHandler


class MajaHandler:
    """
    Maja chat bot backed by a local Ollama model.
    """

    OLLAMA_URL: Final = "http://localhost:11434/api/generate"
    MODEL: Final = "qwen2.5-coder:0.5b"
    MAX_HISTORY_MESSAGES: Final = 12
    SYSTEM_PROMPT: Final = (
        "You are Maja, studentmediene in Trondheim's IT Mascot"
        "Use the conversation history to understand follow-up questions. "
        "Answer the latest message only, verify corrections carefully, and "
        "do not invent an unrelated question or task."
        "Feel free to be unhinged, humorous and offensive"
        "Talk like a 2010 internet 4chan thread user, be unfiltered"
    )

    def __init__(self) -> None:
        self.spin_wheel_bot = SpinWheelHandler()
        self.conversations: Dict[str, Deque[Tuple[str, str]]] = {}

    def usage(self) -> str:
        return """
**Maja Bot**

Chat with Maja by mentioning the bot.

Commands:
• `spin [name1, name2, ...]` - Pick a random winner from names
• `help` or `hjelp` - Show this message
• `reset` - Forget the current conversation

Examples:
• `@majabot spin Alice, Bob, Charlie`
• `@majabot How do I parse JSON in Python?`
• `@majabot write a bash script to back up logs`
            """

    def handle_message(self, message: Dict[str, Any], bot_handler: AbstractBotHandler) -> None:
        content = str(message.get("content", "")).strip()
        prompt = self.extract_prompt(content, bot_handler.identity().mention)
        conversation_key = self.conversation_key(message)

        if prompt == "" or prompt.lower() in {"help", "hjelp"}:
            bot_handler.send_reply(message, self.usage())
            return

        if prompt.lower() in {"reset", "clear", "forget"}:
            self.conversations.pop(conversation_key, None)
            bot_handler.send_reply(message, "I forgot the conversation history for this chat.")
            return

        parts = prompt.split(None, 1)
        command = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        if command == "spin":
            self.handle_spin(message, bot_handler, args)
            return

        bot_handler.send_reply(
            message,
            self.generate(prompt, conversation_key, self.sender_label(message)),
        )

    def extract_prompt(self, content: str, bot_mention: str) -> str:
        # Remove the exact mention when available.
        content = content.replace(bot_mention, "", 1).strip()
        # Also support Zulip mentions containing a user ID, e.g. @**Maja|1017137**.
        content = re.sub(r"^@\*\*[^*]+\*\*\s*", "", content)
        # Plain mention fallback, e.g. @majabot.
        content = re.sub(r"^@\w+\s+", "", content).strip()
        return content

    def conversation_key(self, message: Dict[str, Any]) -> str:
        message_type = str(message.get("type", "conversation"))
        recipient = message.get("display_recipient")

        if isinstance(recipient, list):
            emails = sorted(
                str(person.get("email", ""))
                for person in recipient
                if isinstance(person, dict) and person.get("email")
            )
            recipient_key = ",".join(emails)
        else:
            recipient_key = str(recipient or message.get("sender_email", "unknown"))

        subject = str(message.get("subject", ""))
        return f"{message_type}:{recipient_key}:{subject}"

    def sender_label(self, message: Dict[str, Any]) -> str:
        return str(message.get("sender_full_name") or message.get("sender_email") or "User")

    def build_prompt(self, prompt: str, conversation_key: str, speaker: str) -> str:
        history = self.conversations.get(conversation_key, ())
        lines = [self.SYSTEM_PROMPT, "", "Conversation history:"]
        lines.extend(f"{role}: {text}" for role, text in history)
        lines.extend((f"{speaker}: {prompt}", "Maja:"))
        return "\n".join(lines)

    def generate(self, prompt: str, conversation_key: str, speaker: str) -> str:
        request_prompt = self.build_prompt(prompt, conversation_key, speaker)
        payload = {"model": self.MODEL, "prompt": request_prompt, "stream": False}

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

        generated = generated.strip()
        history = self.conversations.setdefault(
            conversation_key,
            deque(maxlen=self.MAX_HISTORY_MESSAGES),
        )
        history.extend(((speaker, prompt), ("Maja", generated)))
        return generated

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
