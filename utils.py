import time
import functools
from selenium.common.exceptions import StaleElementReferenceException

def retry_on_stale(*, tries: int = 3, delay_s: float = 0.0, on_retry=None):
    """
    Retry a function if Selenium raises StaleElementReferenceException.

    on_retry: optional callback (exc, attempt_number) -> None
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, tries + 1):
                try:
                    return fn(*args, **kwargs)
                except StaleElementReferenceException as e:
                    last_exc = e
                    if on_retry:
                        on_retry(e, attempt)
                    if attempt == tries:
                        raise
                    if delay_s:
                        time.sleep(delay_s)
            raise last_exc  # should be unreachable
        return wrapper
    return decorator