from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import socket
import threading
import time
from factory.models import new_id, now

class JobStatus(str, Enum):
    PENDING='PENDING'; RUNNING='RUNNING'; WAITING_APPROVAL='WAITING_APPROVAL'; WAITING_QUOTA='WAITING_QUOTA'; RETRYING='RETRYING'; COMPLETED='COMPLETED'; FAILED='FAILED'; CANCELLED='CANCELLED'

@dataclass(frozen=True)
class Job:
    id: str; project_id: str; task_id: str|None; status: str; priority: int; created_at: str; started_at: str|None; completed_at: str|None; retry_count: int; last_error: str|None; worker_state: str|None; worker_type: str='generic'

class PersistentJobQueue:
    def __init__(self, db, max_retries=5): self.db=db; self.max_retries=max_retries
    def enqueue(self, project_id, task_id=None, priority=50):
        return self.db.enqueue_job(project_id, task_id, priority)
    def claim(self, worker_id=None, worker_type='generic'): return self.db.claim_job(worker_id or socket.gethostname(), worker_type)
    def heartbeat(self, job_id, worker_id=None): return self.db.extend_job_lease(job_id, worker_id or socket.gethostname())
    def complete(self, job_id): self.db.update_job(job_id, JobStatus.COMPLETED.value, completed_at=now().isoformat(), worker_state='completed', lease_until=None)
    def retry(self, job_id, error): self.db.retry_job(job_id, error, self.max_retries)
    def fail(self, job_id, error): self.db.update_job(job_id, JobStatus.FAILED.value, completed_at=now().isoformat(), last_error=error, worker_state='failed')
    def cancel_project(self, project_id): self.db.cancel_pending_jobs(project_id)
    def pending_count(self): return self.db.queue_count()
    def update_waiting(self, job_id): self.db.update_job(job_id, JobStatus.WAITING_APPROVAL.value, worker_state='waiting_approval')
    def update_waiting_quota(self, job_id, resume_at): self.db.update_job(job_id, JobStatus.WAITING_QUOTA.value, worker_state='waiting_quota', resume_at=resume_at)

class FactoryWorker:
    def __init__(self, orchestrator, queue, poll_interval=2.0, worker_id=None, worker_type='generic'):
        self.orchestrator=orchestrator; self.queue=queue; self.poll_interval=poll_interval; self.worker_id=worker_id or socket.gethostname(); self.worker_type=worker_type; self._stop=threading.Event()
    def stop(self): self._stop.set()
    def run_forever(self):
        self.orchestrator.db.recover_jobs()
        while not self._stop.is_set():
            job=self.queue.claim(self.worker_id, self.worker_type)
            if not job:
                self._stop.wait(self.poll_interval); continue
            try:
                def _renew():
                    while True:
                        if self._stop.wait(60): return
                        try:
                            if not self.queue.heartbeat(job.id, self.worker_id): return
                        except Exception:
                            return
                threading.Thread(target=_renew,daemon=True).start()
                current=self.orchestrator.db.get_project(job.project_id)
                # UNKNOWN is allowed at intake. The factory must reach the UI/UX
                # approval gate before implementation, and the stack may be decided later
                # by planning/architecture. Only specialized workers should enforce their
                # own project-type routing below.
                if current and current.project_type.value != self.worker_type and self.worker_type != 'generic':
                    self.queue.retry(job.id, f'Job routed to {current.project_type.value} worker, current worker is {self.worker_type}.')
                    continue
                if current and current.current_state.value in {'PAUSED','CANCELLED'}:
                    self.queue.fail(job.id, f'Project is {current.current_state.value.lower()}')
                    continue
                state=self.orchestrator.run(job.project_id, dry_run=False, mock=False)
                if state.current_state.value == 'WAITING_FOR_QUOTA':
                    resume_at=state.quota_resume_at
                    if resume_at:
                        self.orchestrator.db.update_job(job.id, JobStatus.WAITING_QUOTA.value, worker_state='waiting_quota', resume_at=resume_at)
                    else:
                        self.orchestrator.db.update_job(job.id, JobStatus.WAITING_QUOTA.value, worker_state='waiting_quota')
                elif state.current_state.value == 'BLOCKED' and self.orchestrator.db.has_pending_approval(job.project_id):
                    self.queue.update_waiting(job.id) if hasattr(self.queue,'update_waiting') else self.orchestrator.db.update_job(job.id, JobStatus.WAITING_APPROVAL.value, worker_state='waiting_approval')
                elif state.current_state.value in {'FAILED','CANCELLED'}:
                    self.queue.fail(job.id, f'Project ended in {state.current_state.value}')
                elif state.current_state.value in {'COMPLETED','READY_FOR_HUMAN'}:
                    self.queue.complete(job.id)
                else:
                    self.queue.complete(job.id)
            except Exception as exc:
                self.queue.retry(job.id, f'{type(exc).__name__}: {exc}')
                self.orchestrator.db.log_job_event(job.project_id, job.id, 'JOB_FAILED', str(exc))

    def run_once(self):
        job=self.queue.claim(self.worker_id, self.worker_type)
        if not job:return False
        try:
            current=self.orchestrator.db.get_project(job.project_id)
            if current and current.current_state.value in {'PAUSED','CANCELLED'}:
                self.queue.fail(job.id, f'Project is {current.current_state.value.lower()}')
                return True
            state=self.orchestrator.run(job.project_id, dry_run=False, mock=False)
            if state.current_state.value == 'WAITING_FOR_QUOTA': self.orchestrator.db.update_job(job.id, JobStatus.WAITING_QUOTA.value, worker_state='waiting_quota', resume_at=state.quota_resume_at)
            elif state.current_state.value == 'BLOCKED' and self.orchestrator.db.has_pending_approval(job.project_id): self.orchestrator.db.update_job(job.id, JobStatus.WAITING_APPROVAL.value, worker_state='waiting_approval')
            elif state.current_state.value in {'FAILED','CANCELLED'}: self.queue.fail(job.id, f'Project ended in {state.current_state.value}')
            else: self.queue.complete(job.id)
        except Exception as exc:
            self.queue.retry(job.id, f'{type(exc).__name__}: {exc}')
        return True
