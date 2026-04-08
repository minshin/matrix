from __future__ import annotations

import asyncio


class LLMBudget:
    def __init__(self, max_calls: int = 50) -> None:
        self.max_calls = max_calls
        self.used_calls = 0
        self._lock = asyncio.Lock()

    async def try_consume(self) -> bool:
        async with self._lock:
            if self.used_calls >= self.max_calls:
                return False
            self.used_calls += 1
            return True
