from __future__ import annotations
from pathlib import Path
import json, urllib.request
from .formatter import project_status, approval_text
from .keyboards import approval_keyboard
from factory.roles import tag_for

class TelegramNotifier:
    """Synchronous notifier safe to call from the orchestrator worker thread."""
    def __init__(self, settings, db=None): self.settings=settings; self.db=db
    def _send(self, text, reply_markup=None):
        token=self.settings.telegram_bot_token
        if not token:return
        chat_ids=self.settings.telegram_allowed_chat_ids or self.settings.telegram_allowed_user_ids
        if not chat_ids and self.db:
            try: chat_ids=self.db.list_telegram_chats()
            except Exception: chat_ids=[]
        for chat_id in chat_ids:
            body={'chat_id':chat_id,'text':text,'parse_mode':'HTML'}
            if reply_markup is not None: body['reply_markup']=reply_markup.to_dict() if hasattr(reply_markup,'to_dict') else reply_markup
            try:
                req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
                urllib.request.urlopen(req,timeout=20).read()
            except Exception: pass
    def state_changed(self, project, state):
        important={'DESIGNING':'🎨 #UIUX بدأ تصميم المشروع','DESIGN_APPROVED':'✅ التصميم اتوافق عليه — الفريق يستعد للتنفيذ','PLANNING':'🧠 Planning started','DOCUMENTATION':'📋 Requirements generated','ANALYSIS':'🔍 Requirements analysis started','TASK_CREATION':'📋 Task creation started','IMPLEMENTATION':'💻 Implementation started','TESTING':'🧪 Tests running','REVIEWING':'🔍 Code review started','UX_REVIEW':'🎨 UI/UX implementation review started','SECURITY_REVIEW':'🛡️ Security review started','FIXING':'🔧 Fix loop started','READY_FOR_HUMAN':'✅ Project ready for human review','BLOCKED':'⛔ Project blocked','FAILED':'❌ Project failed','CANCELLED':'🛑 Project cancelled'}
        if state in important:self._send(f'{important[state]}\n\n{project_status(project)}')
    def agent_started(self, project, agent_name, action='بدأ العمل'):
        tag = tag_for(agent_name)
        self._send(f'🔄 <b>{tag}</b> {action}.')

    def approval_requested(self, approval):
        self._send(approval_text(approval),{'inline_keyboard':[[{'text':'✅ APPROVE','callback_data':f'apr:a:{approval.id}'},{'text':'❌ REJECT','callback_data':f'apr:r:{approval.id}'}]]})
    def design_ready(self, project, approval, result):
        data=result.detailed_output if isinstance(result.detailed_output,dict) else {}
        self._send(f"🎨 <b>UI/UX DESIGN READY</b>\n\n{project_status(project)}\n\n<b>Summary:</b> {data.get('design_summary','')}\n<b>Screens:</b> {', '.join(data.get('screens',[]))}\n\nPreview: <code>docs/design/preview.html</code>\n\nهتوصلك صورة الـ UI/UX دلوقتي.\n\nاضغط APPROVE أو اكتب «تمام». ", {'inline_keyboard':[[{'text':'✅ APPROVE DESIGN','callback_data':f'apr:a:{approval.id}'},{'text':'❌ REJECT DESIGN','callback_data':f'apr:r:{approval.id}'}]]})
        preview = data.get('design_preview_image')
        if preview:
            self._send_photo(project, preview)

    def _send_photo(self, project, relative_path):
        token=self.settings.telegram_bot_token
        if not token: return
        path=Path(project.workspace_path) / str(relative_path)
        if not path.is_file(): return
        chat_ids=self.settings.telegram_allowed_chat_ids or self.settings.telegram_allowed_user_ids
        if not chat_ids and self.db:
            try: chat_ids=self.db.list_telegram_chats()
            except Exception: chat_ids=[]
        for chat_id in chat_ids:
            try:
                boundary='factorytelegramphoto'
                data=path.read_bytes()
                body=(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
                      f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{path.name}"\r\n'
                      'Content-Type: image/png\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode()
                req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendPhoto',data=body,
                    headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
                urllib.request.urlopen(req,timeout=60).read()
            except Exception:
                pass

    def agent_result(self, project, result):
        tag = tag_for(getattr(result, 'agent_name', ''))
        summary = getattr(result, 'summary', '') or ('completed' if getattr(result, 'success', False) else 'reported a problem')
        icon = '✅' if getattr(result, 'success', False) else '⚠️'
        self._send(f'{icon} <b>{tag}</b> {summary}\\n\\n{project_status(project)}')

    def ready_summary(self, project, tasks):
        self._send(f'✅ <b>PROJECT READY FOR HUMAN REVIEW</b>\n\n{project_status(project)}\n\nTasks: {len(tasks)}')


    def release_ready(self, project, result):
        data = result.detailed_output if isinstance(result.detailed_output, dict) else {}
        package = data.get('package')
        self._send("📦 <b>#RELEASE</b> Release package created\n\n" + project_status(project) + "\n\nPackage: <code>" + str(package or 'release/') + "</code>")
        if package:
            self._send_document(project, package)

    def _send_document(self, project, relative_path):
        token=self.settings.telegram_bot_token
        if not token: return
        path=Path(project.workspace_path) / relative_path
        if not path.is_file(): return
        chat_ids=self.settings.telegram_allowed_chat_ids or self.settings.telegram_allowed_user_ids
        if not chat_ids and self.db:
            try: chat_ids=self.db.list_telegram_chats()
            except Exception: chat_ids=[]
        for chat_id in chat_ids:
            try:
                boundary='factorytelegram'
                data=path.read_bytes()
                body=(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
                      f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{path.name}"\r\n'
                      'Content-Type: application/zip\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode()
                req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendDocument',data=body,
                    headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
                urllib.request.urlopen(req,timeout=60).read()
            except Exception:
                pass
