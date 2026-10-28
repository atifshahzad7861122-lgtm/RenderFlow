"""
engine/updates/semver.py — Semantic Versioning 2.0.0 Parser & Comparator
========================================================================
Robust parser and comparator adhering to the Semantic Versioning 2.0.0 specification.
"""

from typing import Tuple, Optional, Any, List


class SemVer:
    """Semantic version parser and comparator (e.g. 2.2.0, 2.4.1-rc.1)."""

    def __init__(self, version_str: str):
        self.raw = str(version_str).strip()
        cleaned = self.raw.lstrip("vV").strip()

        # Split build metadata if present (e.g., 2.4.1+20261019)
        if "+" in cleaned:
            cleaned, self.build_metadata = cleaned.split("+", 1)
        else:
            self.build_metadata = None

        # Split prerelease if present (e.g., 2.4.1-beta.1)
        if "-" in cleaned:
            core_part, self.prerelease = cleaned.split("-", 1)
        else:
            core_part = cleaned
            self.prerelease = None

        # Parse core major.minor.patch
        parts = core_part.split(".")
        self.major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
        self.minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        self.patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    @classmethod
    def parse(cls, version_str: str) -> "SemVer":
        return cls(version_str)

    def core_tuple(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def _compare_prerelease(self, other_prerelease: Optional[str]) -> int:
        """
        Compare prerelease strings according to SemVer 2.0.0:
        - 1.0.0 > 1.0.0-alpha
        - 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1
        Returns:
          -1 if self < other
           0 if self == other
           1 if self > other
        """
        if self.prerelease is None and other_prerelease is None:
            return 0
        if self.prerelease is None and other_prerelease is not None:
            return 1  # non-prerelease has higher precedence
        if self.prerelease is not None and other_prerelease is None:
            return -1

        parts_a = self.prerelease.split(".")
        parts_b = other_prerelease.split(".")

        for id_a, id_b in zip(parts_a, parts_b):
            is_num_a = id_a.isdigit()
            is_num_b = id_b.isdigit()

            if is_num_a and is_num_b:
                val_a = int(id_a)
                val_b = int(id_b)
                if val_a != val_b:
                    return 1 if val_a > val_b else -1
            elif is_num_a and not is_num_b:
                # Numeric identifiers always have lower precedence than non-numeric
                return -1
            elif not is_num_a and is_num_b:
                return 1
            else:
                # Both lexical
                if id_a != id_b:
                    return 1 if id_a > id_b else -1

        # If identical so far, the one with more parts has higher precedence
        if len(parts_a) != len(parts_b):
            return 1 if len(parts_a) > len(parts_b) else -1

        return 0

    def compare(self, other: Any) -> int:
        if not isinstance(other, SemVer):
            other = SemVer(str(other))

        if self.core_tuple() != other.core_tuple():
            return 1 if self.core_tuple() > other.core_tuple() else -1

        return self._compare_prerelease(other.prerelease)

    def __lt__(self, other: Any) -> bool:
        return self.compare(other) < 0

    def __le__(self, other: Any) -> bool:
        return self.compare(other) <= 0

    def __gt__(self, other: Any) -> bool:
        return self.compare(other) > 0

    def __ge__(self, other: Any) -> bool:
        return self.compare(other) >= 0

    def __eq__(self, other: Any) -> bool:
        return self.compare(other) == 0

    def __ne__(self, other: Any) -> bool:
        return self.compare(other) != 0

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            s += f"-{self.prerelease}"
        return s

    def __repr__(self) -> str:
        return f"SemVer('{str(self)}')"
