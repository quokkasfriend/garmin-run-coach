"""Client Garmin: solo auth + retry. Gli endpoint sono quelli del client ufficiale."""

import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from garmin_personal_api import (
    GarminPersonalApiClient,
    HttpError,
    PersonalApiAuthenticator,
)

from coach.settings import TOKEN_CACHE, ensure_dirs, garmin_api_key

PAUSE_S = 0.4  # rate limit non documentato: pausa fra chiamate
RETRIES = 3


@contextmanager
def garmin_client(force_refresh: bool = False):
    ensure_dirs()
    with PersonalApiAuthenticator(bearer_token_cache_file=TOKEN_CACHE) as auth:
        token = auth.obtain_token(garmin_api_key(), force_refresh=force_refresh)
    with GarminPersonalApiClient(token.access_token) as client:
        yield client


def call(fn: Callable[..., Any], *args, **kwargs) -> Any:
    """Chiama un endpoint con pausa e retry sui 5xx/429. I 4xx (es. 401) non si ritentano."""
    for attempt in range(1, RETRIES + 1):
        try:
            result = fn(*args, **kwargs)
            time.sleep(PAUSE_S)
            return result
        except HttpError as e:
            retryable = e.status_code >= 500 or e.status_code == 429
            if not retryable or attempt == RETRIES:
                raise
            time.sleep(2**attempt)
