from __future__ import annotations
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import threading, time
from .handlers import TelegramHandlers
from .notifications import TelegramNotifier

class TelegramBot:
    def __init__(self, service, settings):
        if not settings.telegram_bot_token: raise RuntimeError('TELEGRAM_BOT_TOKEN is not configured')
        self.service=service; self.settings=settings
        self.application=Application.builder().token(settings.telegram_bot_token).build()
        self.service.notifier=TelegramNotifier(settings)
        h=TelegramHandlers(service)
        self.application.add_handler(CommandHandler('start',self._guard(h.start))); self.application.add_handler(CommandHandler('help',self._guard(h.help))); self.application.add_handler(CommandHandler('new',self._guard(h.new)))
        for cmd,fn in [('projects',h.projects),('project',h.project),('status',h.status),('tasks',h.tasks),('run',h.run),('pause',h.pause),('resume',h.resume),('cancel',h.cancel),('retry',h.retry),('logs',h.logs),('approve',h.approve),('reject',h.reject),('review',h.review),('feedback',h.feedback)]: self.application.add_handler(CommandHandler(cmd,self._guard(fn)))
        self.application.add_handler(CallbackQueryHandler(h.callback,pattern=r'^apr:[ar]:'))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,self._guard(h.text)))
    def _guard(self, fn):
        async def wrapped(update, context):
            if not self.service.authorized(update):
                if update.effective_message: await update.effective_message.reply_text('Unauthorized.')
                return
            return await fn(update,context)
        return wrapped
    def run(self):
        stop = threading.Event()
        def heartbeat():
            while not stop.is_set():
                try:self.service.db.heartbeat('telegram', {'status':'running'})
                except Exception:pass
                stop.wait(10)
        t=threading.Thread(target=heartbeat,daemon=True); t.start()
        try:self.application.run_polling(drop_pending_updates=False)
        finally:
            stop.set()
            try:self.service.db.heartbeat('telegram', {'status':'stopped'})
            except Exception:pass
