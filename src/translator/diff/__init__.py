"""Git diff detection for .strings files."""

from .detector import DiffDetector, StringChange, ChangeType

__all__ = ["DiffDetector", "StringChange", "ChangeType"]
