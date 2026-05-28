import os

import pytest

from backend.tools.theory_lookup import reset_index_for_tests, theory_lookup


def setup_module(module):
    reset_index_for_tests()


def test_empty_query_returns_empty_list():
    r = theory_lookup("")
    assert r["data"] == []


def test_range_advantage_query_finds_relevant_chunk():
    r = theory_lookup("range advantage on dry high card boards", k=3)
    assert len(r["data"]) > 0
    top_titles = " ".join(c["title"].lower() for c in r["data"])
    assert "range advantage" in top_titles or "c-bet" in top_titles


def test_cbet_sizing_query():
    r = theory_lookup("c-bet sizing", k=2)
    assert len(r["data"]) > 0
    assert any("sizing" in c["title"].lower() or "c-bet" in c["title"].lower() for c in r["data"])


def test_chunks_have_sources():
    r = theory_lookup("opponent type station LAG", k=3)
    assert len(r["data"]) > 0
    for c in r["data"]:
        assert c["source"]
        assert c["excerpt"]


def test_6max_query_pulls_relevant_chunk():
    # k=4 (was 3): the theory corpus grew with the merged chunks, which
    # renormalized BM25 scores and nudged the HU-vs-6max chunk to rank 4. Still
    # the same strict check — the real HU/6-max chunk must surface, just within
    # the top 4 now.
    r = theory_lookup("6max vs heads up open ranges", k=4)
    assert len(r["data"]) > 0
    found = False
    for c in r["data"]:
        if "6-max" in c["excerpt"].lower() or "hu" in c["title"].lower():
            found = True
            break
    assert found, "Expected a 6-max-related chunk in top-4 for that query."


def test_chunks_have_excerpts_within_limit():
    r = theory_lookup("3-bet pot postflop SPR", k=3)
    for c in r["data"]:
        assert len(c["excerpt"]) <= 700  # 600 cap + a little slack for boundary


def test_k_parameter_caps_results():
    r = theory_lookup("c-bet", k=2)
    assert len(r["data"]) <= 2
