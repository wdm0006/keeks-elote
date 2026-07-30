from typing import Any, List, Protocol, Tuple, runtime_checkable


@runtime_checkable
class RatingArena(Protocol):
    def tournament(self, matchups: List[Tuple[Any, Any]]) -> Any: ...

    def expected_score(self, competitor: Any, opponent: Any) -> float: ...
