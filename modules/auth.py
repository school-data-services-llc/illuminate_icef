import requests
import logging
import threading
import time
from .access_secrets import *

J_CLIENT_ID = access_secret_version('icef-437920', 'illuminate_client_id', version_id="latest")
J_CLIENT_SECRET = access_secret_version('icef-437920', 'illuminate_access_key', version_id="latest")
token_url_illuminate = 'https://icefps.illuminateed.com/live/'
base_url_illuminate = 'https://icefps.illuminateed.com/live/rest_server.php/Api/'

# Configuration
TOKEN_URL = f'{token_url_illuminate}?OAuth2_AccessToken'
TOKEN_EXPIRY = 3600  # Token expiry time in seconds (1 hour)
TOKEN_REFRESH_BUFFER_SECONDS = 300  # refresh 5 minutes before expiry


def get_access_token():
    # Prepare the payload for the token request
    payload = {
        'client_id': J_CLIENT_ID,
        'client_secret': J_CLIENT_SECRET,
        'grant_type': 'client_credentials',  # Assuming client credentials grant type
    }

    # Request the access token
    try:
        response = requests.post(TOKEN_URL, data=payload)
        logging.info('Calling API token endpoint')
    except Exception as e:
        logging.error(f'Unable to get API token succesfully due to {e}')
        raise Exception(f"Error occurred while getting API token: {e}")
    
    if response.status_code == 200:
        logging.info('Succesfully retrieved API token')
        token_info = response.json()
        access_token = token_info.get('access_token')
        expires_in = token_info.get('expires_in', TOKEN_EXPIRY)  # Default to 1 hour if not provided
        
        return access_token, expires_in
    else:
        logging.error(f'Failed to obtain access token: {response.status_code} {response.text}')
        print('Failed to obtain access token:', response.status_code, response.text)
        return None, None


class IlluminateTokenSession:
    """Thread-safe Illuminate OAuth token that refreshes before expiry and on demand."""

    def __init__(self):
        self._lock = threading.Lock()
        self._token = None
        self._expires_at = 0.0
        self.force_refresh()

    def get_token(self):
        with self._lock:
            if (
                not self._token
                or time.time() >= self._expires_at - TOKEN_REFRESH_BUFFER_SECONDS
            ):
                self._refresh_unlocked()
            return self._token

    def force_refresh(self):
        with self._lock:
            self._refresh_unlocked()
            return self._token

    def _refresh_unlocked(self):
        token, expires_in = get_access_token()
        if not token:
            raise RuntimeError("Failed to obtain Illuminate access token")
        self._token = token
        self._expires_at = time.time() + float(expires_in or TOKEN_EXPIRY)
        logging.info(
            f"Illuminate token ready; expires_in={expires_in}s "
            f"(refresh buffer={TOKEN_REFRESH_BUFFER_SECONDS}s)"
        )
