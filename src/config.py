import os


# Load configuration from environment variables
def load_env(name, default=None, sanitize=lambda x: x, valid_values=None, convert=lambda x: x):
    value = sanitize(os.getenv(name, default))
    if valid_values and value not in valid_values:
        raise ValueError(f"Invalid {name}: {value}")
    return convert(value)


# Configuration
LOG_LEVEL = load_env(
    name='LOG_LEVEL',
    default='WARNING',
    valid_values=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
    sanitize=lambda x: x.upper()
)
TLS_SOURCE = load_env(
    name='TLS_SOURCE',
    default='file',
    valid_values=['off', 'file', 'keyvault'],
    sanitize=lambda x: x.lower(),
)
REQUIRE_TLS = load_env(
    name='REQUIRE_TLS',
    default='true',
    valid_values=['true', 'false'],
    sanitize=lambda x: x.lower(),
    convert=lambda x: x == 'true'
)
SERVER_GREETING = load_env(
    name='SERVER_GREETING',
    default='Microsoft Graph SMTP OAuth Relay'
)
HTTP_TIMEOUT_SECONDS = load_env(
    name='HTTP_TIMEOUT_SECONDS',
    default='30',
    convert=lambda x: float(x)
)
TLS_CERT_FILEPATH = load_env(
    name='TLS_CERT_FILEPATH',
    default='certs/cert.pem'
)
TLS_KEY_FILEPATH = load_env(
    name='TLS_KEY_FILEPATH',
    default='certs/key.pem'
)
TLS_CIPHER_SUITE = load_env(
    name='TLS_CIPHER_SUITE',
    default=None  # Make it optional
)
USERNAME_DELIMITER = load_env(
    name='USERNAME_DELIMITER',
    default='@',
    valid_values=['@', ':', '|']
)
AZURE_KEY_VAULT_URL = load_env(
    name='AZURE_KEY_VAULT_URL',
    default=None,  # Make it optional
)
AZURE_KEY_VAULT_CERT_NAME = load_env(
    name='AZURE_KEY_VAULT_CERT_NAME',
    default=None,  # Make it optional
)
AZURE_TABLES_URL = load_env(
    name='AZURE_TABLES_URL',
    default=None,  # Make it optional
)
AZURE_TABLES_PARTITION_KEY = load_env(
    name='AZURE_TABLES_PARTITION_KEY',
    default='user'
)
GRAPH_MAILBOX_CONCURRENCY = load_env(
    name='GRAPH_MAILBOX_CONCURRENCY',
    default='4',
    convert=lambda x: int(x)
)
GRAPH_RATE_LIMIT_PER_10_SECONDS = load_env(
    name='GRAPH_RATE_LIMIT_PER_10_SECONDS',
    default='25',
    convert=lambda x: float(x)
)
GRAPH_LIMITER_TTL_SECONDS = load_env(
    name='GRAPH_LIMITER_TTL_SECONDS',
    default='3600',
    convert=lambda x: float(x)
)
GRAPH_FAILBACK_ON_404 = load_env(
    name='GRAPH_FAILBACK_ON_404',
    default='false',
    valid_values=['true', 'false'],
    sanitize=lambda x: x.lower(),
    convert=lambda x: x == 'true'
)
FROM_REMAP_DOMAINS = load_env(
    name='FROM_REMAP_DOMAINS',
    default='',
    sanitize=lambda x: x.strip() if x else x,
    convert=lambda value: {
        item.strip().lower() for item in value.split(",") if item.strip()
    } if value else set()
)
FROM_REMAP_ADDRESSES = load_env(
    name='FROM_REMAP_ADDRESSES',
    default='',
    sanitize=lambda x: x.strip() if x else x,
    convert=lambda value: {
        item.strip().lower() for item in value.split(",") if item.strip()
    } if value else set()
)
TO_REMAP_DOMAINS = load_env(
    name='TO_REMAP_DOMAINS',
    default='',
    sanitize=lambda x: x.strip() if x else x,
    convert=lambda value: {
        item.strip().lower() for item in value.split(",") if item.strip()
    } if value else set()
)
TO_REMAP_ADDRESSES = load_env(
    name='TO_REMAP_ADDRESSES',
    default='',
    sanitize=lambda x: x.strip() if x else x,
    convert=lambda value: {
        item.strip().lower() for item in value.split(",") if item.strip()
    } if value else set()
)
DOMAIN_SETTINGS_TABLES_PARTITION_KEY = load_env(
    name='DOMAIN_SETTINGS_TABLES_PARTITION_KEY',
    default='domain'
)
