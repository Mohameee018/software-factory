from __future__ import annotations
import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from factory.models import ProjectType, WorkflowState, WorkflowEvent
from factory.approvals import ApprovalService
from factory.integrations.telegram.formatter import project_status, task_lines
from factory.roles import extract_target, TAG_TO_ROLE

class TelegramHandlers:
    def __init__(self, service): self.service=service; self.queue=getattr(service,'job_queue',None)
    def _enqueue(self, project_id, task_id=None, priority=50):
        if self.queue: return self.queue.enqueue(project_id,task_id,priority)
        return None
    async def start(self, update:Update, context:ContextTypes.DEFAULT_TYPE): await update.effective_message.reply_text('Software Factory online. Use /help.')
    async def help(self, update, context): await update.effective_message.reply_text('/new /projects /project <id> /status <id> /tasks <id> /run <id> /pause <id> /resume <id> /cancel <id> /retry <id> /logs <id> /approve <id> /reject <id> /review <id> /feedback <id> <text>')
    async def new(self, update, context):
        if context.args:
            description=' '.join(context.args); p=self.service.create_project('Telegram Project',description); context.user_data['active_project_id']=p.id; effective_user=getattr(update,'effective_user',None); db=getattr(self.service,'db',None);
            if effective_user and db and hasattr(db,'set_active_project'): db.set_active_project(effective_user.id,p.id)
            self._enqueue(p.id); await update.effective_message.reply_text(f'Created <code>{p.id}</code>. 🚀 Execution queued.',parse_mode='HTML'); return
        context.user_data['awaiting_project']=True; await update.effective_message.reply_text('Describe the project you want to build.')
    async def text(self, update, context):
        raw = update.effective_message.text or ''
        target, message = extract_target(raw)
        if target:
            pid = context.user_data.get('active_project_id') or self.service.db.get_active_project(update.effective_user.id)
            if not pid or not self.service.db.get_project(pid):
                await update.effective_message.reply_text('No active project. Use /new first.')
                return
            p = self.service.db.get_project(pid)
            if target == '#ALL':
                self.service.db.event(WorkflowEvent(project_id=pid,event_type='HUMAN_DIRECTIVE',details={'target':'#ALL','message':message}))
                f = Path(p.workspace_path) / 'docs' / 'TEAM_CONTEXT.md'; f.parent.mkdir(parents=True,exist_ok=True)
                with f.open('a',encoding='utf-8') as fh: fh.write('\n\n## #ALL directive\n' + message + '\n')
                await update.effective_message.reply_text('📢 #ALL directive saved to the shared factory context.')
                self._enqueue(pid,priority=100)
                return
            role = TAG_TO_ROLE[target]
            self.service.db.event(WorkflowEvent(project_id=pid,event_type='HUMAN_DIRECTIVE',details={'target':target,'role':role,'message':message}))
            f = Path(p.workspace_path) / 'docs' / 'TEAM_CONTEXT.md'
            f.parent.mkdir(parents=True,exist_ok=True)
            with f.open('a',encoding='utf-8') as fh:
                fh.write("\n\n## " + target + " directive\n" + message + "\n")
            if role == 'uiux' and p.current_state == WorkflowState.WAITING_FOR_DESIGN_APPROVAL:
                self.service.add_feedback(pid, message)
            elif role == 'developer':
                self.service._add_fix_task(p, target + ' direct fix', message)
            await update.effective_message.reply_text('📨 ' + target + ' استلم الرسالة. هتتنفذ حسب ترتيب الـworkflow، ومش هتتخطى الموظف اللي قبله.')
            self._enqueue(pid,priority=100)
            return
        if not context.user_data.pop('awaiting_project',False):
            pid=context.user_data.get('active_project_id')
            if pid and self.service.db.get_project(pid):
                p=self.service.db.get_project(pid); msg=update.effective_message.text.strip().casefold()
                if p.current_state in (WorkflowState.WAITING_FOR_DESIGN_APPROVAL, WorkflowState.READY_FOR_HUMAN) and msg in {'تمام','تم','موافق','approve','approved','ok','okay'}:
                    action='design_approval' if p.current_state==WorkflowState.WAITING_FOR_DESIGN_APPROVAL else 'final_approval'
                    approvals=[a for a in self.service.db.list_approvals(p.id) if a.requested_action==action and a.status.value=='PENDING']
                    if approvals:
                        ApprovalService(self.service.db).resolve(approvals[-1],True,'Human approved via Telegram')
                        self._enqueue(p.id,priority=100)
                        await update.effective_message.reply_text('✅ تمت الموافقة. المصنع بيكمل المرحلة التالية.')
                    return
                t=self.service.add_feedback(pid,update.effective_message.text)
                if t:
                    await update.effective_message.reply_text(f'🧑‍💼 #PM Feedback saved as task <code>{t.id}</code>. Resuming the factory.',parse_mode='HTML')
                else:
                    await update.effective_message.reply_text('🎨 #UIUX التعديل اتسجل. برجع الـUI/UX Agent يعيد التصميم.')
                    self._enqueue(pid,priority=100)
                return
            return
        name='Telegram Project'
        p=self.service.create_project(name, update.effective_message.text)
        context.user_data['active_project_id']=p.id; effective_user=getattr(update,'effective_user',None); db=getattr(self.service,'db',None)
        if effective_user and db and hasattr(db,'set_active_project'): db.set_active_project(effective_user.id,p.id)
        self._enqueue(p.id)
        await update.effective_message.reply_text(f'Created <code>{p.id}</code>. 🚀 Execution queued.',parse_mode='HTML')
    async def photo(self, update, context):
        caption=(update.effective_message.caption or '').strip()
        if not caption:
            await update.effective_message.reply_text('📷 الصورة وصلت. ابعت وصف المشروع في نفس الرسالة كـ caption عشان أبدأ.')
            return
        p=self.service.create_project('Telegram Project', caption)
        context.user_data['active_project_id']=p.id
        user=getattr(update,'effective_user',None)
        if user and hasattr(self.service.db,'set_active_project'): self.service.db.set_active_project(user.id,p.id)
        photo=update.effective_message.photo[-1]
        tg_file=await photo.get_file()
        target=Path(p.workspace_path)/'docs'/'design'/'reference.png'
        target.parent.mkdir(parents=True,exist_ok=True)
        await tg_file.download_to_drive(custom_path=str(target))
        self.service.db.event(WorkflowEvent(project_id=p.id,event_type='DESIGN_REFERENCE_RECEIVED',details={'path':'docs/design/reference.png'}))
        self._enqueue(p.id,priority=100)
        await update.effective_message.reply_text(f'📷 Reference screenshot saved. Created <code>{p.id}</code> and queued the design phase.',parse_mode='HTML')

    async def projects(self, update, context):
        ps=self.service.db.list_projects(); await update.effective_message.reply_text('\n'.join(f'{p.id} [{p.current_state.value}] {p.name}' for p in ps) or 'No projects.')
    async def project(self, update, context):
        p=await self._require_project(update,context)
        if p: await update.effective_message.reply_text(project_status(p),parse_mode='HTML')
    async def status(self, update, context): return await self.project(update,context)
    async def tasks(self, update, context):
        p=await self._require_project(update,context)
        if not p:
            return
        await update.effective_message.reply_text(task_lines(self.service.db.list_tasks(p.id)),parse_mode='HTML')
    async def run(self, update, context):
        p=await self._require_project(update,context)
        if p: self._enqueue(p.id); await update.effective_message.reply_text('🚀 Project execution queued. Worker will continue in the background.')
    async def pause(self, update, context):
        p=await self._require_project(update,context)
        if p:
            if self.queue: self.queue.cancel_project(p.id)
            self.service.pause(p.id)
            await update.effective_message.reply_text('PAUSED. Pending background jobs were safely stopped.')
    async def resume(self, update, context):
        p=await self._require_project(update,context)
        if p:
            self._enqueue(p.id,priority=100)
            await update.effective_message.reply_text('▶️ Project resumed and queued in the background.')
    async def cancel(self, update, context):
        p=await self._require_project(update,context)
        if p:
            if self.queue: self.queue.cancel_project(p.id)
            self.service.set_state(p,WorkflowState.CANCELLED)
            await update.effective_message.reply_text('CANCELLED')
    async def retry(self, update, context):
        p=await self._require_project(update,context)
        if p:
            try: await asyncio.to_thread(self.service.retry,p.id)
            except Exception as e: await update.effective_message.reply_text(f'Retry blocked: {e}')
    async def logs(self, update, context):
        p=await self._require_project(update,context)
        if p: await update.effective_message.reply_text('\n'.join(f'{e.timestamp.isoformat()} {e.event_type}' for e in self.service.db.list_events(p.id,30)) or 'No events.')
    async def approve(self, update, context): await self._resolve(update,context,True)
    async def reject(self, update, context): await self._resolve(update,context,False)
    async def review(self, update, context):
        p=await self._require_project(update,context)
        if p: await update.effective_message.reply_text(project_status(p),parse_mode='HTML')
    async def feedback(self, update, context):
        if len(context.args)<2: await update.effective_message.reply_text('Usage: /feedback <project_id> <feedback>'); return
        p=self.service.db.get_project(context.args[0]);
        if not p: await update.effective_message.reply_text('Project not found.'); return
        self.service.add_feedback(p.id,' '.join(context.args[1:])); self._enqueue(p.id,priority=90); await update.effective_message.reply_text('Feedback saved as new work and queued.')
    async def callback(self, update, context):
        q=update.callback_query; await q.answer()
        if not self.service.authorized(update): return
        try: _,action,aid=q.data.split(':',2); a=self.service.db.get_approval(aid)
        except Exception: return
        if not a or a.status.value!='PENDING': await q.edit_message_text('Approval is no longer pending.'); return
        approved = action == 'a'
        ApprovalService(self.service.db).resolve(a,approved,f'Telegram user {update.effective_user.id}')
        await q.edit_message_text('APPROVED' if approved else 'REJECTED')
        p = self.service.db.get_project(a.project_id)
        if p and a.requested_action == 'design_approval':
            if approved:
                self._enqueue(a.project_id, priority=100)
            else:
                self.service.set_state(p, WorkflowState.DESIGNING)
                self._enqueue(a.project_id, priority=100)
        elif p and a.requested_action == 'final_approval':
            if approved:
                self._enqueue(a.project_id, priority=100)
            else:
                self.service.add_feedback(a.project_id, a.response or 'Final approval rejected; please implement the requested changes.')
                self._enqueue(a.project_id, priority=100)
                await q.edit_message_text('FINAL APPROVAL REJECTED — changes were queued for the factory.')
        elif approved:
            self._enqueue(a.project_id, a.task_id, priority=100)
    def _project(self,u,c):
        pid=c.args[0] if c.args else c.user_data.get('active_project_id')
        effective_user = getattr(u,'effective_user',None) if u is not None else None
        if not pid and effective_user: pid=self.service.db.get_active_project(effective_user.id)
        if pid and effective_user and hasattr(self.service.db,'set_active_project'): self.service.db.set_active_project(effective_user.id,pid)
        return self.service.db.get_project(pid) if pid else None
    async def _require_project(self,u,c):
        p=self._project(u,c)
        if not p:
            await u.effective_message.reply_text('No active project. Use /projects, /new, or provide a project ID.')
        return p
    async def _resolve(self,u,c,approved):
        if not self.service.authorized(u): return
        aid=c.args[0] if c.args else ''
        a=self.service.db.get_approval(aid)
        if not a: await u.effective_message.reply_text('Approval not found.'); return
        ApprovalService(self.service.db).resolve(a,approved,f'Telegram user {u.effective_user.id}')
        if approved:
            self._enqueue(a.project_id,a.task_id,priority=100)
        elif a.requested_action == 'final_approval':
            self.service.add_feedback(a.project_id, a.response or 'Final approval rejected; please implement the requested changes.')
            self._enqueue(a.project_id,priority=100)
        await u.effective_message.reply_text('APPROVED' if approved else 'REJECTED')
    async def _set_state(self,u,c,state):
        p=await self._require_project(u,c)
        if p: self.service.set_state(p,state); await u.effective_message.reply_text(state.value)

