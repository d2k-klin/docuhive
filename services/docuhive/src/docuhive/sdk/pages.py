"""What a page action can answer besides a plain message."""

from dataclasses import dataclass, field


@dataclass
class Result:
    message: str = ""
    errors: dict[str, str] = field(default_factory=dict)  # form field -> what is wrong
    goto: str | None = None  # another page of this plugin, or "/documents/<id>"
    download: tuple[str, bytes, str] | None = None  # (file name, content, media type)


class ActionError(ValueError):
    """Raise with a message for the person: it is shown on the page, nothing is logged as a bug."""
