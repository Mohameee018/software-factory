from factory.self_test import run_self_test


def test_deterministic_factory_self_test():
    results = run_self_test()
    assert results == {
        "telegram_intake": "PASS",
        "mock_workflow": "PASS",
    }
