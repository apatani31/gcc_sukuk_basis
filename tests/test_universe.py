from src.universe import parent_key


def test_parent_key_matches_word_order_and_suffixes():
    assert parent_key("Sharjah, Emirate Of") == parent_key("Emirate of Sharjah") == "emirate sharjah"
    assert parent_key("Saudi Arabia, Kingdom Of (government)") == parent_key(
        "Saudi Arabia, Kingdom of (Government)")
    assert parent_key("Dubai Islamic Bank Pjsc") == parent_key("Dubai Islamic Bank PJSC")
    assert parent_key("Qatar Islamic Bank (Q.P.S.C)") == parent_key("Qatar Islamic Bank Qpsc")
    assert parent_key(None) != parent_key(None)  # NaN for missing names
