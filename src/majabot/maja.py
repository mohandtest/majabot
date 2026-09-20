import logging
import os
import re
import threading
from collections import deque
from typing import Any, Deque, Dict, Final, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from .spin_wheel import SpinWheelHandler
from zulip_bots.lib import AbstractBotHandler

load_dotenv()


def tags_url_for(generate_url: str) -> str:
    if not generate_url:
        return ""
    return generate_url.rsplit("/", 1)[0] + "/tags"


def timeout_from_env() -> float:
    """Return a positive model request timeout from the environment."""
    try:
        timeout = float(os.getenv("OLLAMA_TIMEOUT", "120"))
    except (TypeError, ValueError):
        return 120.0
    return timeout if timeout > 0 else 120.0


class MajaHandler:
    """
    Maja chat bot backed by a local Ollama model.
    """

    LOCAL_OLLAMA_URL: Final = "http://localhost:11434/api/generate"
    LOCAL_TAGS_URL: Final = "http://localhost:11434/api/tags"
    LOCAL_MODEL: Final = os.getenv("LOCAL_MODEL", "qwen2.5-coder:0.5b")
    AARMO_OLLAMA_URL: Final = os.getenv("OLLAMA_URL", "").strip()
    AARMO_TAGS_URL: Final = os.getenv(
        "OLLAMA_TAGS_URL", tags_url_for(AARMO_OLLAMA_URL)
    ).strip()
    AARMO_MODEL: Final = os.getenv("MODEL", "").strip() or LOCAL_MODEL
    AARMO_API_KEY: Final = os.getenv("OLLAMA_API_KEY", "").strip()
    OLLAMA_TIMEOUT: Final = timeout_from_env()
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
        self.model_preferences: Dict[str, str] = {}
        self.provider_preferences: Dict[str, str] = {}

    def usage(self) -> str:
        return """
**Maja Bot**

Chat with Maja by mentioning the bot.

Commands:
• `spin [name1, name2, ...]` - Pick a random winner from names
• `help` or `hjelp` - Show this message
• `reset` - Forget the current conversation
• `models` - List installed Ollama models
• `set <model-name>` - Use an installed model for your messages
• `set-provider local|aarmo` - Choose the Ollama provider

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

        if command == "set-provider":
            bot_handler.send_reply(message, self.set_provider(message, args))
            return

        if command == "models":
            bot_handler.send_reply(message, self.models_reply(message))
            return

        if command == "set":
            bot_handler.send_reply(message, self.set_model(message, args))
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
            provider = self.selected_provider(message)
            ollama_url, _, api_key = self.provider_config(provider)
            response = self.generate(
                prompt,
                conversation_key,
                self.sender_label(message),
                self.selected_model(message),
                ollama_url,
                api_key,
                provider,
            )
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

    def model_preference_key(self, message: Dict[str, Any]) -> str:
        return str(
            message.get("sender_email")
            or message.get("sender_id")
            or message.get("sender_full_name")
            or "default"
        )

    def selected_provider(self, message: Dict[str, Any]) -> str:
        return self.provider_preferences.get(self.model_preference_key(message), "local")

    def provider_config(self, provider: str) -> Tuple[str, str, str]:
        if provider == "aarmo":
            return self.AARMO_OLLAMA_URL, self.AARMO_TAGS_URL, self.AARMO_API_KEY
        return self.LOCAL_OLLAMA_URL, self.LOCAL_TAGS_URL, ""

    def selected_model(self, message: Dict[str, Any]) -> str:
        preference = self.model_preferences.get(self.model_preference_key(message))
        if preference:
            return preference
        return self.AARMO_MODEL if self.selected_provider(message) == "aarmo" else self.LOCAL_MODEL

    def request_headers(self, api_key: str) -> Dict[str, str]:
        if not api_key:
            return {}
        return {"Authorization": f"Bearer {api_key}"}

    def available_models(self, message: Dict[str, Any]) -> Optional[List[str]]:
        provider = self.selected_provider(message)
        _, tags_url, api_key = self.provider_config(provider)
        if not tags_url:
            return None

        try:
            response = requests.get(
                tags_url,
                headers=self.request_headers(api_key),
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException:
            logging.exception("Failed to list Ollama models")
            return None
        except ValueError:
            logging.exception("Ollama returned invalid model-list data")
            return None

        models = data.get("models")
        if not isinstance(models, list):
            return None

        names = {
            model.get("name") or model.get("model")
            for model in models
            if isinstance(model, dict)
            and isinstance(model.get("name") or model.get("model"), str)
        }
        return sorted(names)

    def models_reply(self, message: Dict[str, Any]) -> str:
        provider = self.selected_provider(message)
        models = self.available_models(message)
        if provider == "aarmo" and not self.AARMO_OLLAMA_URL:
            return "The aarmo provider is not configured. Set `OLLAMA_URL` in `.env` first."
        if models is None:
            return "I could not get the installed models from Ollama. Is Ollama running?"
        if not models:
            return "Ollama is running, but no models are installed."

        model_list = "\n".join(f"• `{model}`" for model in models)
        return f"**Installed Ollama models:**\n{model_list}\n\nUse `set <model-name>` to choose one."

    def set_model(self, message: Dict[str, Any], model_name: str) -> str:
        if not model_name:
            return "Usage: `set <model-name>`. Use `models` to list installed models."

        models = self.available_models(message)
        if self.selected_provider(message) == "aarmo" and not self.AARMO_OLLAMA_URL:
            return "The aarmo provider is not configured. Set `OLLAMA_URL` in `.env` first."
        if models is None:
            return "I could not get the installed models from Ollama. Is Ollama running?"
        if model_name not in models:
            return f"Model `{model_name}` is not installed. Use `models` to see available models."

        self.model_preferences[self.model_preference_key(message)] = model_name
        return f"I will use `{model_name}` for your messages."

    def set_provider(self, message: Dict[str, Any], provider: str) -> str:
        provider = provider.lower()
        if provider not in {"local", "aarmo"}:
            return "Usage: `set-provider local` or `set-provider aarmo`."
        if provider == "aarmo" and not self.AARMO_OLLAMA_URL:
            return "The aarmo provider is not configured. Set `OLLAMA_URL` in `.env` first."

        preference_key = self.model_preference_key(message)
        previous_provider = self.provider_preferences.get(preference_key, "local")
        self.provider_preferences[preference_key] = provider
        if previous_provider != provider:
            self.model_preferences.pop(preference_key, None)
        model = self.selected_model(message)
        return f"I will use the `{provider}` provider with model `{model}` for your messages."

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

    def generate(
        self,
        prompt: str,
        conversation_key: str,
        speaker: str,
        model: str,
        ollama_url: str,
        api_key: str,
        provider: str,
    ) -> str:
        request_prompt = self.build_prompt(prompt, conversation_key, speaker)
        payload = {"model": model, "prompt": request_prompt, "stream": False}

        try:
            response = requests.post(
                ollama_url,
                json=payload,
                headers=self.request_headers(api_key),
                timeout=self.OLLAMA_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            logging.exception("Timed out waiting for the %s model service", provider)
            return (
                f"The {provider} model took too long to respond "
                f"(timeout: {self.OLLAMA_TIMEOUT:g} seconds). "
                "Reasoning models can take longer; increase `OLLAMA_TIMEOUT` in `.env` if needed."
            )
        except requests.exceptions.RequestException:
            logging.exception("Failed to reach the %s model service", provider)
            if provider == "local":
                return "I could not reach the local Ollama model. Please make sure Ollama is running."
            return f"I could not reach the configured {provider} model service."
        except ValueError:
            logging.exception("The %s model service returned invalid JSON", provider)
            return f"I got an invalid response from the {provider} model service."

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
