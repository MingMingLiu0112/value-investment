"""PDFium requires process-wide serialization, even for different documents."""
from functools import wraps
from threading import RLock


_PDFIUM_LOCK = RLock()


def serialized_pdfium(function):
    """Keep native handles, text access and their cleanup within one lock."""
    @wraps(function)
    def run(*args, **kwargs):
        with _PDFIUM_LOCK:
            return function(*args, **kwargs)
    return run
