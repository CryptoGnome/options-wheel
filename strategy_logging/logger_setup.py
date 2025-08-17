import logging
import sys
from pathlib import Path

def setup_logger(log_file="logs/run.log", level="INFO", to_file=False):
    logger = logging.getLogger("strategy")
    logger.setLevel(getattr(logging, level.upper()))

    if not logger.handlers:
        # Console output
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(getattr(logging, level.upper()))
        ch.setFormatter(logging.Formatter("[%(message)s]"))
        logger.addHandler(ch)

        # File output
        if to_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            logger.addHandler(fh)

    return logger
