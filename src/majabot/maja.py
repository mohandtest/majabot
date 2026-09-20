import logging
import re
import threading
from collections import deque
from typing import Any, Deque, Dict, Final, Optional, Tuple

import requests

from .spin_wheel import SpinWheelHandler
from zulip_bots.lib import AbstractBotHandler


class MajaHandler:
    """
    Maja chat bot backed by a local Ollama model.
    """

    OLLAMA_URL: Final = "http://localhost:11434/api/generate"
    MODEL: Final = "gemma3:1b"
    MAX_HISTORY_MESSAGES: Final = 12
    TYPING_REFRESH_SECONDS: Final = 8
    SYSTEM_PROMPT: Final = (
        "You are Maja, Studentmediene in Trondheim's IT mascot. "
        "Use the conversation history to understand follow-up questions. "
        "Answer the latest message only, verify corrections carefully, and "
        "do not invent an unrelated question or task. "
        "Feel free to be unhinged, humorous, and offensive. "
        "Talk like a 2010 internet Tumblr thread user and use modern TTTT vocabulary. "
        "Conversation context is formatted as 'name: message'. "
        "Return only Maja's answer. Do not prefix the answer with Maja's name, "
        "the user's name, or any speaker label."
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

        typing_stop = threading.Event()
        typing_thread = threading.Thread(
            target=self.refresh_typing_status,
            args=(message, bot_handler, typing_stop),
            daemon=True,
        )
        self.set_typing_status(message, bot_handler, "start")
        typing_thread.start()
        try:
            response = self.generate(prompt, conversation_key, self.sender_label(message))
            bot_handler.send_reply(message, response)
        finally:
            typing_stop.set()
            typing_thread.join(timeout=1)
            self.set_typing_status(message, bot_handler, "stop")

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

    def typing_request(
        self,
        message: Dict[str, Any],
        bot_handler: AbstractBotHandler,
        operation: str,
    ) -> Optional[Dict[str, Any]]:
        message_type = message.get("type")
        if message_type in {"stream", "channel"}:
            stream_id = message.get("stream_id")
            if stream_id is None:
                client = getattr(bot_handler, "_client", None)
                get_stream_id = getattr(client, "get_stream_id", None)
                if callable(get_stream_id):
                    try:
                        stream_id = get_stream_id(message.get("display_recipient", ""))["stream_id"]
                    except Exception:
                        logging.exception("Could not resolve the stream ID for typing status")

            if stream_id is None:
                return None

            return {
                "op": operation,
                "type": "stream",
                "stream_id": stream_id,
                "topic": str(message.get("subject", "")),
            }

        if message_type in {"private", "direct"}:
            bot_user_id = getattr(bot_handler, "user_id", None)
            recipients = message.get("display_recipient", [])
            recipient_ids = [
                person["id"]
                for person in recipients
                if isinstance(person, dict)
                and "id" in person
                and person["id"] != bot_user_id
            ]
            if not recipient_ids:
                return None
            return {"op": operation, "type": "direct", "to": recipient_ids}

        return None

    def set_typing_status(
        self,
        message: Dict[str, Any],
        bot_handler: AbstractBotHandler,
        operation: str,
    ) -> None:
        # zulip-bots currently keeps the Zulip client private on ExternalBotHandler.
        client = getattr(bot_handler, "_client", None)
        set_status = getattr(client, "set_typing_status", None)
        request = self.typing_request(message, bot_handler, operation)
        if not callable(set_status) or request is None:
            return

        try:
            set_status(request)
        except Exception:
            logging.exception("Failed to set Maja typing status to %s", operation)

    def refresh_typing_status(
        self,
        message: Dict[str, Any],
        bot_handler: AbstractBotHandler,
        stop_event: threading.Event,
    ) -> None:
        while not stop_event.wait(self.TYPING_REFRESH_SECONDS):
            self.set_typing_status(message, bot_handler, "start")

    def build_prompt(self, prompt: str, conversation_key: str, speaker: str) -> str:
        history = self.conversations.get(conversation_key, ())
        lines = [self.SYSTEM_PROMPT, "", "Conversation context starts:"]
        lines.extend(f"{role}: {text}" for role, text in history)
        lines.extend(
            (
                "Conversation context ends.",
                f"Current message from {speaker}: {prompt}",
                "Her følger et passende svar -->",
            )
        )
        return "\n".join(lines)

    def clean_response(self, response: str, speaker: str) -> str:
        label_pattern = rf"^(?:{re.escape(speaker)}|Maja)\s*:\s*"
        return re.sub(label_pattern, "", response.strip(), count=1, flags=re.IGNORECASE)

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

        generated = self.clean_response(generated, speaker)
        if generated == "":
            return "The model did not return any response text."

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
