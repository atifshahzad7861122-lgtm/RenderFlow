#!/usr/bin/env python3
"""
errors.py — Structured Error Hierarchy for Rendering Studio Engine v2.

Provides standardized, typed exception classes for all pipeline failure modes.
Ensures errors are never silent, include actionable diagnostic metadata,
and inherit from standard Python built-ins for complete backwards compatibility.
"""

from typing import Any, Dict, Optional


class RenderingEngineError(Exception):
    """Base class for all Rendering Studio Engine exceptions."""

    def __init__(
        self,
        message: str,
        code: str = "ENGINE_ERROR",
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = False
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.recoverable = recoverable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable
        }

    def __str__(self) -> str:
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"[{self.code}] {self.message} ({detail_str})"
        return f"[{self.code}] {self.message}"


class MissingAudioError(RenderingEngineError, FileNotFoundError):
    """Raised when narration or required audio file is missing or unreadable."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="MISSING_AUDIO", details=details, recoverable=False)


class InvalidImageError(RenderingEngineError, ValueError):
    """Raised when an image file is corrupted, unreadable, or invalid format."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_IMAGE", details=details, recoverable=False)


class MissingImageError(RenderingEngineError, FileNotFoundError):
    """Raised when a referenced image does not exist on disk."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="MISSING_IMAGE", details=details, recoverable=False)


class InvalidProjectError(RenderingEngineError, ValueError):
    """Raised when project directory structure or manifest is invalid."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_PROJECT", details=details, recoverable=False)


class MissingSTTModelError(RenderingEngineError, FileNotFoundError):
    """Raised when a requested STT model is missing from offline cache."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="MISSING_STT_MODEL", details=details, recoverable=True)


class STTFailureError(RenderingEngineError, RuntimeError):
    """Raised when speech-to-text transcription fails during execution."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="STT_FAILURE", details=details, recoverable=False)


class FFmpegFailureError(RenderingEngineError, RuntimeError):
    """Raised when an FFmpeg or FFprobe command fails with non-zero exit code."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="FFMPEG_FAILURE", details=details, recoverable=False)


class DiskFailureError(RenderingEngineError, OSError):
    """Raised when disk space is exhausted or I/O failure occurs."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="DISK_FAILURE", details=details, recoverable=False)


class PermissionFailureError(RenderingEngineError, PermissionError):
    """Raised when file or directory permission is denied."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="PERMISSION_DENIED", details=details, recoverable=False)


class SubprocessFailureError(RenderingEngineError, RuntimeError):
    """Raised when an external subprocess terminates unexpectedly."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="SUBPROCESS_FAILURE", details=details, recoverable=False)


class InvalidTimelineError(RenderingEngineError, ValueError):
    """Raised when scene timeline contains gaps, overlaps, or duration mismatches."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_TIMELINE", details=details, recoverable=False)


class InvalidTransitionError(RenderingEngineError, ValueError):
    """Raised when a transition violates scene duration limits or alignment."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_TRANSITION", details=details, recoverable=False)


class CorruptedTempFileError(RenderingEngineError, IOError):
    """Raised when a temporary intermediate file is truncated or corrupted."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="CORRUPTED_TEMP_FILE", details=details, recoverable=True)
