from unittest.mock import patch

from zulip_bots.test_lib import BotTestCase, DefaultTests


class TestSpinWheelBot(BotTestCase, DefaultTests):
    bot_name = "spin_wheel"

    def test_help_message(self) -> None:
        self.verify_reply("help", self.usage_message())
        self.verify_reply("", self.usage_message())

    def test_single_name(self) -> None:
        bot_response = "Only one name provided: **Alice**. They win by default! 🎉"
        self.verify_reply("Alice", bot_response)

    def test_multiple_names_with_spaces(self) -> None:
        with patch("random.choice", return_value="Bob"):
            bot_response = "🎡 Spinning the wheel...\n\n**The winner is: Bob!** 🎉"
            self.verify_reply("Alice, Bob, Charlie", bot_response)

    def test_multiple_names_without_spaces(self) -> None:
        with patch("random.choice", return_value="Diana"):
            bot_response = "🎡 Spinning the wheel...\n\n**The winner is: Diana!** 🎉"
            self.verify_reply("Alice,Bob,Charlie,Diana", bot_response)

    def test_names_with_extra_whitespace(self) -> None:
        with patch("random.choice", return_value="Eve"):
            bot_response = "🎡 Spinning the wheel...\n\n**The winner is: Eve!** 🎉"
            self.verify_reply("  Alice  ,  Bob  ,  Charlie  ,  Eve  ", bot_response)

    def test_empty_names_filtered(self) -> None:
        with patch("random.choice", return_value="Frank"):
            bot_response = "🎡 Spinning the wheel...\n\n**The winner is: Frank!** 🎉"
            self.verify_reply("Alice,,Bob,,,Frank", bot_response)

    def test_only_commas(self) -> None:
        bot_response = "Please provide at least one name. Use commas to separate multiple names."
        self.verify_reply(",,,", bot_response)

    def usage_message(self) -> str:
        return """
            This bot randomly selects a name from a list you provide.
            Usage:
            - @mention-bot name1, name2, name3
            - @mention-bot help

            Example:
            @mention-bot Alice, Bob, Charlie, Diana

            The bot will randomly pick one name from the list.
            """
