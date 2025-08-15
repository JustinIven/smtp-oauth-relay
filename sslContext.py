import ssl
import logging


def from_keyvault(azure_key_vault_url, azure_key_vault_cert_name):
    """
    Load certificate from Azure Key Vault.
    Returns ssl.SSLContext object.
    """
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
    from cryptography.hazmat.primitives.serialization import pkcs12
    import base64
    from tempfile import NamedTemporaryFile

    # Create a secret client
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=azure_key_vault_url, credential=credential)
        
    cert_secret = client.get_secret(azure_key_vault_cert_name)
    cert_data = base64.b64decode(cert_secret.value)
    # Load the certificate and key from the PKCS#12 data
    try:
        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(cert_data, None)
    except Exception as e:
        logging.error(f"Failed to load PKCS#12 data: {str(e)}")
        raise

    # Create a temporary file to store the certificate and key
    with NamedTemporaryFile(delete=False) as cert_file, NamedTemporaryFile(delete=False) as key_file:
        # write certificate
        cert_file.write(certificate.public_bytes(Encoding.PEM))
        cert_file.flush()

        # write private key
        key_file.write(private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=NoEncryption()
        ))
        key_file.flush()
    

        # Create SSL context
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=cert_file.name, keyfile=key_file.name)

    return context


def from_file(cert_filepath, key_filepath):
    """
    Load certificate and key from file paths.
    Returns ssl.SSLContext object.
    """
    import os

    # check if cert and key files exist
    if not os.path.exists(path=cert_filepath) or not os.path.exists(path=key_filepath):
        logging.error("Certificate or key not found")
        raise FileNotFoundError("Certificate or key not found")


    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    try:
        context.load_cert_chain(certfile=cert_filepath, keyfile=key_filepath)
    except ssl.SSLError as e:
        logging.error(f"Failed to load Certificate or key: {str(e)}")
        raise
    except FileNotFoundError as e:
        logging.error(f"Certificate or key not found: {str(e)}")
        raise
    return context
