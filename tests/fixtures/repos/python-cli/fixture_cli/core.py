"""Core logic for the crawl fixture."""

import json


class Engine:
    """Renders a greeting as JSON."""

    def __init__(self, greeting: str) -> None:
        self.greeting = greeting

    def render(self) -> str:
        """Render the greeting payload."""
        return format_payload(self.greeting)


def format_payload(text: str) -> str:
    """Format text as a JSON payload."""
    return json.dumps({"message": text}, sort_keys=True)
