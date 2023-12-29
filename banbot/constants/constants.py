from pathlib import Path
from typing import TypedDict, Optional
from enum import IntEnum


__all__ = (
    "Config",
    "SubmissionState",
    "SubmissionType",
    "BASE_DIR",
    "LOG_FILE",
    "CONFIG_FILE",
    "DB_FILE",
    "DEV_DB_FILE",
    "CREDS",
    "AUTHOR",
    "CONFIG",
)


class Config(TypedDict):
    sub: str
    limit: Optional[int]
    max_days: int
    verbocity: int
    last_run: str


class SubmissionState(IntEnum):
    REMOVED = 0
    ACTIVE = 1


class SubmissionType(IntEnum):
    CROSSPOST = 1
    VIDEO = 2
    IMAGE = 3
    TEXT = 4
    UNKNOWN = 5


BASE_DIR: Path = Path(__file__).parent.parent.parent
LOG_FILE: Path = BASE_DIR / "logs.txt"
CONFIG_FILE: Path = BASE_DIR / "config.json"
DB_FILE: Path = BASE_DIR / "db.sqlite"
DEV_DB_FILE: Path = BASE_DIR / "dev_db.sqlite"
CREDS: Path = BASE_DIR / "creds.json"
AUTHOR: str = "kaerfkeerg"
CONFIG: Config = {
    "sub": "test",
    "limit": None,
    "max_days": 60,
    "verbocity": 2,
    "last_run": "",
}
