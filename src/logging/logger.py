import io
import logging
import logging.handlers
import os
import sys
from pathlib import Path


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    root.setLevel(log_level)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # On Windows the default console encoding (e.g. cp1252) cannot encode characters
    # like the Unicode arrow →.  Wrap stderr's underlying buffer so that any
    # unencodable character is safely escaped instead of raising UnicodeEncodeError.
    if hasattr(sys.stderr, "buffer"):
        safe_stream = io.TextIOWrapper(
            sys.stderr.buffer,
            encoding=sys.stderr.encoding or "utf-8",
            errors="backslashreplace",
            line_buffering=getattr(sys.stderr, "line_buffering", True),
        )
        console_handler = logging.StreamHandler(safe_stream)
    else:
        console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
