from typing import Any, Dict

import pytest
import requests

from laituri.docker.credential_manager import get_credential_manager
from laituri.docker.credential_manager.errors import CallbackFailed
from laituri_tests.mock_data import EXAMPLE_IMAGES
from laituri_tests.mock_process import create_mock_popen
from laituri_tests.test_docker_v1 import VALID_DOCKER_CREDENTIALS

VALID_CALLBACK_CREDENTIALS: Dict[str, Any] = {
    'version': 1,
    'type': 'registry-credentials-callback',
    'url': 'https://example.com/?name=erkki',
}
VALID_CALLBACK_RESPONSE = VALID_DOCKER_CREDENTIALS


@pytest.mark.parametrize('image', EXAMPLE_IMAGES)
@pytest.mark.parametrize('with_header', (False, True))
def test_callback_retry(mocker, requests_mock, with_header: bool, image: str):
    registry_credentials = VALID_CALLBACK_CREDENTIALS.copy()
    if with_header:
        registry_credentials['headers'] = {
            'x-hello': 'there',
            '': 0,
        }
    rh = requests_mock.post(
        VALID_CALLBACK_CREDENTIALS['url'],
        [
            {'status_code': 500},
            {'exc': requests.exceptions.ConnectTimeout},
            {'status_code': 200},  # no JSON
            {'status_code': 200, 'json': VALID_CALLBACK_RESPONSE},
        ],
    )
    mock_popen = mocker.patch('subprocess.Popen', new_callable=create_mock_popen)
    mocker.patch('time.sleep')  # removes retry delays for testing
    my_action = mocker.Mock()
    with get_credential_manager(image=image, registry_credentials=registry_credentials):
        my_action()
    assert mock_popen.call_count == 2  # login + logout
    my_action.assert_called_once_with()
    headers = rh.request_history[-1].headers
    assert 'laituri/' in headers['user-agent']
    assert ('x-hello' in headers) == with_header


@pytest.mark.parametrize('status_code', (400, 404))
def test_callback_no_retry_on_client_error(requests_mock, status_code):
    rh = requests_mock.post(VALID_CALLBACK_CREDENTIALS['url'], status_code=status_code)
    with pytest.raises(CallbackFailed) as ei:
        with get_credential_manager(image="foo/bar", registry_credentials=VALID_CALLBACK_CREDENTIALS):
            pass
    assert f"{status_code} Client Error" in str(ei.value)
    assert len(rh.request_history) == 1  # One call, no retries


def test_callback_error(mocker, requests_mock):
    registry_credentials = VALID_CALLBACK_CREDENTIALS.copy()
    rebbitron_error = {'error': 'failed to figbungle the rebbitron'}
    requests_mock.post(
        registry_credentials['url'],
        status_code=401,
        json=rebbitron_error,
    )
    mocker.patch('time.sleep')  # removes retry delays for testing
    with pytest.raises(CallbackFailed) as ei:
        with get_credential_manager(image='owner/projungle', registry_credentials=registry_credentials):
            pass

    exc = ei.value
    # See that we can access the inner exception to get the error
    assert isinstance(exc, CallbackFailed) and exc.get_callback_response().json() == rebbitron_error


@pytest.mark.parametrize('auth_tries', (1, 32))
def test_custom_auth_tries(mocker, requests_mock, auth_tries):
    registry_credentials = VALID_CALLBACK_CREDENTIALS.copy()
    responses = requests_mock.post(registry_credentials['url'], status_code=500)
    mocker.patch('time.sleep')  # removes retry delays for testing
    my_action = mocker.Mock()

    with pytest.raises(CallbackFailed, match='500 Server Error'):
        with get_credential_manager(
            image='owner/boggers',
            registry_credentials=registry_credentials,
            auth_tries=auth_tries,
        ):
            my_action()

    assert my_action.call_count == 0
    assert responses.call_count == auth_tries
