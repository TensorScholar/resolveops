from resolveops.demo import run_demo


def test_demo() -> None:
    result = run_demo()
    assert result["analysis"]["disposition"] == "review_required"
    assert result["execution"]["success"] is True
    assert result["metrics"]["resolution_rate"] == 1.0
    assert result["audit_events"] == 4
