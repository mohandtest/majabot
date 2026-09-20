from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from requests.exceptions import ConnectionError

from majabot.maja import MajaHandler


class FakeBotHandler:
    def __init__(self, client=None) -> None:
        self.replies = []
        self._client = client

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


def test_models_lists_installed_ollama_models() -> None:
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "models": [{"name": "gemma3:1b"}, {"name": "qwen2.5-coder:0.5b"}]
    }

    with patch("majabot.maja.requests.get", return_value=mock_response):
        response = reply_for("models")

    assert "`gemma3:1b`" in response
    assert "`qwen2.5-coder:0.5b`" in response


def test_set_model_changes_model_for_that_user() -> None:
    tags_response = Mock()
    tags_response.raise_for_status.return_value = None
    tags_response.json.return_value = {"models": [{"name": "qwen2.5-coder:0.5b"}]}
    ollama_response = Mock()
    ollama_response.raise_for_status.return_value = None
    ollama_response.json.return_value = {"response": "Hello"}

    bot = MajaHandler()
    handler = FakeBotHandler()
    message = {"sender_email": "x@example.com", "content": "set qwen2.5-coder:0.5b"}

    with patch("majabot.maja.requests.get", return_value=tags_response):
        bot.handle_message(message, handler)

    assert handler.replies == ["I will use `qwen2.5-coder:0.5b` for your messages."]

    with patch("majabot.maja.requests.post", return_value=ollama_response) as post:
        bot.handle_message({**message, "content": "hello"}, handler)

    assert post.call_args.kwargs["json"]["model"] == "qwen2.5-coder:0.5b"


def test_set_provider_aarmo_uses_env_configuration(monkeypatch) -> None:
    monkeypatch.setattr(MajaHandler, "AARMO_OLLAMA_URL", "https://example.test/api/generate")
    monkeypatch.setattr(MajaHandler, "AARMO_TAGS_URL", "https://example.test/api/tags")
    monkeypatch.setattr(MajaHandler, "AARMO_MODEL", "Qwen3.6:27B")
    monkeypatch.setattr(MajaHandler, "AARMO_API_KEY", "secret")

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"response": "Hello from aarmo"}
    bot = MajaHandler()
    handler = FakeBotHandler()
    message = {"sender_email": "x@example.com", "content": "set-provider aarmo"}

    bot.handle_message(message, handler)
    assert handler.replies == [
        "I will use the `aarmo` provider with model `Qwen3.6:27B` for your messages."
    ]

    with patch("majabot.maja.requests.post", return_value=response) as post:
        bot.handle_message({**message, "content": "hello"}, handler)

    assert post.call_args.args[0] == "https://example.test/api/generate"
    assert post.call_args.kwargs["json"]["model"] == "Qwen3.6:27B"
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"}


def test_typing_status_wraps_chat_response() -> None:
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": "Hei fra Maja"}
    client = Mock()
    handler = FakeBotHandler(client)
    bot = MajaHandler()
    message = {
        "type": "stream",
        "stream_id": 123,
        "display_recipient": "general",
        "subject": "chat",
        "content": "hello",
    }

    with patch("majabot.maja.requests.post", return_value=mock_response):
        bot.handle_message(message, handler)

    assert client.set_typing_status.call_args_list == [
        call(
            {
                "op": "start",
                "type": "stream",
                "stream_id": 123,
                "topic": "chat",
            }
        ),
        call(
            {
                "op": "stop",
                "type": "stream",
                "stream_id": 123,
                "topic": "chat",
            }
        ),
    ]


def test_typing_status_for_direct_message() -> None:
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": "Hei fra Maja"}
    client = Mock()
    handler = FakeBotHandler(client)
    handler.user_id = 1017137
    bot = MajaHandler()
    message = {
        "type": "private",
        "display_recipient": [
            {"id": 1017137, "email": "maja@example.com"},
            {"id": 42, "email": "x@example.com"},
        ],
        "content": "hello",
    }

    with patch("majabot.maja.requests.post", return_value=mock_response):
        bot.handle_message(message, handler)

    assert client.set_typing_status.call_args_list == [
        call({"op": "start", "type": "direct", "to": [42]}),
        call({"op": "stop", "type": "direct", "to": [42]}),
    ]


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

    request_prompt = post.call_args.kwargs["json"]["prompt"]
    assert "explain recursion" in request_prompt
    assert "@majabot" not in request_prompt


def test_chat_message_strips_zulip_mention_with_user_id() -> None:
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": "It is 3."}

    with patch("majabot.maja.requests.post", return_value=mock_response) as post:
        assert reply_for("@**Maja|1017137** what is 2+1?") == "It is 3."

    assert "what is 2+1?" in post.call_args.kwargs["json"]["prompt"]


def test_chat_history_is_sent_for_follow_up_messages() -> None:
    first_response = Mock()
    first_response.raise_for_status.return_value = None
    first_response.json.return_value = {"response": "The sum is 3."}
    second_response = Mock()
    second_response.raise_for_status.return_value = None
    second_response.json.return_value = {"response": "2 + 1 is still 3."}

    bot = MajaHandler()
    handler = FakeBotHandler()
    message = {
        "type": "stream",
        "display_recipient": "general",
        "subject": "math",
        "sender_full_name": "X",
    }

    with patch(
        "majabot.maja.requests.post",
        side_effect=[first_response, second_response],
    ) as post:
        bot.handle_message({**message, "content": "what is 2+1?"}, handler)
        bot.handle_message({**message, "content": "That is wrong, try again"}, handler)

    second_prompt = post.call_args_list[1].kwargs["json"]["prompt"]
    assert "X: what is 2+1?" in second_prompt
    assert "Maja: The sum is 3." in second_prompt
    assert "X: That is wrong, try again" in second_prompt
    assert second_prompt.endswith("Her følger et passende svar -->")


def test_response_does_not_repeat_speaker_label() -> None:
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": "X X: The answer is 3."}
    bot = MajaHandler()
    handler = FakeBotHandler()
    message = {"sender_full_name": "X X", "content": "what is 2+1?"}

    with patch("majabot.maja.requests.post", return_value=mock_response):
        bot.handle_message(message, handler)

    assert handler.replies == ["The answer is 3."]


def test_reset_forgets_chat_history() -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"response": "First answer"}
    next_response = Mock()
    next_response.raise_for_status.return_value = None
    next_response.json.return_value = {"response": "Fresh answer"}

    bot = MajaHandler()
    handler = FakeBotHandler()
    message = {"type": "stream", "display_recipient": "general", "subject": "math"}

    with patch("majabot.maja.requests.post", side_effect=[response, next_response]) as post:
        bot.handle_message({**message, "content": "first question"}, handler)
        bot.handle_message({**message, "content": "reset"}, handler)
        bot.handle_message({**message, "content": "new question"}, handler)

    assert "First answer" not in post.call_args_list[1].kwargs["json"]["prompt"]


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
