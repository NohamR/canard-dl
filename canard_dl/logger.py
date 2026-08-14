"""Logging configuration for canard-dl."""

import logging
import sys

APP_LOGGER_NAME = "canard_dl"

DEFAULT_FORMAT = "%(levelname)8s %(message)s"
VERBOSE_FORMAT = "%(asctime)s %(levelname)8s %(name)s - %(message)s"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger in the canard_dl namespace."""

    return logging.getLogger(name or APP_LOGGER_NAME)


def setup_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """
    Configure the canard_dl logger for console output.

    Levels: quiet -> WARNING, default -> INFO, verbose -> DEBUG.
    """

    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.setLevel(level)

    # Avoid duplicate handlers when called more than once.
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            VERBOSE_FORMAT if verbose else DEFAULT_FORMAT,
            datefmt="%H:%M:%S",
        )
    )

    logger.addHandler(handler)
    logger.propagate = False