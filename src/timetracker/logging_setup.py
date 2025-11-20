import logging
from logging.handlers import RotatingFileHandler
from .config import LOG_PATH

def get_logger(name="tt"):
    """Returnează un logger configurat pentru aplicație."""
    logger = logging.getLogger(name)
    if getattr(logger, "_configured", False):
        return logger

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)

    fh = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger._configured = True
    return logger
