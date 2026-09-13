import logging
import sys
import os

def init_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear ALL handlers from basicConfig to avoid duplication
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Add a file handler for persistent logging (ALL levels)
    log_dir = os.path.join(os.path.expanduser("~"), ".kerros")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, "kerr_os_debug.log"))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    # Add console handler - ONLY show ERROR and above as plain text
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(logging.ERROR)
    stream_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(stream_handler)


def get_logger(name: str):
    return logging.getLogger(name)
