import secrets
from typing import Dict

from zulip_bots.lib import AbstractBotHandler


class SpinWheelHandler:
    """
    This bot spins a virtual wheel to randomly select a name from a comma-separated list.
    """

    def usage(self) -> str:
        return """
            This bot randomly selects a name from a list you provide.

            Usage:
            - @mention-bot name1, name2, name3
            - @mention-bot help

            Example:
            @mention-bot Alice, Bob, Charlie, Diana

            The bot will randomly pick one name from the list.
            """

    def handle_message(self, message: Dict[str, str], bot_handler: AbstractBotHandler) -> None:
        content = message["content"].strip()

        if content == "" or content.lower() == "help":
            bot_handler.send_reply(message, self.usage())
            return
        # Parse the comma-separated names
        names = [name.strip() for name in content.split(",") if name.strip()]

        if not names:
            bot_response = "Please provide at least one name. Use commas to separate multiple names."
            bot_handler.send_reply(message, bot_response)
            return

        if len(names) == 1:
            bot_response = f"Only one name provided: **{names[0]}**. They win by default! 🎉"
            bot_handler.send_reply(message, bot_response)
            return

        # Spin the wheel and pick a random name
        winner = secrets.choice(names)

        bot_response = f"🎡 Spinning the wheel...\n\n**The winner is: {winner}!** 🎉"
        bot_handler.send_reply(message, bot_response)


handler_class = SpinWheelHandler
