import time
import datetime
import jwt
import uuid
import base64
from hashlib import sha256
from .dbu import async_eval
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec as asymec

STREAM_BLOCKSIZE = 1000000
DEFAULT_JWT_VALID_FOR_SEC = 24*60*60
DEFAULT_JWT_ROLE = "user"
DEFAULT_JWT_USER_ID = "jwt-user"
_default_jwt_opts = {"valid_for_sec": DEFAULT_JWT_VALID_FOR_SEC, "role": DEFAULT_JWT_ROLE, "user_id": DEFAULT_JWT_USER_ID}

DASHBORG_CERT = """
-----BEGIN CERTIFICATE-----
MIIBxDCCAUmgAwIBAgIFAv2DbD4wCgYIKoZIzj0EAwMwLzEtMCsGA1UEAxMkNWZk
YWYxZDEtYjUyNC00MzYxLWFkY2ItMzI1ZDBlOGFiN2VlMB4XDTIwMDEwMTAwMDAw
MFoXDTMwMDEwMTAwMDAwMFowLzEtMCsGA1UEAxMkNWZkYWYxZDEtYjUyNC00MzYx
LWFkY2ItMzI1ZDBlOGFiN2VlMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEhsrFNs6I
reL5fWAdQxzNrYRgJdf2zE2aeBj/o28mXR1iQRtAlBY9Jh9zQtZCnypK2MprKvqw
07f0YoquV17gOhumj7LIRhlZ9GANwra6VorRVtVVgKCpTmG8o/ulJ3o4ozUwMzAO
BgNVHQ8BAf8EBAMCB4AwEwYDVR0lBAwwCgYIKwYBBQUHAwIwDAYDVR0TAQH/BAIw
ADAKBggqhkjOPQQDAwNpADBmAjEAtW26nW+AHoa9VQiqmGJ8z/+265YUK6QkkQ+T
276zLFAdfAO+bOVK0MMjzr21v6aLAjEA6LknqHnEh+QDWWIm8vM1Jp/FtiJ0KT//
4qUptLIY0pSijwpt/TAZd4QG8M5IQ+T7
-----END CERTIFICATE-----
"""

def make_account_jwt(key_file_name, acc_id, jwt_opts=None):
    if jwt_opts is None:
        jwt_opts = {}
    pk_bytes = open(key_file_name, "rb").read()
    private_key = serialization.load_pem_private_key(pk_bytes, None, default_backend())
    claims = {}
    valid_for_sec = jwt_opts.get("valid_for_sec") or DEFAULT_JWT_VALID_FOR_SEC
    jwt_role = jwt_opts.get("role") or DEFAULT_JWT_ROLE
    jwt_user_id = jwt_opts.get("user_id") or DEFAULT_JWT_USER_ID
    claims["iss"] = "dashborg"
    claims["exp"] = int(time.time()) + valid_for_sec
    claims["iat"] = int(time.time()) - 5
    claims["jti"] = str(uuid.uuid4())
    claims["dash-acc"] = acc_id
    claims["aud"] = "dashborg-auth"
    claims["sub"] = jwt_user_id
    claims["role"] = jwt_role
    jwtstr = jwt.encode(claims, private_key, algorithm="ES384")
    return jwtstr


def create_key_pair(keyfile, certfile, acc_id):
    private_key = asymec.generate_private_key(asymec.SECP384R1, default_backend())
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(encoding=serialization.Encoding.PEM,
                                              format=serialization.PrivateFormat.PKCS8,
                                              encryption_algorithm=serialization.NoEncryption())
    with open(keyfile, "wb") as f:
        f.write(bytes("-----BEGIN EC PARAMETERS-----\n"
                      "BgUrgQQAIg==\n"
                      "-----END EC PARAMETERS-----\n", "utf-8"))
        f.write(private_bytes)
    cert_name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, acc_id)])
    builder = x509.CertificateBuilder()
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.subject_name(cert_name)
    builder = builder.issuer_name(cert_name)
    builder = builder.not_valid_before(datetime.datetime(2020, 1, 1))
    builder = builder.not_valid_after(datetime.datetime(2030, 1, 1))
    builder = builder.public_key(public_key)
    builder = builder.sign(private_key=private_key,
                           algorithm=hashes.SHA256(),
                           backend=default_backend())
    cert_bytes = builder.public_bytes(encoding=serialization.Encoding.PEM)
    with open(certfile, "wb") as f:
        f.write(cert_bytes)

def read_cert_info(cert_file):
    cert_data = open(cert_file, "rb").read()
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    subject = cert.subject
    cns = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    acc_id = cns[0].value
    pk = cert.public_key()
    pkbytes = pk.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pkdigest = sha256(pkbytes)
    pk256_base64 = base64.standard_b64encode(pkdigest.digest()).decode("ascii")
    return {"acc_id": acc_id, "pk256": pk256_base64, "pubkey": pk}

async def compute_sha256_stream(stream):
    sha = sha256()
    size = 0
    while True:
        result = stream.read(STREAM_BLOCKSIZE)
        buf = await async_eval(result)
        if len(buf) == 0:
            break
        if isinstance(buf, str):
            encoded_buf = buf.encode('utf-8')
            size += len(encoded_buf)
            sha.update(encoded_buf)
        elif isinstance(buf, bytes):
            sha.update(buf)
            size += len(buf)
        else:
            raise ValueError("Stream must produce either str or bytes when calling read()")
    return base64.b64encode(sha.digest()).decode('utf-8'), size

