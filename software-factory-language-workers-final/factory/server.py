from __future__ import annotations
import signal
from factory.config import get_settings
from factory.database import Database
from factory.orchestrator import Orchestrator
from factory.queue import PersistentJobQueue, FactoryWorker
from factory.integrations.telegram.notifications import TelegramNotifier


def build_worker():
    settings=get_settings(); settings.ensure_directories(); db=Database(settings.db_path)
    notifier=TelegramNotifier(settings) if settings.telegram_enabled and settings.telegram_bot_token else None
    orchestrator=Orchestrator(db,settings,notifier=notifier)
    queue=PersistentJobQueue(db,settings.job_max_retries)
    return settings,db,FactoryWorker(orchestrator,queue,settings.worker_poll_interval,worker_type=settings.worker_type)

def run_worker():
    settings,db,worker=build_worker()
    db.heartbeat(f'worker:{settings.worker_type}', {'status':'starting','worker_type':settings.worker_type})
    def stop(*_): worker.stop()
    signal.signal(signal.SIGTERM,stop)
    if hasattr(signal,'SIGINT'): signal.signal(signal.SIGINT,stop)
    worker.run_forever()
    db.heartbeat(f'worker:{settings.worker_type}', {'status':'stopped','worker_type':settings.worker_type})
