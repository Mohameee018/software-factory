from __future__ import annotations
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from factory.models import ProjectType, WorkflowState
from factory.approvals import ApprovalService
from factory.integrations.telegram.formatter import project_status, task_lines

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
        if not context.user_data.pop('awaiting_project',False):
            pid=context.user_data.get('active_project_id')
            if pid and self.service.db.get_project(pid):
                p=self.service.db.get_project(pid); msg=update.effective_message.text.strip().casefold()
                if p.current_state==WorkflowState.WAITING_FOR_DESIGN_APPROVAL and msg in {'تمام','تم','موافق','approve','approved','ok','okay'}:
                    approvals=[a for a in self.service.db.list_approvals(p.id) if a.requested_action=='design_approval' and a.status.value=='PENDING']
                    if approvals:
                        ApprovalService(self.service.db).resolve(approvals[-1],True,'Human approved design via Telegram'); self._enqueue(p.id,priority=100)
                        await update.effective_message.reply_text('✅ التصميم اتوافق عليه. بدأت مرحلة التخطيط والتنفيذ.')
                    return
                t=self.service.add_feedback(pid,update.effective_message.text)
                await update.effective_message.reply_text(f'Feedback saved as task <code>{t.id}</code>. Resuming the factory.',parse_mode='HTML')
                await asyncio.to_thread(self.service.run,pid,False,False)
            return
        name='Telegram Project'
        p=self.service.create_project(name, update.effective_message.text)
        context.user_data['active_project_id']=p.id; effective_user=getattr(update,'effective_user',None); db=getattr(self.service,'db',None)
        if effective_user and db and hasattr(db,'set_active_project'): db.set_active_project(effective_user.id,p.id)
        self._enqueue(p.id)
        await update.effective_message.reply_text(f'Created <code>{p.id}</code>. 🚀 Execution queued.',parse_mode='HTML')
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
        ApprovalService(self.service.db).resolve(a,action=='a',f'Telegram user {update.effective_user.id}')
        await q.edit_message_text('APPROVED' if action=='a' else 'REJECTED')
        if action=='a': self._enqueue(a.project_id, a.task_id, priority=100)
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
        ApprovalService(self.service.db).resolve(a,approved,f'Telegram user {u.effective_user.id}'); await u.effective_message.reply_text('APPROVED' if approved else 'REJECTED')
        if approved: self.queue.enqueue(a.project_id,a.task_id,priority=100)
    async def _set_state(self,u,c,state):
        p=await self._require_project(u,c)
        if p: self.service.set_state(p,state); await u.effective_message.reply_text(state.value)

