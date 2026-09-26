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
from factory.project_manager import ProjectManager
from factory.project_detection import detect_project_type

class TelegramHandlers:
    def __init__(self, service):
        self.service=service; self.queue=getattr(service,'job_queue',None)
        self.github=getattr(service,'github',None)
        self.notifier=getattr(service,'notifier',None)
        self.manager=ProjectManager(service)
    def _ensure_project_type(self, project, description):
        """Detect and persist a concrete project type at intake, before workflow work starts."""
        try:
            detected = detect_project_type(description or "", getattr(project, "workspace_path", None))
            if detected != ProjectType.UNKNOWN:
                project.project_type = detected
            if getattr(project, "project_type", ProjectType.UNKNOWN) == ProjectType.UNKNOWN:
                return
            db = getattr(self.service, "db", None)
            if db is not None:
                db.save_project(project)
                state = db.get_state(project.id)
                if state is not None:
                    state.project_type = detected
                    db.save_state(state)
        except Exception:
            # Intake detection must never break project creation.
            return

    async def _reply(self, update, text, **kwargs):
        """Send a client message with the live roadmap whenever a project is active."""
        pid = None
        try:
            pid = self.service.db.get_active_project(update.effective_user.id)
        except Exception:
            pass
        project = self.service.db.get_project(pid) if pid else None
        if project and isinstance(text, str):
            text = text.rstrip() + "\n\n" + self.manager.progress_map(project)
        return await update.effective_message.reply_text(text, **kwargs)

    def _set_state(self, project, state):
        setter = getattr(self.service, 'set_state', None)
        if setter:
            return setter(project, state)
        project.current_state = state
        db = getattr(self.service, 'db', None)
        if db and hasattr(db, 'save_project'):
            db.save_project(project)

    def _enqueue(self, project_id, task_id=None, priority=50):
        if self.queue: return self.queue.enqueue(project_id,task_id,priority)
        return None
    async def start(self, update:Update, context:ContextTypes.DEFAULT_TYPE): await update.effective_message.reply_text('Software Factory online. Use /help.')
    async def ai_smoke(self, update, context):
        """Run a real AI request and expose enough diagnostics to verify failover."""
        import traceback
        router = None
        try:
            router = self.service.model_router.for_role('planner')
            result = router.generate(
                'You are a production smoke-test assistant. Reply with exactly: AI_SMOKE_OK',
                'Return the required smoke-test text only.',
                timeout=min(getattr(self.service.settings, 'ai_timeout', 120), 30),
            )
            attempts = list(getattr(router, 'last_attempts', None) or [])
            model = getattr(router, 'last_model', None) or 'unknown'
            await update.effective_message.reply_text(
                f'✅ AI SMOKE PASS\\nProvider/model: <code>{model}</code>\\nAttempts: <code>{", ".join(attempts) or "none"}</code>\\nResponse: <code>{str(result)[:500]}</code>',
                parse_mode='HTML',
            )
        except Exception as exc:
            attempts = list(getattr(router, 'last_attempts', None) or [])
            skipped = list(getattr(router, 'last_skipped', None) or [])
            tb = traceback.format_exc().splitlines()[-6:]
            await update.effective_message.reply_text(
                f'❌ AI SMOKE FAIL\\nAttempts: <code>{", ".join(attempts) or "none"}</code>\\nSkipped: <code>{", ".join(skipped) or "none"}</code>\\nError: <code>{str(exc)[:700]}</code>\\nTrace: <code>{" | ".join(tb)[:1200]}</code>',
                parse_mode='HTML',
            )
    async def help(self, update, context): await update.effective_message.reply_text('/new /projects /project <id> /status <id> /manager /audit /requirements /tasks <id> /run <id> /pause <id> /resume <id> /cancel <id> /retry <id> /logs <id> /approve <id> /reject <id> /review <id> /feedback <id> <text> /github-public <id>')
    async def new(self, update, context):
        if context.args:
            description=' '.join(context.args); p=self.service.create_project('Telegram Project',description); self._ensure_project_type(p,description)
            context.user_data['active_project_id']=p.id; effective_user=getattr(update,'effective_user',None); db=getattr(self.service,'db',None)
            if effective_user and db and hasattr(db,'set_active_project'): db.set_active_project(effective_user.id,p.id)
            self._set_state(p,WorkflowState.REQUIREMENTS_GATHERING)
            await update.effective_message.reply_text(f'Created <code>{p.id}</code>. 🧑‍💼 #REQUIREMENTS هراجع اللي قلته وأسألك فقط عن اللي ناقص.',parse_mode='HTML')
            if hasattr(p, 'workspace_path'):
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
            p=self.service.create_project('Telegram Project',raw); self._ensure_project_type(p,raw)
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
            msg=raw.casefold().strip()
            # Approval gates are deterministic workflow controls. Resolve them BEFORE
            # AI intent routing so the client-facing manager can never misclassify a
            # simple approval (for example "تمام") as an artifact request.
            if p.current_state in (WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL,WorkflowState.WAITING_FOR_DESIGN_APPROVAL,WorkflowState.READY_FOR_HUMAN) and msg in {'تمام','تم','موافق','approve','approved','ok','okay'}:
                action={WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL:'requirements_approval',WorkflowState.WAITING_FOR_DESIGN_APPROVAL:'design_approval',WorkflowState.READY_FOR_HUMAN:'final_approval'}[p.current_state]
                approvals=[a for a in self.service.db.list_approvals(p.id) if a.requested_action==action and a.status.value=='PENDING']
                if approvals:
                    ApprovalService(self.service.db).resolve(approvals[-1],True,'Human approved via Telegram')
                    if action=='requirements_approval':
                        self.service.set_state(p,WorkflowState.DESIGNING)
                        await update.effective_message.reply_text('✅ المتطلبات اتوافقت. الـManager هيبدأ مرحلة الـUI/UX والتصميم.')
                    else:
                        await update.effective_message.reply_text('✅ تمت الموافقة. المصنع بيكمل.')
                    self._enqueue(p.id,priority=100)
                else:
                    await update.effective_message.reply_text('ℹ️ مفيش طلب موافقة معلّق للمرحلة الحالية. هكمل من حالة المشروع الفعلية.')
                    self._enqueue(p.id,priority=100)
                return

            # Client-facing Project Manager resolves natural-language status/artifact requests
            # only after deterministic workflow gates have been handled.
            routed=self.manager.route(getattr(update.effective_user,'id',None),raw,p)
            if routed.get('intent')=='artifact':
                await self._send_requested_artifacts(update,context,p,routed.get('artifact',''))
                return
            if routed.get('intent')=='status':
                await update.effective_message.reply_text(self.manager.status_message(p),parse_mode='HTML')
                return
            if routed.get('intent')=='continue':
                self._enqueue(p.id,priority=100)
                await update.effective_message.reply_text('👔 <b>#MANAGER</b> تمام. رجعت الـworkflow للطابور وهتابع الموظفين من هنا.',parse_mode='HTML')
                return
            # Conversational acknowledgements/inquiries are not bug reports.
            conversational = {'تمام','تم','اشتغل','اشتاغل','ها','ها؟','؟','ok','okay','تمام؟','مستمر','كمل','كمّل'}
            if msg in conversational and p.current_state not in (WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL,WorkflowState.WAITING_FOR_DESIGN_APPROVAL,WorkflowState.READY_FOR_HUMAN):
                self.service.db.event(WorkflowEvent(project_id=pid,event_type='HUMAN_CONVERSATIONAL_INPUT',details={'message':raw,'classified_as':'acknowledgment_or_inquiry'}))
                if msg in {'اشتغل','اشتاغل','كمل','كمّل','مستمر'}:
                    job_id = self._enqueue(pid,priority=100)
                    # Give the worker a brief chance to claim the job so the reply
                    # reports the real live state instead of only confirming enqueue.
                    await asyncio.sleep(1.5)
                    live = self.service.db.get_project(pid) or p
                    jobs = self.service.db.list_jobs(pid, 5)
                    job = next((j for j in jobs if j[0] == job_id), None)
                    latest = self.service.db.list_events(pid, 1)
                    job_status = job[3] if job else 'UNKNOWN'
                    last_event = latest[0].event_type if latest else 'NONE'
                    await update.effective_message.reply_text(
                        f'👔 <b>#MANAGER</b> تمام، رجّعت المشروع للـworkflow.\\n'
                        f'📍 الحالة الآن: <b>{live.current_state.value}</b>\\n'
                        f'⚙️ Job: <code>{job_id or "none"}</code> — <b>{job_status}</b>\\n'
                        f'🕒 آخر حدث: <b>{last_event}</b>\\n'
                        f'📌 لو الحالة WAITING_FOR_QUOTA/BLOCKED فالمصنع استلم الأمر لكن العائق هو اللي موقف التنفيذ.',
                        parse_mode='HTML')
                else:
                    await update.effective_message.reply_text('👔 <b>#MANAGER</b> تمام، فهمت. مفيش Fix Task هتتعمل لمجرد الرسالة دي.',parse_mode='HTML')
                return
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
        try:
            memory=load_user_memory(self.service.settings.workspaces_root,update.effective_user.id)
            mem_path=Path(p.workspace_path)/'docs'/'USER_MEMORY.md'
            mem_path.parent.mkdir(parents=True,exist_ok=True)
            mem_path.write_text('# User Working Memory\\n\\n'+(memory or 'No durable preferences recorded yet.'),encoding='utf-8')
        except Exception:
            pass
        f=Path(p.workspace_path)/'docs'/'CLIENT_CONVERSATION.md'; f.parent.mkdir(parents=True,exist_ok=True)
        with f.open('a',encoding='utf-8') as fh: fh.write("\n\n## Client\n"+user_message+"\n")
        try:
            r=self.service.agents['requirements'].run(type('Ctx',(),{'project':p,'workspace':p.workspace_path,'timeout':self.service.settings.ai_timeout})())
        except Exception as e:
            await update.effective_message.reply_text(f'حصل خطأ وأنا بجمع المتطلبات: {e}'); return
        self._ensure_project_type(p, user_message)
        if r.next_action=='ask_client':
            await update.effective_message.reply_text('💬 '+r.summary); return
        if r.success:
            approval=ApprovalService(self.service.db).request(p.id,'requirements_approval','Requirements package is ready for client approval.',Severity.MEDIUM,files=['docs/PRD.md','docs/REQUIREMENTS.md','docs/ACCEPTANCE_CRITERIA.md'])
            st=self.service.db.get_state(p.id); st.approvals.append(approval.id); self.service.db.save_state(st)
            self.service.set_state(p,WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL)
            await update.effective_message.reply_text('📋 جهزت الـPRD والـRequirements والـAcceptance Criteria.\nهيوصلكوا كملفات دلوقتي. راجعهم، ولو تمام اكتب «تمام». ولو محتاج تعديل قولي عادي.')
            if self.notifier:
                try:
                    self.notifier.send_requirements_package(p)
                except Exception:
                    pass
        else:
            await update.effective_message.reply_text('⚠️ '+(r.summary or 'محتاج أعيد محاولة جمع المتطلبات.'))

    async def document(self, update, context):
        context.user_data.pop('awaiting_project',None)
        doc=update.effective_message.document
        pid=context.user_data.get('active_project_id') or self.service.db.get_active_project(update.effective_user.id)
        if pid and self.service.db.get_project(pid):
            p=self.service.db.get_project(pid)
        else:
            p=self.service.create_project('Telegram Project', (update.effective_message.caption or '').strip() or f'Client project with attached file: {doc.file_name}'); self._ensure_project_type(p, update.effective_message.caption or doc.file_name)
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

    async def _send_requested_artifacts(self, update, context, p, requested=''):
        requested=(requested or '').casefold()
        files=[]
        if p.current_state == WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL or any(x in requested for x in ('prd','requirements','acceptance')):
            files=['docs/PRD.md','docs/REQUIREMENTS.md','docs/ACCEPTANCE_CRITERIA.md']
        elif p.current_state == WorkflowState.WAITING_FOR_DESIGN_APPROVAL or any(x in requested for x in ('preview','design','الصورة','التصميم')):
            files=['docs/design/preview.png','docs/design/preview.jpg','docs/design/preview.jpeg','docs/design/preview.html']
        sent=False
        for rel in files:
            path=Path(p.workspace_path)/rel
            if not path.is_file():
                continue
            sent=True
            if path.suffix.lower() in {'.png','.jpg','.jpeg','.webp'} and self.notifier:
                self.notifier.send_photo(p,rel)
            elif self.notifier:
                self.notifier.send_document(p,rel)
        if not sent:
            await update.effective_message.reply_text('👔 <b>#MANAGER</b> لقيت إن الـartifact المطلوب مش موجود كملف قابل للإرسال حاليًا. هسجل ده كحالة محتاجة متابعة بدل ما أفترض إنه اتبعت.',parse_mode='HTML')
            self.service.db.event(WorkflowEvent(project_id=p.id,event_type='ARTIFACT_DELIVERY_MISSING',details={'requested':requested,'state':p.current_state.value}))
        else:
            await update.effective_message.reply_text('👔 <b>#MANAGER</b> أيوه، لقيت الـartifact وبعتهولك فوق. مش هاعتبر إنك طلبت تعديل لمجرد إنك سألت عنه.',parse_mode='HTML')

    async def manager(self, update, context):
        p=await self._require_project(update,context)
        if p: await update.effective_message.reply_text(self.manager.status_message(p),parse_mode='HTML')

    async def audit(self, update, context):
        from factory.supervisor import FactorySupervisor
        supervisor = FactorySupervisor(self.service, getattr(self.service, "job_queue", None))
        ok = supervisor.run_audit()
        await update.effective_message.reply_text(
            "🧠 <b>Factory Audit</b> اتعمل دلوقتي.\n"
            + ("✅ التقرير اتولد واتحدثت ذاكرة المصنع." if ok else "⚠️ التقرير اتولد لكن فيه مشكلة في تشغيل الـAI audit.")
            + "\n📄 شوف التقرير اليومي داخل .factory/FACTORY_AUDIT_YYYY-MM-DD.md",
            parse_mode="HTML",
        )

    async def requirements(self, update, context):
        p=await self._require_project(update,context)
        if p: await self._send_requested_artifacts(update,context,p,'requirements')

    async def github_public(self, update, context):
        if not context.args:
            await update.effective_message.reply_text('اكتب /github-public <project_id>.')
            return
        pid=context.args[0]
        p=self.service.db.get_project(pid)
        if not p:
            await update.effective_message.reply_text('المشروع مش موجود.')
            return
        try:
            info=self.service.github.make_public(p.workspace_path)
            self.service.db.event(WorkflowEvent(project_id=pid,event_type='GITHUB_REPOSITORY_PUBLIC',details=info or {}))
            await update.effective_message.reply_text(f'🌍 الريبو بقى Public.\n{info.get("html_url") or info.get("full_name")}')
        except Exception as exc:
            await update.effective_message.reply_text(f'⚠️ مقدرتش أغيّر حالة الريبو: {str(exc)[:1000]}')

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
        if not p:
            return
        events = self.service.db.list_events(p.id, 30)
        text = '\\n'.join(f'{e.timestamp.isoformat()} {e.event_type}' for e in events) or 'No events.'
        # Telegram messages are limited to 4096 characters. Keep a safety margin.
        max_chars = 3500
        if len(text) > max_chars:
            text = '⚠️ Logs truncated to the latest events.\\n' + text[-(max_chars - 50):]
        await update.effective_message.reply_text(text)
    async def approve(self, update, context): await self._resolve(update,context,True)
    async def reject(self, update, context): await self._resolve(update,context,False)
    async def review(self, update, context):
        p=await self._require_project(update,context)
        if p: await update.effective_message.reply_text(project_status(p),parse_mode='HTML')
    async def feedback(self, update, context):
        if len(context.args)<2: await update.effective_message.reply_text('Usage: /feedback <project_id> <feedback>'); return
        p=self.service.db.get_project(context.args[0]);
        if not p: await update.effective_message.reply_text('Project not found.'); return
        feedback=' '.join(context.args[1:])
        self.service.add_feedback(p.id,feedback)
        self._enqueue(p.id,priority=90)
        reply=self.manager.respond(getattr(update.effective_user,'id',None),feedback,p)
        await update.effective_message.reply_text(reply + "\n\n📌 اتسجلت كمهمة واتحطت في الـworkflow.",parse_mode='HTML')
    async def callback(self, update, context):
        q=update.callback_query; await q.answer()
        if not self.service.authorized(update): return
        try: _,action,aid=q.data.split(':',2); a=self.service.db.get_approval(aid)
        except Exception: return
        if not a or a.status.value!='PENDING': await q.edit_message_text('Approval is no longer pending.'); return
        approved = action == 'a'
        ApprovalService(self.service.db).resolve(a,approved,f'Telegram user {update.effective_user.id}')
        await q.edit_message_text(('✅ APPROVED\\n👔 #MANAGER: الموافقة اتسجلت، وهتابع انتقال المشروع للمرحلة التالية.' if approved else '❌ REJECTED\\n👔 #MANAGER: الرفض اتسجل، وهارجع المرحلة للمراجعة والتعديل.'))
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
    async def _set_state_command(self,u,c,state):
        p=await self._require_project(u,c)
        if p: self.service.set_state(p,state); await u.effective_message.reply_text(state.value)

