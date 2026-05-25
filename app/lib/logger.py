"""
app/lib/logger.py — Structured Logging
========================================
Setup structlog for clean JSON console output.
"""

import logging
import sys
import structlog


def setup_logging(log_level: str = "INFO"):
    """Configure structlog and standard logging."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
    
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer()  # Use JSONRenderer() in prod if shipping to ELK/Datadog
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
