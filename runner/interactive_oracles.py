"""Interactive oracles for hidden-API problems (invocation type
"interactive"), mirroring the GridMaster pattern: each oracle wraps the
case's hidden state, charges a query budget on every access, and — where
the solution method returns nothing — reports a judged outcome from its
own final state.

GridMaster itself lives in python_harness.py; these are the later
oracles, kept in their own module so the harness entry stays readable.
"""
from typing import Any


class Robot:
    """Oracle for 489 robot-room-cleaner: the solution drives a blind
    robot over a hidden room. Verdict = the exact set of cleaned cells,
    so any complete spiral/backtracking strategy compares equal."""

    DIRECTIONS = [(-1, 0), (0, 1), (1, 0), (0, -1)]  # up, right, down, left

    def __init__(self, room: list[list[int]], start: list[int], budget: int):
        self.room = room
        self.rows, self.cols = len(room), len(room[0]) if room else 0
        self.row, self.col = start
        self.face = 0  # starts facing up, LeetCode convention
        self.cleaned: set[tuple[int, int]] = set()
        self.budget = budget
        self.clean()

    def _spend(self) -> None:
        if self.budget <= 0:
            raise RuntimeError("Robot operation budget exhausted")
        self.budget -= 1

    def move(self) -> bool:  # noqa: N802 — LeetCode API
        self._spend()
        dr, dc = self.DIRECTIONS[self.face]
        nr, nc = self.row + dr, self.col + dc
        if not (0 <= nr < self.rows and 0 <= nc < self.cols) or self.room[nr][nc] == 0:
            return False  # wall or obstacle: stays in place
        self.row, self.col = nr, nc
        return True

    def turnLeft(self) -> None:  # noqa: N802 — LeetCode API
        self._spend()
        self.face = (self.face - 1) % 4

    def turnRight(self) -> None:  # noqa: N802 — LeetCode API
        self._spend()
        self.face = (self.face + 1) % 4

    def clean(self) -> None:  # noqa: N802 — LeetCode API
        self._spend()
        self.cleaned.add((self.row, self.col))

    def verdict(self) -> Any:
        return sorted(list(cell) for cell in self.cleaned)


class Master:
    """Oracle for 843 guess-the-word: guess(word) answers the number of
    matching positions; the secret must be found within the call budget
    (LeetCode allows 10)."""

    def __init__(self, wordlist: list[str], secret: str, budget: int):
        self.wordlist = wordlist
        self.secret = secret
        self.budget = budget
        self.calls = 0
        self.found = False

    def guess(self, word: str) -> int:
        if self.budget <= 0:
            raise RuntimeError("Master guess budget exhausted")
        self.budget -= 1
        self.calls += 1
        if word == self.secret:
            self.found = True
        return sum(a == b for a, b in zip(word, self.secret))

    def verdict(self) -> Any:
        return self.found


class MountainArray:
    """Oracle for 1095 find-in-mountain-array: get(index) with a hard
    call budget (LeetCode allows 100)."""

    def __init__(self, mountain: list[int], budget: int):
        self.mountain = mountain
        self.budget = budget

    def get(self, index: int) -> int:  # noqa: N802 — LeetCode API
        if self.budget <= 0:
            raise RuntimeError("MountainArray query budget exhausted")
        self.budget -= 1
        if not 0 <= index < len(self.mountain):
            raise IndexError("MountainArray index out of range")
        return self.mountain[index]

    def length(self) -> int:  # noqa: N802 — LeetCode API
        return len(self.mountain)


class BinaryMatrix:
    """Oracle for 1428 leftmost-column-with-at-least-a-one: get(row, col)
    and dimensions(), under LeetCode's 1000-call budget."""

    def __init__(self, matrix: list[list[int]], budget: int):
        self.matrix = matrix
        self.budget = budget

    def get(self, row: int, col: int) -> int:  # noqa: N802 — LeetCode API
        if self.budget <= 0:
            raise RuntimeError("BinaryMatrix query budget exhausted")
        self.budget -= 1
        return self.matrix[row][col]

    def dimensions(self) -> list[int]:  # noqa: N802 — LeetCode API
        return [len(self.matrix), len(self.matrix[0]) if self.matrix else 0]


class ArrayReader:
    """Oracle for 702 search-in-a-sorted-array-of-unknown-size: get(k)
    returns 2^31 - 1 past the end (LeetCode's out-of-range sentinel)."""

    SENTINEL = 2**31 - 1

    def __init__(self, arr: list[int], budget: int):
        self.arr = arr
        self.budget = budget

    def get(self, index: int) -> int:  # noqa: N802 — LeetCode API
        if self.budget <= 0:
            raise RuntimeError("ArrayReader query budget exhausted")
        self.budget -= 1
        if 0 <= index < len(self.arr):
            return self.arr[index]
        return self.SENTINEL


class InfiniteStream:
    """Oracle for 3023 find-pattern-in-infinite-stream-i: next() yields
    one bit at a time from a (finite but generous) recorded prefix."""

    def __init__(self, bits: list[int], budget: int):
        self.bits = bits
        self.budget = budget
        self.position = 0

    def next(self) -> int:  # noqa: N802 — LeetCode API
        if self.budget <= 0:
            raise RuntimeError("InfiniteStream query budget exhausted")
        self.budget -= 1
        value = self.bits[self.position]
        self.position += 1
        return value
