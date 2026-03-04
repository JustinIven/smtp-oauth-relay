import base64
import re
import uuid

import requests
from aiosmtpd.smtp import AuthResult
from azure.data.tables import TableClient
from azure.identity import DefaultAzureCredential

import relay_logging
from config import (
    AZURE_TABLES_PARTITION_KEY,
    AZURE_TABLES_URL,
    HTTP_TIMEOUT_SECONDS,
    USERNAME_DELIMITER,
)
from constants import (
    AUTH_CREDENTIALS_MISSING,
    AUTH_FAILED,
    AUTH_INVALID_ENCODING,
    AUTH_UNEXPECTED_ERROR,
    AUTH_UNSUPPORTED_MECHANISM,
)

UUID_PATTERN = re.compile(
    r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'
)


def decode_uuid_or_base64url(input_str: str) -> str:
    # Checks if input is a UUID string, otherwise decodes base64url into a UUID.
    # Returns the decoded string in UUID format.
    if UUID_PATTERN.match(input_str):
        return input_str

    # Attempt to decode as base64url.
    try:
        padded = input_str + "=" * (-len(input_str) % 4)
        return str(uuid.UUID(bytes=base64.urlsafe_b64decode(padded)))
    except Exception as exc:
        raise ValueError(f"Invalid base64url encoding in input '{input_str}'") from exc


def lookup_user(lookup_id: str) -> tuple[str, str, str | None]:
    # Search in Azure Table for user information based on the lookup_id (RowKey).
    # Returns (tenant_id, client_id, from_email) or raises ValueError if not found.
    if not AZURE_TABLES_URL:
        raise ValueError("AZURE_TABLES_URL environment variable not set")

    try:
        credential = DefaultAzureCredential()
        with TableClient.from_table_url(
            table_url=AZURE_TABLES_URL,
            credential=credential
        ) as client:  # pyright: ignore[reportArgumentType]
            entities = client.query_entities(
                query_filter=(
                    f"PartitionKey eq '{AZURE_TABLES_PARTITION_KEY}' "
                    f"and RowKey eq '{lookup_id}'"
                )
            )
            entity = None
            for i in entities:
                entity = i
                break
    except Exception as e:
        raise RuntimeError(f"Failed to query Azure Table: {str(e)}") from e

    if not entity:
        raise ValueError(f"No entity found for RowKey '{lookup_id}'")

    tenant_id = entity.get('tenant_id')
    client_id = entity.get('client_id')
    from_email = entity.get('from_email')

    if not tenant_id or not client_id:
        raise ValueError(f"Entity for RowKey '{lookup_id}' is missing tenant_id or client_id")

    return tenant_id, client_id, from_email


def parse_username(username: str) -> tuple[str, str, str | None]:
    # Parse the username to extract tenant_id and client_id.
    # Expected format: tenant_id{USERNAME_DELIMITER}client_id{. optional_tld}

    # remove the optional TLD if present
    if '.' in username:
        username = username.split('.')[0]

    # Check if username is valid
    if not username or USERNAME_DELIMITER not in username:
        raise ValueError(
            f"Invalid username format. Expected format: tenant_id{USERNAME_DELIMITER}client_id"
        )

    # Split the username by the delimiter
    parts = username.split(USERNAME_DELIMITER)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid username format. Expected exactly one '{USERNAME_DELIMITER}' character"
        )

    # check if the second part hints a user stored in the lookup table
    if parts[1] == 'lookup':
        return lookup_user(parts[0])

    # else return both parts decoded
    return decode_uuid_or_base64url(parts[0]), decode_uuid_or_base64url(parts[1]), None


def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        response = requests.post(
            url=f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data=data,
            headers=headers,
            timeout=HTTP_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        access_token = response.json().get("access_token")
        if not access_token:
            raise ValueError("OAuth token response missing access_token")
        return access_token
    except requests.RequestException as e:
        relay_logging.log_oauth_token_request_failed(e)
        if hasattr(e, 'response') and e.response:
            relay_logging.log_oauth_token_response_details(
                e.response.status_code,
                e.response.text
            )
        raise


class Authenticator:
    def __call__(self, server, session, envelope, mechanism, auth_data):
        try:
            # Only support LOGIN and PLAIN mechanisms
            if mechanism not in ('LOGIN', 'PLAIN'):
                relay_logging.log_unsupported_auth_mechanism(mechanism)
                return AuthResult(
                    success=False,
                    handled=False,
                    message=AUTH_UNSUPPORTED_MECHANISM
                )

            # Check if authentication data is present
            if not auth_data or not auth_data.login or not auth_data.password:
                relay_logging.log_missing_auth_data()
                return AuthResult(
                    success=False,
                    handled=False,
                    message=AUTH_CREDENTIALS_MISSING
                )

            try:
                login_str = auth_data.login.decode("utf-8")
            except Exception as e:
                relay_logging.log_auth_login_decode_failed(e)
                return AuthResult(
                    success=False,
                    handled=False,
                    message=AUTH_INVALID_ENCODING
                )

            # Parse tenant_id and client_id from login string using the configured format
            try:
                tenant_id, client_id, from_email = parse_username(login_str)
            except ValueError as e:
                relay_logging.log_auth_parse_failed(str(e))
                return AuthResult(
                    success=False,
                    handled=False,
                    message=f"535 5.7.8 {str(e)}"
                )

            client_secret = auth_data.password
            session.lookup_from_email = from_email

            try:
                session.access_token = get_access_token(tenant_id, client_id, client_secret)
                return AuthResult(success=True)
            except Exception as e:
                relay_logging.log_authentication_failed(e)
                return AuthResult(
                    success=False,
                    handled=False,
                    message=AUTH_FAILED
                )

        except Exception as e:
            relay_logging.log_auth_unexpected_error(e)
            return AuthResult(
                success=False,
                handled=False,
                message=AUTH_UNEXPECTED_ERROR
            )
