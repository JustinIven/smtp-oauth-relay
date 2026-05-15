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
    default=None # Make it optional
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
AZURE_TABLES_FORCE_USAGE = load_env(
    name='AZURE_TABLES_FORCE_USAGE',
    default='false',
    valid_values=['true', 'false'],
    sanitize=lambda x: x.lower(),
    convert=lambda x: x == 'true'
)
