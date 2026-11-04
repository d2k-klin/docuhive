"""Fail closed before operations on a NAS mount; never create the mount point."""

from docuhive import vault


def available() -> bool:
    """The same check every vault write uses: the right vault is mounted and writable."""
    return vault.check().ok
