from concurrent.futures import ThreadPoolExecutor

from factory.database import Database


def test_queue_stress_and_expired_lease_recovery(tmp_path):
    db = Database(tmp_path / "factory.db")
    project_ids = []
    for i in range(25):
        from factory.models import Project, ProjectType
        p = Project(
            name=f"stress-{i}",
            description="queue stress",
            project_type=ProjectType.PYTHON,
            workspace_path=str(tmp_path / f"p-{i}"),
        )
        db.save_project(p)
        project_ids.append(p.id)
        for n in range(4):
            db.enqueue_job(p.id, priority=n)

    def claim(worker):
        return db.claim_job(worker, "python")

    with ThreadPoolExecutor(max_workers=8) as pool:
        claimed = list(pool.map(claim, [f"worker-{i}" for i in range(8)]))

    claimed = [j for j in claimed if j is not None]
    assert len({j.id for j in claimed}) == len(claimed)
    assert len({j.project_id for j in claimed}) == len(claimed)

    first = claimed[0]
    db.update_job(
        first.id,
        "RUNNING",
        worker_id="dead-worker",
        lease_until="2000-01-01T00:00:00+00:00",
    )
    assert db.reclaim_expired_jobs() >= 1
    recovered = db.list_jobs(first.project_id)[0]
    assert recovered[3] == "RETRYING"
