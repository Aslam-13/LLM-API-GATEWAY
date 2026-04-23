from app.auth.keys import KEY_PREFIX, extract_prefix, generate_key, verify_key


def test_generate_key_shape():
    g = generate_key()
    assert g.plaintext.startswith(KEY_PREFIX)
    assert g.prefix == g.plaintext[: len(KEY_PREFIX) + 6]
    assert g.hash.startswith("$argon2")
    assert g.plaintext != g.hash


def test_verify_key_accepts_original_rejects_tampered():
    g = generate_key()
    assert verify_key(g.plaintext, g.hash) is True
    assert verify_key(g.plaintext + "x", g.hash) is False
    assert verify_key("sk-gw-live-" + "a" * 32, g.hash) is False


def test_verify_key_on_bad_hash_returns_false():
    assert verify_key("whatever", "not-a-hash") is False


def test_extract_prefix_rejects_non_gw_keys():
    assert extract_prefix("random-token") is None
    assert extract_prefix("") is None
    assert extract_prefix(KEY_PREFIX + "abcdef123") == KEY_PREFIX + "abcdef"
