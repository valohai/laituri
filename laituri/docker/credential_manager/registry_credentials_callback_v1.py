from __future__ import annotations

import logging
import random
import time
from contextlib import contextmanager
from typing import Any, Iterator

import requests
from requests.utils import default_headers

import laituri
from laituri.docker.credential_manager.docker_v1 import docker_v1_credential_manager
from laituri.docker.credential_manager.errors import CallbackFailed
from laituri.types import LogStatusCallable, RegistryCredentialsDict

log = logging.getLogger(__name__)


@contextmanager
def registry_credentials_callback_v1_credential_manager(
    *,
    image: str,
    registry_credentials: RegistryCredentialsDict,
    log_status: LogStatusCallable,
    auth_tries: int,
) -> Iterator[None]:
    docker_credentials = _get_docker_credentials_with_retry(
        registry_credentials,
        auth_tries=auth_tries,
    )

    with docker_v1_credential_manager(
        image=image,
        registry_credentials=docker_credentials,
        log_status=log_status,
        auth_tries=auth_tries,
    ):
        yield


def _get_docker_credentials_with_retry(
    registry_credentials: dict[str, Any],
    *,
    auth_tries: int,
) -> RegistryCredentialsDict:
    for attempt in range(auth_tries):
        try:
            return fetch_docker_credentials(registry_credentials)
        except Exception as exc:
            should_retry = attempt < auth_tries - 1
            if isinstance(exc, requests.HTTPError) and exc.response.status_code < 500:
                # Don't retry on client errors, as they are unlikely to succeed on retry
                should_retry = False
            if not should_retry:
                raise CallbackFailed(f"Credential callback failed: {exc}") from exc
            log.warning("Failed to retrieve credentials, attempt %d", attempt, exc_info=True)
            time.sleep(min((2**attempt) + random.random(), 16))
    raise RuntimeError("Did not attempt to retrieve credentials")  # pragma: no cover


def fetch_docker_credentials(request_info: dict[str, Any]) -> RegistryCredentialsDict:
    headers = default_headers()
    headers['User-Agent'] = f'{headers.get("User-Agent")} laituri/{laituri.__version__}'
    ri_headers = request_info.get('headers')
    if isinstance(ri_headers, dict):
        headers.update({key: str(value) for (key, value) in ri_headers.items() if key and value})

    response = requests.request(
        method=request_info.get('method', 'POST'),
        url=request_info['url'],
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Invalid response data: {data}")
    return {str(k): v for (k, v) in data.items()}
