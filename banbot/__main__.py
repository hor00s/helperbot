# mypy: disable-error-code="attr-defined"
import os
import sys
import praw
import time
import signal
import cProfile
import traceback
import datetime as dt
import threading as thr
from jsonwrapper import AutoSaveDict
from logger import Logger, get_color
from prawcore.exceptions import (
    TooManyRequests,
    RequestException,
)
from constants.constants import (
    SubmissionState,
    SubmissionType,
    AUTHOR,
    CREDS,
    CONFIG,
    DB_FILE,
    LOG_FILE,
    DEV_DB_FILE,
    CONFIG_FILE,
)
from typing import (
    Any,
    Set,
    Dict,
    Callable,
    Optional,
)
from sqlitemanager import (
    DB,
    Row,
    Table,
    Datatype,
    get_values,
)


assert len(sys.argv) > 1, "No command line arguments found"
file, *args = sys.argv
mode, *_ = args
modes = ("-rel", "-dev")
assert mode in modes, f"You have to pick a mode: {modes}"

if mode == "-rel":
    a = ""
    while True:
        a = input(
            "Are you sure you want to run the bot in release mode?(Y/n): "
        ).lower()
        if a in ("y", "n"):
            break
        else:
            print("Invalid answer")

    if a == "n":
        print("Aborting...")
        sys.exit(0)


def send_modmail(sub: praw.reddit.Subreddit, header: str, message: str) -> None:
    print(header, message, sep="\n")
    if mode == "-rel":
        sub.modmail(header, message)


def get_creds() -> Dict[str, str]:
    data = {
        "client_id": "",
        "client_secret": "",
        "user_agent": "BanBot",
        "username": "",
        "password": "",
    }
    creds_conf = AutoSaveDict(CREDS, **data)
    creds_conf.init()

    if not all(list(creds_conf.values())):
        for i, v in creds_conf.items():
            if not v:
                header = " ".join(i.split("_")).title()
                creds_conf[i] = input(f"{header}: ")

    return creds_conf


def on_error(sub: praw.reddit.Subreddit) -> Callable[[Any], Any]:
    def dec(func: Callable[[Any], Any]) -> Callable[[Any], Any]:
        def wrap(*args: Any, **kwargs: Any) -> int:
            try:
                func(*args, **kwargs)
            except Exception as e:
                mode = "w"
                if os.path.exists(LOG_FILE):
                    mode = "a"
                msg = f"An error has occured. Refer to {LOG_FILE} and inform the author at https://reddit.com/u/{AUTHOR}"
                log.error(msg)
                send_modmail(sub, "An error has occured", msg)
                with open(LOG_FILE, mode=mode) as f:
                    f.write(str(dt.datetime.now()))
                    f.write("\n")
                    f.write(traceback.format_exc())
                    f.write("\n\n")
                return 1
            else:
                return 0
        return wrap
    return dec


def profile_function(func):
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        result = func(*args, **kwargs)
        profiler.disable()
        profiler.print_stats()
        return result
    return wrapper


exit_event = thr.Event()
config = AutoSaveDict(
    CONFIG_FILE,
    **CONFIG,
)
config.init()
log = Logger(config["verbocity"])
reddit = praw.Reddit(**get_creds())  # type: ignore
sub = reddit.subreddit(config["sub"])
log.settings.update(info=1, warning=2, error=2, debug=2, custom=2)

table = {
    "id": Datatype.STR,
    "username": Datatype.STR_NOT_NULL,
    "title": Datatype.STR_NOT_NULL,
    "text": Datatype.STR,
    "date_created": Datatype.STR_NOT_NULL,
}
if mode == "-dev":
    db_path = DEV_DB_FILE
else:
    db_path = DB_FILE

db = DB(str(db_path))
table_name = "posts"
table = db.create_table(table_name, False, **table)  # type: ignore


def string_to_dt(date: str) -> dt.date:
    return dt.datetime.strptime(date, "%Y-%m-%d").date()


def get_days_between(date0: dt.date, date1: dt.date) -> int:
    df = date0 - date1
    return df.days


def get_submission_state(submission: praw.reddit.Submission) -> SubmissionState:
    if submission.author is None:
        return SubmissionState.REMOVED
    return SubmissionState.ACTIVE


def get_submission_type(submission: praw.reddit.Submission) -> SubmissionType:
    try:
        if submission.post_hint == "rich:video":
            return SubmissionType.VIDEO
        elif submission.post_hint == "image":
            return SubmissionType.IMAGE
        elif submission.crosspost_parent_list:
            return SubmissionType.CROSSPOST
        else:
            return SubmissionType.TEXT
    except AttributeError:
        return SubmissionType.UNKNOWN


@on_error(sub)
def scrape_data(table: Table, sub: praw.reddit.Subreddit, limit: Optional[int]) -> None:
    query = f"INSERT INTO {table_name} ({', '.join(table.get_cols())}) VALUES "
    submissions = sub.new(limit=limit)
    posts_saved = 0

    sub_queries = []
    for submission in submissions:
        if exit_event.is_set():
            break
        sub_state = get_submission_state(submission)

        if sub_state == SubmissionState.ACTIVE:
            # sub_type = get_submission_type(submission)
            submission_id = submission.id
            exists = table.get_row(id=submission_id)
            date_created = str(dt.datetime.fromtimestamp(submission.created).date())
            if exists is None:
                d = {
                    "id": submission_id,
                    "username": submission.author,
                    "title": submission.title,
                    "text": submission.selftext,
                    "date_created": date_created,
                }
                sub_queries.append(f"({get_values(**d)})")
                posts_saved += 1

    query += ",\n".join(sub_queries)
    if posts_saved:
        db.execute(query, False)
    log.debug(f"`{posts_saved}` New posts scraped")


@on_error(sub)
def check_data(table: Table, max_days: int, sub: praw.reddit.Subreddit) -> None:
    to_be_removed: Set[Row] = set()
    get_days = lambda d1: get_days_between(dt.datetime.now().date(), string_to_dt(d1))
    data = (row for row in table.fetch_all() if get_days(row.date_created) < max_days)  # type: ignore

    for idx, row in enumerate(data):
        if exit_event.is_set():
            break

        threshold = 30
        submission = None
        sub_state = None
        re_tries = 0

        # Attempt to get a post 5 times. If all fail, abort and go to the next
        while (submission is None) and (sub_state is None) and (re_tries <= 5):
            try:
                submission = reddit.submission(id=row.id)  # type: ignore
                sub_state = get_submission_state(submission)
            except (TooManyRequests, RequestException):
                re_tries += 1
                if re_tries <= 5:
                    seconds = threshold * re_tries
                    log.warning(
                        f"Request limit reached. `{seconds}` seconds cooldown before procceding"
                    )
                    time.sleep(seconds)
                else:
                    log.warning(
                        f"State for https://reddit.com/{row.id} can't be evaluated.\
                             This post will no longer be tracked\
                                Consider handling it manually. Moving on..."
                    )
                    to_be_removed.add(row)
                    break

        re_tries = 0
        if sub_state == SubmissionState.REMOVED:
            msg = f"Removed post found\n\nPost: reddit.com/{row.id}\n\nOP: reddit.com/user/{row.username}"
            send_modmail(sub, "POST REMOVED", msg)
            to_be_removed.add(row)

    total_found = len(to_be_removed)
    log.debug(f"{total_found} Posts found to be removed")
    for row in to_be_removed:
        row.delete()

    try:
        log.debug(f"`{idx + 1}` Posts in total have been checked")
    except UnboundLocalError:
        pass  # Means `data` was empty so `idx` was never and no posts were ever checked


def handle_sigint(*_: Any) -> None:
    log.custom(
        f"Program stopped by user. Exiting safely...",
        "exit event",
        color=get_color("orange"),
    )
    exit_event.set()


@on_error(sub)
def main() -> None:
    config["last_run"] = str(dt.datetime.now())
    limit = config["limit"]
    if mode == "-dev":
        limit = 50

    max_days = config["max_days"]
    table = db.get_table(table_name)

    scrape_proc = thr.Thread(target=scrape_data, args=(table, sub, limit))
    check_proc = thr.Thread(target=check_data, args=(table, max_days, sub))

    scrape_proc.start()
    check_proc.start()

    scrape_proc.join()
    check_proc.join()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_sigint)
    sys.exit(main())
