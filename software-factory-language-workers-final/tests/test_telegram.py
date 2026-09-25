from factory.config import Settings
from factory.database import Database
from factory.models import Project
from factory.approvals import ApprovalService

def test_telegram_authorization_logic(tmp_path):
    from factory.orchestrator import Orchestrator
    s=Settings(tmp_path/'db.sqlite',tmp_path/'w','INFO','mock','m',None,3,5,5,'https://api.openai.com/v1',None,{1},{10},False,'important')
    o=Orchestrator(Database(s.db_path),s)
    class U: pass
    u=U();u.effective_user=type('X',(),{'id':1})();u.effective_chat=type('X',(),{'id':10})()
    assert o.authorized(u)
    u.effective_user.id=2
    assert not o.authorized(u)

def test_approval_callback_data_is_persisted(tmp_path):
    from factory.approvals import ApprovalService
    db=Database(tmp_path/'db.sqlite');p=Project(name='p',description='d',workspace_path=str(tmp_path));db.save_project(p)
    a=ApprovalService(db).request(p.id,'delete','reason')
    assert db.get_approval(a.id).project_id==p.id
def test_telegram_default_denies_without_allowlist(tmp_path):
    from factory.orchestrator import Orchestrator
    s=__import__('factory.config',fromlist=['Settings']).Settings(tmp_path/'db.sqlite',tmp_path/'w','INFO','mock','m',None,3,5,5)
    o=Orchestrator(Database(s.db_path),s)
    class U: pass
    u=U();u.effective_user=type('X',(),{'id':1})();u.effective_chat=type('X',(),{'id':10})()
    assert not o.authorized(u)


def _install_telegram_test_stubs(monkeypatch):
    import sys
    import types

    telegram = types.ModuleType('telegram')
    telegram.Update = object
    telegram.InlineKeyboardButton = type('InlineKeyboardButton', (), {})
    telegram.InlineKeyboardMarkup = type('InlineKeyboardMarkup', (), {})
    ext = types.ModuleType('telegram.ext')

    class _Handler:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.command = args[0] if args else None

    class _Application:
        def __init__(self):
            self.handlers = []
        @classmethod
        def builder(cls):
            return cls._Builder()
        class _Builder:
            def token(self, token):
                return self
            def build(self):
                return _Application()
        def add_handler(self, handler):
            self.handlers.append(handler)

    class _Filter:
        def __and__(self, other): return self
        def __invert__(self): return self

    ext.Application = _Application
    ext.CommandHandler = _Handler
    ext.MessageHandler = _Handler
    ext.CallbackQueryHandler = _Handler
    ext.filters = types.SimpleNamespace(TEXT=_Filter(), COMMAND=_Filter())
    ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)

    monkeypatch.setitem(sys.modules, 'telegram', telegram)
    monkeypatch.setitem(sys.modules, 'telegram.ext', ext)
    for name in [
        'factory.integrations.telegram.bot',
        'factory.integrations.telegram.handlers',
        'factory.integrations.telegram',
    ]:
        sys.modules.pop(name, None)
    return _Application


def test_telegram_tasks_handler_is_registered_and_reachable(monkeypatch):
    Application = _install_telegram_test_stubs(monkeypatch)
    from factory.integrations.telegram.bot import TelegramBot
    from factory.integrations.telegram.handlers import TelegramHandlers

    class Service:
        def __init__(self):
            self.notifier = None

        def authorized(self, update):
            return True

    class Settings:
        telegram_bot_token = 'test-token'

    bot = TelegramBot(Service(), Settings())
    commands = [h.command for h in bot.application.handlers if h.command]
    assert 'tasks' in commands
    assert hasattr(TelegramHandlers, 'tasks')
    assert callable(TelegramHandlers.tasks)
    assert Application is not None


def test_telegram_tasks_responds_with_tasks_for_active_project(monkeypatch):
    _install_telegram_test_stubs(monkeypatch)
    from factory.integrations.telegram.handlers import TelegramHandlers

    class Message:
        def __init__(self):
            self.replies = []
        async def reply_text(self, text, **kwargs):
            self.replies.append((text, kwargs))

    class Project:
        id = 'project-123'

    class DB:
        def get_project(self, pid):
            return Project() if pid == 'project-123' else None
        def list_tasks(self, pid):
            return []

    class Service:
        db = DB()

    class Context:
        args = []
        user_data = {'active_project_id': 'project-123'}

    class Update:
        effective_message = Message()

    import asyncio
    asyncio.run(TelegramHandlers(Service()).tasks(Update(), Context()))
    assert Update.effective_message.replies
    assert Update.effective_message.replies[0][0] == 'No tasks.'


def test_telegram_tasks_gives_usage_when_no_project_is_selected(monkeypatch):
    _install_telegram_test_stubs(monkeypatch)
    from factory.integrations.telegram.handlers import TelegramHandlers

    class Message:
        def __init__(self):
            self.replies = []
        async def reply_text(self, text, **kwargs):
            self.replies.append(text)

    class DB:
        def get_project(self, pid):
            return None
        def list_tasks(self, pid):
            raise AssertionError('list_tasks should not be called without a project')

    class Service:
        db = DB()

    class Context:
        args = []
        user_data = {}

    class Update:
        effective_message = Message()

    import asyncio
    asyncio.run(TelegramHandlers(Service()).tasks(Update(), Context()))
    assert Update.effective_message.replies == ['No active project. Use /projects, /new, or provide a project ID.']


def test_telegram_tasks_responds_with_explicit_project_id(monkeypatch):
    _install_telegram_test_stubs(monkeypatch)
    from factory.integrations.telegram.handlers import TelegramHandlers

    class Message:
        def __init__(self): self.replies=[]
        async def reply_text(self, text, **kwargs): self.replies.append((text, kwargs))
    class Project: id='project-456'
    class DB:
        def get_project(self, pid): return Project() if pid == 'project-456' else None
        def list_tasks(self, pid): return []
    class Service: db=DB()
    class Context: args=['project-456']; user_data={}
    class Update: effective_message=Message()
    import asyncio
    asyncio.run(TelegramHandlers(Service()).tasks(Update(), Context()))
    assert Update.effective_message.replies[0][0] == 'No tasks.'


def test_telegram_project_fallback_uses_active_project(monkeypatch):
    _install_telegram_test_stubs(monkeypatch)
    from factory.integrations.telegram.handlers import TelegramHandlers
    class Project: id='active-789'
    class DB:
        def get_project(self, pid): return Project() if pid == 'active-789' else None
    class Service: db=DB()
    class Context: args=[]; user_data={'active_project_id':'active-789'}
    p=TelegramHandlers(Service())._project(None, Context())
    assert p.id == 'active-789'


def test_telegram_tasks_without_active_project_gives_helpful_message(monkeypatch):
    _install_telegram_test_stubs(monkeypatch)
    from factory.integrations.telegram.handlers import TelegramHandlers
    class Message:
        def __init__(self): self.replies=[]
        async def reply_text(self, text, **kwargs): self.replies.append(text)
    class DB:
        def get_project(self, pid): return None
        def list_tasks(self, pid): raise AssertionError('list_tasks should not be called')
    class Service: db=DB()
    class Context: args=[]; user_data={}
    class Update: effective_message=Message()
    import asyncio
    asyncio.run(TelegramHandlers(Service()).tasks(Update(), Context()))
    assert Update.effective_message.replies == ['No active project. Use /projects, /new, or provide a project ID.']


def test_telegram_new_uses_detected_project_type(monkeypatch):
    _install_telegram_test_stubs(monkeypatch)
    from factory.integrations.telegram.handlers import TelegramHandlers
    import asyncio

    class Message:
        def __init__(self): self.replies=[]
        async def reply_text(self, text, **kwargs): self.replies.append(text)
    class Project: id='flutter-project'
    class Service:
        def __init__(self): self.created=None
        def create_project(self, name, description, project_type=None):
            self.created=(name,description,project_type); return Project()
        def run(self,*args,**kwargs): pass
    class Context:
        args=['Build','a','Flutter','app']; user_data={}
    class Update: effective_message=Message()

    service=Service()
    # Do not execute the real workflow in this handler test.
    asyncio.run(TelegramHandlers(service).new(Update(), Context()))
    assert service.created == ('Telegram Project','Build a Flutter app',None)
    assert Context.user_data['active_project_id'] == 'flutter-project'


def test_telegram_cancel_uses_active_project_without_type_error(monkeypatch):
    _install_telegram_test_stubs(monkeypatch)
    from factory.integrations.telegram.handlers import TelegramHandlers
    import asyncio
    class Message:
        def __init__(self): self.replies=[]
        async def reply_text(self,text,**kwargs): self.replies.append(text)
    class Project: id='p1'
    class DB:
        def get_project(self,pid): return Project() if pid=='p1' else None
    class Service:
        db=DB()
        def set_state(self,p,state): self.called=(p.id,state)
    class Context: args=[]; user_data={'active_project_id':'p1'}
    class Update: effective_message=Message()
    h=TelegramHandlers(Service())
    asyncio.run(h.cancel(Update(),Context()))
    assert Update.effective_message.replies == ['CANCELLED']
