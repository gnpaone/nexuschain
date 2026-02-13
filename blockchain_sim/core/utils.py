import hashlib
import json
import logging
import time
from functools import wraps
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    encode_dss_signature,
    decode_dss_signature,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def sha256_hash(data):
    """
    Compute SHA-256 hash of input data.
    """
    if not isinstance(data, str):
        data = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def timestamp():
    """
    Get the current time in seconds since epoch.
    """
    return time.time()


def log_function_call(func):
    """
    Decorator to log function calls.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        logging.info(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        result = func(*args, **kwargs)
        logging.info(f"{func.__name__} returned {result}")
        return result

    return wrapper


def serialize(obj):
    """
    Serialize an object to a JSON string.
    """
    return json.dumps(obj, sort_keys=True, default=str)


def deserialize(json_str):
    """
    Deserialize JSON string to Python object.
    """
    return json.loads(json_str)


def sleep(seconds):
    """
    Sleep for the given number of seconds.
    """
    time.sleep(seconds)


def generate_private_key():
    """
    Generate a new ECDSA private key (SECP256R1).
    """
    return ec.generate_private_key(ec.SECP256R1())


def serialize_public_key(public_key):
    """
    Serialize a public key to PEM format string.
    """
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem.decode("utf-8")


def serialize_private_key(private_key):
    """
    Serialize a private key to PEM format string (unencrypted).
    """
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


def load_public_key(pem_str):
    """
    Load a public key from PEM string.
    """
    return serialization.load_pem_public_key(pem_str.encode("utf-8"))


def load_private_key(pem_str):
    """
    Load a private key from PEM string.
    """
    return serialization.load_pem_private_key(pem_str.encode("utf-8"), password=None)


def sign_message(private_key, message):
    """
    Sign a message (string or bytes) using ECDSA private key.
    Returns the signature as a hex string (DER encoded).
    """
    if isinstance(message, str):
        message = message.encode("utf-8")
    signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    return signature.hex()


def verify_signature(public_key, message, signature_hex):
    """
    Verify an ECDSA signature given public key, message, and signature hex string.
    Returns True if valid, False otherwise.
    """
    if isinstance(message, str):
        message = message.encode("utf-8")
    try:
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def safe_json_serialize(obj):
    try:
        return json.dumps(obj, sort_keys=True, default=str)
    except Exception as e:
        logging.error(f"Serialization error: {e}")
        return None


def safe_json_deserialize(json_str):
    try:
        return json.loads(json_str)
    except Exception as e:
        logging.error(f"Deserialization error: {e}")
        return None


def retry_operation(operation_func, retries=3, delay=1):
    for attempt in range(retries):
        try:
            return operation_func()
        except Exception as e:
            logging.warning(f"Operation failed (attempt {attempt+1}/{retries}): {e}")
            time.sleep(delay)
    raise Exception("Operation failed after retries")
