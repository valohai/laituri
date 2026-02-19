import random
import time
import warnings
from functools import wraps
from typing import Any, Callable, TypeVar, cast

T = TypeVar('T', bound=Callable[..., Any])


def retry(*, tries: int = 5, max_delay: float = 32) -> Callable[[T], T]:  # pragma: no cover
    """
    Decorator that retries the wrapped function if any exception occurs.
    """

    def inner_retry(func: T) -> T:
        return make_retrying(func, tries=tries, max_delay=max_delay)

    return inner_retry


def make_retrying(func: T, tries: int = 5, max_delay: float = 32) -> T:  # pragma: no cover
    warnings.warn("make_retrying is deprecated", DeprecationWarning, stacklevel=2)
    if tries < 1:
        raise ValueError(f'tries must be >= 1, got {tries}')

    @wraps(func)
    def wrapped_func(*args, **kwargs):  # type: ignore
        attempt = 1
        while attempt < tries:
            try:
                return func(*args, **kwargs)
            except Exception:
                delay = 2 ** (attempt - 1)  # 1, 2, 4, 8, 16, 32...
                delay += random.random()  # a tiny bit of random for desynchronizing multiple potential users
                delay = min(delay, max_delay)
                time.sleep(delay)
                attempt += 1
        # and finally, just try one more time but let any exceptions bubble up
        return func(*args, **kwargs)

    return cast(T, wrapped_func)
