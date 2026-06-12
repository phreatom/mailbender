import time


def retry(fn, *, attempts: int = 3, base_delay: float = 1.0,
          sleep=time.sleep, exceptions: tuple = (Exception,)):
    """Call fn(); on a listed exception, retry with exponential backoff.

    Sleeps base_delay * 2**(n-1) between attempts (never after the last).
    `sleep` is injectable so tests run without real delays. Re-raises the
    last exception once attempts are exhausted.
    """
    for n in range(1, attempts + 1):
        try:
            return fn()
        except exceptions:
            if n == attempts:
                raise
            sleep(base_delay * (2 ** (n - 1)))
