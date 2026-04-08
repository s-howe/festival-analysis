from festival_analysis.normalize import normalize_name, split_b2b


def test_normalize_basic():
    assert normalize_name("  Dekmantel  ") == "dekmantel"
    assert normalize_name("Nuits   Sonores") == "nuits sonores"


def test_split_b2b_single():
    assert split_b2b("Aphex Twin") == ["Aphex Twin"]


def test_split_b2b_pair():
    assert split_b2b("Helena Hauff b2b DJ Stingray") == ["Helena Hauff", "DJ Stingray"]


def test_split_b2b_three():
    assert split_b2b("A B2B B b2b C") == ["A", "B", "C"]


def test_split_b2b_vs_and_amp():
    assert split_b2b("X vs Y") == ["X", "Y"]
    assert split_b2b("X & Y") == ["X", "Y"]
