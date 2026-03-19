from unittest.mock import Mock, patch

from requests.exceptions import ConnectionError

from zulip_bots.test_lib import BotTestCase, DefaultTests


class TestMajaBot(BotTestCase, DefaultTests):
    bot_name = "maja"

    def test_help_message(self) -> None:
        self.verify_reply("help", self.usage_message())
        self.verify_reply("hjelp", self.usage_message())
        self.verify_reply("", self.usage_message())

    def test_chat_message(self) -> None:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"response": "Hei fra Maja"}

        with patch("requests.post", return_value=mock_response):
            self.verify_reply("how are you?", "Hei fra Maja")

    def test_spin_no_names(self) -> None:
        self.verify_reply(
            "spin",
            "Please provide names to spin. Example: `spin Alice, Bob, Charlie`",
        )

    def test_spin_multiple_names(self) -> None:
        with patch("secrets.choice", return_value="Bob"):
            self.verify_reply(
                "spin Alice, Bob, Charlie",
                "🎡 Spinning the wheel...\n\n**The winner is: Bob!** 🎉",
            )

    def test_chat_message_with_leading_mention(self) -> None:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"response": "Prompt stripped"}

        with patch("requests.post", return_value=mock_response) as post:
            self.verify_reply("@majabot explain recursion", "Prompt stripped")

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["prompt"], "explain recursion")

    def test_network_error(self) -> None:
        with patch("requests.post", side_effect=ConnectionError()):
            self.verify_reply(
                "hello",
                (
                    "I could not reach the local model at "
                    "`http://localhost:11434/api/generate`. "
                    "Please make sure Ollama is running."
                ),
            )

    def test_missing_response_field(self) -> None:
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"foo": "bar"}

        with patch("requests.post", return_value=mock_response):
            self.verify_reply("say hi", "The model did not return any response text.")

    def usage_message(self) -> str:
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
