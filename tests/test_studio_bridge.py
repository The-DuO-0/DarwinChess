from studio.backend import normalize_move


def test_normalize_move_accepts_v2_api_shape():
    payload = {"move_uci": "e2e4", "move_san": "e4", "generation": 15}
    assert normalize_move(payload) == "e2e4"


def test_normalize_move_accepts_legacy_shape():
    assert normalize_move({"move": "g1f3"}) == "g1f3"
