from pathlib import Path

from factory.traceability import write_report


def test_traceability_uses_stable_ids(tmp_path):
    docs=tmp_path/"docs"
    docs.mkdir()
    (docs/"REQUIREMENTS.md").write_text("- RQ-001: Users can sign in\n",encoding="utf-8")
    (docs/"PRD.md").write_text("- RQ-001: Users can sign in\n",encoding="utf-8")
    (docs/"TASKS.md").write_text("- T-001: Implement user sign in\n",encoding="utf-8")
    report=write_report(str(tmp_path))
    assert report.complete
    text=(docs/"TRACEABILITY.md").read_text(encoding="utf-8")
    assert "RQ-001" in text
    assert "T-001" in text


def test_traceability_flags_unmapped_requirement(tmp_path):
    docs=tmp_path/"docs"
    docs.mkdir()
    (docs/"REQUIREMENTS.md").write_text("- RQ-001: Export satellite telemetry\n",encoding="utf-8")
    (docs/"TASKS.md").write_text("- T-001: Build login screen\n",encoding="utf-8")
    report=write_report(str(tmp_path))
    assert not report.complete
    assert report.unmapped
