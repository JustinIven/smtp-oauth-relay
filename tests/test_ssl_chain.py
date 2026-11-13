import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from sslContext import _build_chain


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject_cn, subject_key, issuer_cn, issuer_key):
    now = datetime.datetime.now(datetime.UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(_name(subject_cn))
        .issuer_name(_name(issuer_cn))
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(issuer_key, hashes.SHA256())
    )


def _key():
    return ec.generate_private_key(ec.SECP256R1())


def test_orders_unordered_intermediates_and_omits_root_and_unrelated():
    root_key, int1_key, int2_key, leaf_key = _key(), _key(), _key(), _key()
    root = _cert("root", root_key, "root", root_key)
    int1 = _cert("int1", int1_key, "root", root_key)
    int2 = _cert("int2", int2_key, "int1", int1_key)
    leaf = _cert("leaf", leaf_key, "int2", int2_key)
    other_key = _key()
    unrelated = _cert("other", other_key, "other", other_key)

    chain = _build_chain(leaf, [root, unrelated, int1, int2])

    assert chain == [int2, int1]


def test_no_additional_certificates():
    key = _key()
    leaf = _cert("leaf", key, "leaf", key)
    assert _build_chain(leaf, None) == []
    assert _build_chain(leaf, []) == []


def test_self_signed_leaf_is_not_chained():
    key = _key()
    leaf = _cert("leaf", key, "leaf", key)
    assert _build_chain(leaf, [leaf]) == []


def test_same_subject_wrong_key_is_not_selected():
    root_key, int_key, impostor_key, leaf_key = _key(), _key(), _key(), _key()
    real = _cert("int", int_key, "root", root_key)
    # Same subject as the real issuer, but a different key
    impostor = _cert("int", impostor_key, "root", root_key)
    leaf = _cert("leaf", leaf_key, "int", int_key)

    assert _build_chain(leaf, [impostor, real]) == [real]


def test_self_issued_but_not_self_signed_is_chained():
    # Key rollover: subject == issuer but signed by the previous key
    old_key, new_key, leaf_key = _key(), _key(), _key()
    rollover = _cert("ca", new_key, "ca", old_key)
    leaf = _cert("leaf", leaf_key, "ca", new_key)

    assert _build_chain(leaf, [rollover]) == [rollover]


def test_cross_signed_duplicate_subject_yields_valid_chain():
    root1_key, root2_key, int_key, leaf_key = _key(), _key(), _key(), _key()
    root1 = _cert("root1", root1_key, "root1", root1_key)
    root2 = _cert("root2", root2_key, "root2", root2_key)
    int_a = _cert("int", int_key, "root1", root1_key)
    int_b = _cert("int", int_key, "root2", root2_key)
    leaf = _cert("leaf", leaf_key, "int", int_key)

    chain = _build_chain(leaf, [root1, root2, int_a, int_b])

    assert len(chain) == 1
    assert chain[0] in (int_a, int_b)
