import logging
import os
import ssl


def from_keyvault(azure_key_vault_url, azure_key_vault_cert_name):
    # Load certificate from Azure Key Vault and return an SSLContext.
    import base64
    from tempfile import NamedTemporaryFile

    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        pkcs12,
    )

    # Create a secret client
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=azure_key_vault_url, credential=credential)

    cert_secret = client.get_secret(azure_key_vault_cert_name)
    if not cert_secret or not cert_secret.value:
        logging.error("Certificate not found in Key Vault")
        raise ValueError("Certificate not found in Key Vault")

    cert_data = base64.b64decode(cert_secret.value)
    # Load the certificate and key from the PKCS#12 data
    try:
        private_key, certificate, _ = pkcs12.load_key_and_certificates(cert_data, None)
    except Exception as e:
        logging.error("Failed to load PKCS#12 data: %s", e)
        raise

    cert_path = None
    key_path = None
    try:
        # Create a temporary file to store the certificate and key
        with (
            NamedTemporaryFile(delete=False) as cert_file,
            NamedTemporaryFile(delete=False) as key_file,
        ):
            cert_path = cert_file.name
            key_path = key_file.name

            # Write certificate.
            if certificate is None:
                logging.error("No certificate found in PKCS#12 data")
                raise ValueError("No certificate found in PKCS#12 data")
            cert_file.write(certificate.public_bytes(Encoding.PEM))
            cert_file.flush()

            # Write private key.
            if private_key is None:
                logging.error("No private key found in PKCS#12 data")
                raise ValueError("No private key found in PKCS#12 data")
            key_file.write(private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption()
            ))
            key_file.flush()

        # Create SSL context.
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        return context
    finally:
        for path in (cert_path, key_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    logging.warning("Failed to remove temporary certificate file: %s", path)


def log_loaded_certificate_from_file(cert_path: str) -> None:
    logging.info("Loaded certificate from file: %s", cert_path)


def log_loaded_certificate_from_keyvault(cert_name: str) -> None:
    logging.info("Loaded certificate from Azure Key Vault: %s", cert_name)


def log_invalid_tls_source(tls_source: str) -> None:
    logging.error("Invalid TLS_SOURCE: %s", tls_source)


def log_missing_keyvault_config() -> None:
    logging.error(
        "Azure Key Vault URL and Certificate Name must be set when TLS_SOURCE is 'keyvault'"
    )


def log_tls_cipher_suites(cipher_names: str) -> None:
    logging.info("TLS cipher suites used: %s", cipher_names)


def from_file(cert_filepath, key_filepath):
    # Load certificate and key from file paths and return an SSLContext.
    from pathlib import Path

    try:
        cert_path = Path(cert_filepath).expanduser().resolve(strict=True)
        key_path = Path(key_filepath).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        logging.error("Certificate or key not found: %s", exc)
        raise

    if not cert_path.is_file() or not key_path.is_file():
        logging.error("Certificate or key path is not a file")
        raise FileNotFoundError("Certificate or key path is not a file")

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    try:
        context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    except ssl.SSLError as e:
        logging.error("Failed to load Certificate or key: %s", e)
        raise
    return context
