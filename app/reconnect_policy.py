from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ReconnectPolicy:
    max_attempts: int = 10
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0

    def delay(self, attempt: int) -> float:
        if attempt < 1:
            return self.base_delay_seconds
        return min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt - 1)))
