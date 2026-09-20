from types import SimpleNamespace
from unittest.mock import Mock, patch

from requests.exceptions import ConnectionError

from majabot.maja import MajaHandler


class FakeBotHandler:
    def __init__(self) -> None:
        self.replies = []

    def identity(self) -> SimpleNamespace:
        return SimpleNamespace(mention="@**majabot**")

    def send_reply(self, message: dict, response: str) -> None:
        self.replies.append(response)


def reply_for(content: str) -> str:
    bot = MajaHandler()
    handler = FakeBotHandler()
    bot.handle_message({"content": content}, handler)
    assert len(handler.replies) == 1
    return handler.replies[0]


def test_help_message() -> None:
    expected = MajaHandler().usage()

    assert reply_for("help") == expected
    assert reply_for("hjelp") == expected
    assert reply_for("") == expected


def test_chat_message() -> None:
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": "Hei fra Maja"}

    with patch("majabot.maja.requests.post", return_value=mock_response):
        assert reply_for("how are you?") == "Hei fra Maja"


def test_spin_without_names() -> None:
    assert reply_for("spin") == "Please provide names to spin. Example: `spin Alice, Bob, Charlie`"


def test_spin_multiple_names() -> None:
    with patch("majabot.spin_wheel.secrets.choice", return_value="Bob"):
        assert reply_for("spin Alice, Bob, Charlie") == (
            "🎡 Spinning the wheel...\n\n**The winner is: Bob!** 🎉"
        )


def test_chat_message_strips_leading_mention() -> None:
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": "Prompt stripped"}

    with patch("majabot.maja.requests.post", return_value=mock_response) as post:
        assert reply_for("@majabot explain recursion") == "Prompt stripped"

    assert post.call_args.kwargs["json"]["prompt"] == "explain recursion"


def test_network_error() -> None:
    with patch("majabot.maja.requests.post", side_effect=ConnectionError()):
        assert reply_for("hello") == (
            "I could not reach the local model at "
            "`http://localhost:11434/api/generate`. "
            "Please make sure Ollama is running."
        )


def test_missing_response_field() -> None:
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"foo": "bar"}

    with patch("majabot.maja.requests.post", return_value=mock_response):
        assert reply_for("say hi") == "The model did not return any response text."
