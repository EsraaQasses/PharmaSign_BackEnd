import logging
import sys
from pathlib import Path

def get_logger(name: str) -> logging.Logger:
    """Sets up a logger with consistent formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Configure console handler
        c_handler = logging.StreamHandler(sys.stdout)
        c_handler.setLevel(logging.INFO)
        
        # Reconfigure stdout/stderr for Unicode support on Windows
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
            
        c_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(c_format)
        logger.addHandler(c_handler)
        
    return logger

def clean_windows_path(path_str: str) -> str:
    """Normalizes path separators to standard forward slashes for cross-platform compatibility."""
    return str(Path(path_str)).replace("\\", "/")
