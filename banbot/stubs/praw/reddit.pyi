from typing import Any, Iterator, Optional

class Redditor:
    name: str

class Subreddit:
    def new(self, limit: Optional[int]) -> Iterator[Any]: ...

class Submission:
    author: Redditor
