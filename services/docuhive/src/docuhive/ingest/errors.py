"""Explicit reasons for preserving a file for review, or for waiting."""


class Quarantine(Exception):
    """The document itself cannot be processed; keep it with this reason."""


class Transient(Exception):
    """A service the step needs (the converter) is away; wait and try again."""
