import base64
import hashlib
import logging
import os
import ssl
from tempfile import TemporaryDirectory

logger = logging.getLogger(__name__)


def _create_context(cert_filepath, key_filepath, cipher_suite=None):
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=cert_filepath, keyfile=key_filepath)
    if cipher_suite:
        context.set_ciphers(cipher_suite)
    return context


class FileCertificateSource:
    """TLS certificate and key loaded from PEM files."""

    def __init__(self, cert_filepath, key_filepath, cipher_suite=None):
        self.cert_filepath = cert_filepath
        self.key_filepath = key_filepath
        self.cipher_suite = cipher_suite

    def __str__(self):
        return f"file {self.cert_filepath}"

    def fingerprint(self):
        """
        Hash of the certificate and key contents.
        Content is hashed instead of using mtimes because Kubernetes updates
        mounted secrets by atomically swapping a symlinked directory.
        """
        digest = hashlib.sha256()
        for path in (self.cert_filepath, self.key_filepath):
            try:
                with open(path, "rb") as f:
                    digest.update(f.read())
            except FileNotFoundError as e:
                logger.error(f"Certificate or key not found: {e!s}")
                raise
        return digest.hexdigest()

    def load(self):
        """Returns ssl.SSLContext object."""
        if not os.path.exists(self.cert_filepath) or not os.path.exists(
            self.key_filepath
        ):
            logger.error("Certificate or key not found")
            raise FileNotFoundError("Certificate or key not found")

        try:
            return _create_context(
                self.cert_filepath, self.key_filepath, self.cipher_suite
            )
        except ssl.SSLError as e:
            logger.error(f"Failed to load Certificate or key: {e!s}")
            raise
        except FileNotFoundError as e:
            logger.error(f"Certificate or key not found: {e!s}")
            raise


class KeyVaultCertificateSource:
    """TLS certificate (PKCS#12) loaded from Azure Key Vault."""

    def __init__(
        self, azure_key_vault_url, azure_key_vault_cert_name, cipher_suite=None
    ):
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        self.cert_name = azure_key_vault_cert_name
        self.cipher_suite = cipher_suite
        self.client = SecretClient(
            vault_url=azure_key_vault_url, credential=DefaultAzureCredential()
        )

    def __str__(self):
        return f"Azure Key Vault certificate {self.cert_name}"

    def _get_secret(self):
        secret = self.client.get_secret(self.cert_name)
        if not secret or not secret.value:
            logger.error("Certificate not found in Key Vault")
            raise ValueError("Certificate not found in Key Vault")
        return secret

    def fingerprint(self):
        secret = self._get_secret()
        return (
            secret.properties.version
            or hashlib.sha256(secret.value.encode()).hexdigest()
        )

    def load(self):
        """Returns ssl.SSLContext object."""
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            pkcs12,
        )

        cert_data = base64.b64decode(self._get_secret().value)
        # Load the certificate and key from the PKCS#12 data
        try:
            private_key, certificate, _ = pkcs12.load_key_and_certificates(
                cert_data, None
            )
        except Exception as e:
            logger.error(f"Failed to load PKCS#12 data: {e!s}")
            raise

        if certificate is None:
            logger.error("No certificate found in PKCS#12 data")
            raise ValueError("No certificate found in PKCS#12 data")
        if private_key is None:
            logger.error("No private key found in PKCS#12 data")
            raise ValueError("No private key found in PKCS#12 data")

        # load_cert_chain only accepts file paths; the temporary files are removed afterwards
        with TemporaryDirectory() as tmpdir:
            cert_filepath = os.path.join(tmpdir, "cert.pem")
            key_filepath = os.path.join(tmpdir, "key.pem")
            with open(cert_filepath, "wb") as cert_file:
                cert_file.write(certificate.public_bytes(Encoding.PEM))
            with open(
                os.open(key_filepath, os.O_WRONLY | os.O_CREAT, 0o600), "wb"
            ) as key_file:
                key_file.write(
                    private_key.private_bytes(
                        encoding=Encoding.PEM,
                        format=PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=NoEncryption(),
                    )
                )
            return _create_context(cert_filepath, key_filepath, self.cipher_suite)
