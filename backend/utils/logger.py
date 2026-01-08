import logging
import sys
import os
import structlog

def configure_logger():
    """
    Configures structured JSON logging for the application.
    Uses structlog to output logs in JSON format for Cloud Logging compatibility.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Check if we are in a Cloud Run environment (or production-like)
    # If standard logging is used, we want to capture it too
    
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure standard Python logging to hook into structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

def get_logger(name: str):
    """
    Returns a structured logger with the given name bound.
    """
    return structlog.get_logger(logger_name=name)
