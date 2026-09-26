from __future__ import annotations
import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from factory.models import ProjectType, WorkflowState, WorkflowEvent, Severity
from factory.approvals import ApprovalService
from factory.integrations.telegram.formatter import project_status, task_lines
from factory.roles import extract_target, TAG_TO_ROLE
from factory.memory import load_user_memory, update_user_memory

class TelegramHandlers:
    def __init__(self, service): self.service=service; self.queue=getattr(service,'job_queue',None)
    def _enqueue(self, project_id, task_id=None, priority=50):
        if self.queue: return self.queue.enqueue(project_id,task_id,priority)
        return None
    async def start(self, update:Update, context:ContextTypes.DEFAULT_TYPE): await update.effective_message.reply_text('Software Factory online. Use /help.')
    async def help(self, update, context): await update.effective_message.reply_text('/new /projects /project <id> /status <id> /tasks <id> /run <id> /pause <id> /resume <id> /cancel <id> /retry <id> /logs <id> /approve <id> /reject <id> /review <id> /feedback <id> <text>')
    async def new(self, update, context):
        if context.args:
            description=' '.join(context.args); p=self.service.create_project('Telegram Project',description)
            context.user_data['active_project_id']=p.id; effective_user=getattr(update,'effective_user',None); db=getattr(self.service,'db',None)
            if effective_user and db and hasattr(db,'set_active_project'): db.set_active_project(effective_user.id,p.id)
            self.service.set_state(p,WorkflowState.REQUIREMENTS_GATHERING)
            await update.effective_message.reply_text(f'Created <code>{p.id}</code>. 🧑‍💼 #REQUIREMENTS هراجع اللي قلته وأسألك فقط عن اللي ناقص.',parse_mode='HTML')
            await self._requirements_turn(update,context,p,description)
            return
        context.user_data['awaiting_project']=True; await update.effective_message.reply_text('تمام. احكيلي عن المشروع براحتك، أو ابعت PRD/Design/صور/أي ملفات عندك.')
    async def text(self, update, context):
        raw = (update.effective_message.text or '').strip()
        target, message = extract_target(raw)
        if target:
            pid = context.user_data.get('active_project_id') or self.service.db.get_active_project(update.effective_user.id)
            if not pid or not self.service.db.get_project(pid):
                await update.effective_message.reply_text('مفيش مشروع نشط. اكتب /new الأول.')
                return
            p=self.service.db.get_project(pid)
            self.service.db.event(WorkflowEvent(project_id=pid,event_type='HUMAN_DIRECTIVE',details={'target':target,'message':message}))
            f=Path(p.workspace_path)/'docs'/'TEAM_CONTEXT.md'; f.parent.mkdir(parents=True,exist_ok=True)
            with f.open('a',encoding='utf-8') as fh: fh.write("\n\n## "+target+" directive\n"+message+"\n")
            if target == '#ALL':
                await update.effective_message.reply_text('📢 #ALL اتسجل في سياق الفريق.')
            else:
                await update.effective_message.reply_text('📨 '+target+' استلم الرسالة وهتدخل في الـworkflow.')
            self._enqueue(pid,priority=100); return

        pid=context.user_data.get('active_project_id') or self.service.db.get_active_project(update.effective_user.id)
        if context.user_data.pop('awaiting_project',False):
            p=self.service.create_project('Telegram Project',raw)
            context.user_data['active_project_id']=p.id; self.service.db.set_active_project(update.effective_user.id,p.id)
            p=self.service.db.get_project(p.id)
            # The first client message starts discovery, not coding.
            self.service.set_state(p,WorkflowState.REQUIREMENTS_GATHERING)
            await update.effective_message.reply_text('🧑‍💼 #REQUIREMENTS تمام، فهمت البداية. هسألك سؤال واحد في كل مرة حسب اللي تقوله، ولما الصورة تكتمل هجهز الـPRD والـRequirements.')
            await self._requirements_turn(update,context,p,raw)
            return

        if pid and self.service.db.get_project(pid):
            p=self.service.db.get_project(pid)
            if p.current_state==WorkflowState.REQUIREMENTS_GATHERING:
                await self._requirements_turn(update,context,p,raw); return
            msg=raw.casefold()
            if p.current_state in (WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL,WorkflowState.WAITING_FOR_DESIGN_APPROVAL,WorkflowState.READY_FOR_HUMAN) and msg in {'تمام','تم','موافق','approve','approved','ok','okay'}:
                action={WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL:'requirements_approval',WorkflowState.WAITING_FOR_DESIGN_APPROVAL:'design_approval',WorkflowState.READY_FOR_HUMAN:'final_approval'}[p.current_state]
                approvals=[a for a in self.service.db.list_approvals(p.id) if a.requested_action==action and a.status.value=='PENDING']
                if approvals:
                    ApprovalService(self.service.db).resolve(approvals[-1],True,'Human approved via Telegram')
                    if action=='requirements_approval':
                        self.service.set_state(p,WorkflowState.DESIGNING)
                        await update.effective_message.reply_text('✅ المتطلبات اتوافقت. الـManager هيبدأ يراجعها ويجهز خطة المشروع.')
                    else:
                        await update.effective_message.reply_text('✅ تمت الموافقة. المصنع بيكمل.')
                    self._enqueue(p.id,priority=100)
                    if action=='requirements_approval':
                        try:
                            provider=self.service.model_router.for_role('requirements')
                            update_user_memory(self.service.settings.workspaces_root,update.effective_user.id,(Path(p.workspace_path)/'docs'/'CLIENT_CONVERSATION.md').read_text(encoding='utf-8',errors='ignore'),provider,self.service.settings.ai_timeout)
                        except Exception: pass
                return
            if p.current_state==WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL:
                if msg.startswith(('عدّل','عدل','محتاج تعديل','مش تمام')):
                    self.service.db.feedback(p.id,raw)
                    self.service.set_state(p,WorkflowState.REQUIREMENTS_GATHERING)
                    await update.effective_message.reply_text('تمام، مش هعتمدها. قولّي إيه اللي محتاج يتغير وهكمل معاك من نفس السياق.')
                    await self._requirements_turn(update,context,p,raw); return
            if p.current_state in (WorkflowState.WAITING_FOR_DESIGN_APPROVAL,WorkflowState.READY_FOR_HUMAN):
                t=self.service.add_feedback(pid,raw)
                await update.effective_message.reply_text('📝 التعديل اتسجل وهيرجع للمرحلة المناسبة.'); self._enqueue(pid,priority=100); return
            t=self.service.add_feedback(pid,raw)
            if t: await update.effective_message.reply_text(f'📝 اتسجلت ملاحظتك كمهمة <code>{t.id}</code>.',parse_mode='HTML')
            return

        await update.effective_message.reply_text('اكتب /new ونبدأ.')

    async def _requirements_turn(self,update,context,p,user_message):
        f=Path(p.workspace_path)/'docs'/'CLIENT_CONVERSATION.md'; f.parent.mkdir(parents=True,exist_ok=True)
        with f.open('a',encoding='utf-8') as fh: fh.write("\n\n## Client\n"+user_message+"\n")
        try:
            r=self.service.agents['requirements'].run(type('Ctx',(),{'project':p,'workspace':p.workspace_path,'timeout':self.service.settings.ai_timeout})())
        except Exception as e:
            await update.effective_message.reply_text(f'حصل خطأ وأنا بجمع المتطلبات: {e}'); return
        if r.next_action=='ask_client':
            await update.effective_message.reply_text('💬 '+r.summary); return
        if r.success:
            approval=ApprovalService(self.service.db).request(p.id,'requirements_approval','Requirements package is ready for client approval.',Severity.MEDIUM,files=['docs/PRD.md','docs/REQUIREMENTS.md','docs/ACCEPTANCE_CRITERIA.md'])
            st=self.service.db.get_state(p.id); st.approvals.append(approval.id); self.service.db.save_state(st)
            self.service.set_state(p,WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL)
            await update.effective_message.reply_text('📋 جهزت الـPRD والـRequirements والـAcceptance Criteria.\nراجعهم، ولو تمام اكتب «تمام». ولو محتاج تعديل قولي عادي.')
        else:
            await update.effective_message.reply_text('⚠️ '+(r.summary or 'محتاج أعيد محاولة جمع المتطلبات.'))

    async def document(self, update, context):
        doc=update.effective_message.document
        pid=context.user_data.get('active_project_id') or self.service.db.get_active_project(update.effective_user.id)
        if pid and self.service.db.get_project(pid):
            p=self.service.db.get_project(pid)
        else:
            p=self.service.create_project('Telegram Project', (update.effective_message.caption or '').strip() or f'Client project with attached file: {doc.file_name}')
            context.user_data['active_project_id']=p.id; self.service.db.set_active_project(update.effective_user.id,p.id)
            self.service.set_state(p,WorkflowState.REQUIREMENTS_GATHERING)
        target=Path(p.workspace_path)/'docs'/'attachments'/doc.file_name
        target.parent.mkdir(parents=True,exist_ok=True)
        tg_file=await doc.get_file(); await tg_file.download_to_drive(custom_path=str(target))
        self.service.db.event(WorkflowEvent(project_id=p.id,event_type='PROJECT_FILE_RECEIVED',details={'path':str(target.relative_to(Path(p.workspace_path))),'name':doc.file_name}))
        if p.current_state==WorkflowState.REQUIREMENTS_GATHERING:
            await self._requirements_turn(update,context,p,f'أرفقت الملف: {doc.file_name}. افهمه واستخدمه بدل ما تسألني عن معلومات موجودة فيه.')
        else:
            self._enqueue(p.id,priority=100)
            await update.effective_message.reply_text(f'📎 استلمت {doc.file_name} وضمّيته لسياق المشروع.')
        return

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
        if p and a.requested_action == 'requirements_approval':
            if approved:
                self.service.set_state(p, WorkflowState.DESIGNING)
                self._enqueue(a.project_id, priority=100)
            else:
                self.service.set_state(p, WorkflowState.REQUIREMENTS_GATHERING)
                self._enqueue(a.project_id, priority=100)
        elif p and a.requested_action == 'design_approval':
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
        elif a.requested_action == 'requirements_approval':
            self.service.set_state(self.service.db.get_project(a.project_id), WorkflowState.REQUIREMENTS_GATHERING)
            self._enqueue(a.project_id,priority=100)
        elif a.requested_action == 'final_approval':
            self.service.add_feedback(a.project_id, a.response or 'Final approval rejected; please implement the requested changes.')
            self._enqueue(a.project_id,priority=100)
        await u.effective_message.reply_text('APPROVED' if approved else 'REJECTED')
    async def _set_state(self,u,c,state):
        p=await self._require_project(u,c)
        if p: self.service.set_state(p,state); await u.effective_message.reply_text(state.value)

