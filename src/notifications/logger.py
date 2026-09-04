"""
Centralized logging setup.

Replaces the run_daily.bat ">>" text-file redirect that Modules 1-5
used as a stopgap. This gives Veltrix a proper rotating log file (so
logs/ never grows without bound) plus console output, so running
`python main.py` manually still shows progress in the terminal.

Design decision: Python's built-in `logging` module with a
RotatingFileHandler, not a third-party logging library. This project
runs once a day from one machine -- there's no need for structured
JSON logs, log aggregation, or anything a heavier logging stack would
add. A single rotating text file is easy to open and read by hand,
which matters for a solo operator checking "did last night's run go
okay?".
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOGGER_NAME = "veltrix"

# Keep roughly the last ~35 MB of history (5 MB x 7 files) -- generous
# for a once-a-day job's worth of text logs, without growing forever.
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 7


def get_logger(log_dir: str = "logs", log_file: str = "veltrix.log") -> logging.Logger:
    """
    Return the shared "veltrix" logger, configured on first call with
    a rotating file handler and a console handler. Safe to call
    multiple times (e.g. once per module) -- handlers are only
    attached once, so log lines are never duplicated.
    """
    logger = logging.getLogger(LOGGER_NAME)

    if logger.handlers:
        # Already configured (e.g. by an earlier call in the same
        # process) -- return as-is rather than attaching duplicate
        # handlers, which would double- or triple-print every line.
        return logger

    logger.setLevel(logging.INFO)

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger