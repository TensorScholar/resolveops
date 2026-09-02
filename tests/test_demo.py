from resolveops.demo import run_demo


def test_demo() -> None:
    result = run_demo()
    assert result["analysis"]["disposition"] == "review_required"
    assert result["execution"]["state"] == "succeeded"
    assert result["execution"]["attempt_count"] == 1
    assert result["metrics"]["resolution_rate"] == 1.0
    assert result["audit_events"] == 5
