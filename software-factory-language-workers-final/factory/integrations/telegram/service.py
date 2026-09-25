from factory.orchestrator import Orchestrator
from factory.queue import PersistentJobQueue

class TelegramService(Orchestrator):
    def __init__(self, db, settings, notifier=None):
        super().__init__(db, settings, notifier)
        self.job_queue = PersistentJobQueue(db, settings.job_max_retries)
