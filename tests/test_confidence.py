from backend.tools.confidence import Confidence, is_green, voice_prefix


def test_confidence_values_match_design():
    assert Confidence.GREEN.value == "green"
    assert Confidence.YELLOW.value == "yellow"
    assert Confidence.AMBER.value == "amber"


def test_voice_prefix_returns_human_phrase():
    assert "Solver" in voice_prefix(Confidence.GREEN)
    assert "Theory" in voice_prefix("yellow")
    assert "no direct data" in voice_prefix(Confidence.AMBER)


def test_is_green():
    assert is_green(Confidence.GREEN)
    assert is_green("green")
    assert not is_green(Confidence.YELLOW)
    assert not is_green(None)
