from __future__ import annotations

from pathlib import Path
from typing import Any

from factory.models import WorkflowState


class ProjectManager:
    """Client-facing AI manager: interprets messages, inspects the live project, and routes intent."""

    ROUTING_SCHEMA = {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["status", "artifact", "approve", "reject", "feedback", "continue", "unknown"],
            },
            "artifact": {"type": "string"},
            "summary": {"type": "string"},
        },
        "required": ["intent", "artifact", "summary"],
    }

    def __init__(self, service):
        self.service = service

    def _project(self, user_id: int | None):
        db = self.service.db
        pid = db.get_active_project(user_id) if user_id is not None else None
        return db.get_project(pid) if pid else None

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join((text or "").casefold().strip().split())

    def _deterministic_intent(self, text: str, state: WorkflowState) -> tuple[str, str]:
        m = self._norm(text)
        artifact_words = (
            "فين الصورة", "الصورة فين", "ابعت الصورة", "ابعتلي الصورة",
            "اشوف الصورة", "أشوف الصورة", "التصميم فين", "فين التصميم",
            "ابعت التصميم", "ابعتهم", "ابعت الملفات", "فين الprd",
            "فين prd", "requirements فين", "acceptance criteria",
            "preview فين", "فين الـpreview", "فين الpreview",
        )
        if any(x in m for x in artifact_words):
            return "artifact", "المستخدم يريد رؤية الـartifact الذي قال المصنع إنه جهزه."
        if m in {"تمام", "تم", "موافق", "approve", "approved", "ok", "okay"}:
            return "approve", "المستخدم وافق على المرحلة الحالية."
        if m in {"لا", "ارفض", "مرفوض", "reject", "rejected"}:
            return "reject", "المستخدم رفض المرحلة الحالية."
        if any(x in m for x in ("وصلتوا لفين", "وصلتوا لايه", "وصلتوا لأيه", "وصلنا لفين", "وصلنا لأيه", "الحالة", "status", "ايه الاخبار", "إيه الأخبار")):
            return "status", "المستخدم يريد حالة المشروع الحالية."
        if m in {"كمل", "استمر", "continue", "كمّل"}:
            return "continue", "المستخدم يريد استمرار الـworkflow."
        return "", ""

    def route(self, user_id: int | None, text: str, project=None) -> dict[str, Any]:
        project = project or self._project(user_id)
        if not project:
            return {"intent": "unknown", "artifact": "", "summary": "لا يوجد مشروع نشط."}

        deterministic, summary = self._deterministic_intent(text, project.current_state)
        if deterministic:
            return {"intent": deterministic, "artifact": "", "summary": summary}

        provider = None
        try:
            provider = self.service.model_router.for_role("manager")
        except Exception:
            provider = None
        if provider is None:
            return {"intent": "feedback", "artifact": "", "summary": "سأتعامل مع الرسالة كملاحظة للمشروع."}

        state = self.service.db.get_state(project.id)
        recent = self.service.db.list_events(project.id, 12)
        context = (
            f"Project: {project.name} ({project.id})\n"
            f"State: {project.current_state.value}\n"
            f"Type: {project.project_type.value}\n"
            f"Last agent: {(state.timestamps.get('last_agent') if state else '')}\n"
            f"Recent events: {[e.event_type for e in recent]}\n"
            f"User message: {text}"
        )
        instructions = (
            "You are the client-facing Project Manager for a software factory. "
            "Interpret the user's Arabic/English message using the live project context. "
            "Do not invent project progress. Route only to one of: status, artifact, approve, reject, feedback, continue, unknown. "
            "artifact means the user wants a file/image/preview that the factory previously generated. "
            "Return a short Arabic summary."
        )
        try:
            data = provider.generate_json(instructions, context, self.ROUTING_SCHEMA, timeout=self.service.settings.ai_timeout)
            intent = str(data.get("intent", "unknown"))
            if intent not in {"status", "artifact", "approve", "reject", "feedback", "continue", "unknown"}:
                intent = "unknown"
            return {"intent": intent, "artifact": str(data.get("artifact", "")), "summary": str(data.get("summary", ""))}
        except Exception:
            return {"intent": "feedback", "artifact": "", "summary": "سأتعامل مع الرسالة كملاحظة للمشروع."}

    @staticmethod
    def progress_map(project) -> str:
        """Render a client-facing roadmap from requirements to a usable release."""
        s = project.current_state
        stages = [
            ("1", "فهم الفكرة والمتطلبات", {WorkflowState.IDEA, WorkflowState.REQUIREMENTS_GATHERING, WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL}),
            ("2", "اعتماد الـPRD والـAcceptance Criteria", {WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL}),
            ("3", "UI/UX والتصميم", {WorkflowState.DESIGNING, WorkflowState.WAITING_FOR_DESIGN_APPROVAL, WorkflowState.DESIGN_APPROVED}),
            ("4", "التخطيط والمعمارية وتجهيز المهام", {WorkflowState.PLANNING, WorkflowState.DOCUMENTATION, WorkflowState.ANALYSIS, WorkflowState.ARCHITECTURE, WorkflowState.TASK_CREATION}),
            ("5", "البرمجة وتنفيذ الـMVP", {WorkflowState.IMPLEMENTATION}),
            ("6", "الاختبارات وإصلاح المشاكل", {WorkflowState.TESTING, WorkflowState.FIXING}),
            ("7", "Code Review + UX Review + Security", {WorkflowState.REVIEWING, WorkflowState.UX_REVIEW, WorkflowState.SECURITY_REVIEW}),
            ("8", "Final Gate وتجهيز النسخة النهائية", {WorkflowState.READY_FOR_HUMAN}),
            ("9", "رفع المشروع على GitHub كـPrivate Repo", set()),
            ("10", "بناء Release قابل للاستخدام (APK/AAB أو الهدف المناسب)", set()),
            ("11", "النشر/التشغيل والتحقق النهائي", set()),
            ("12", "🎉 التسليم — البرنامج جاهز للاستخدام", {WorkflowState.COMPLETED}),
        ]
        order = {
            WorkflowState.IDEA: 0, WorkflowState.REQUIREMENTS_GATHERING: 0, WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL: 1,
            WorkflowState.DESIGNING: 2, WorkflowState.WAITING_FOR_DESIGN_APPROVAL: 2, WorkflowState.DESIGN_APPROVED: 2,
            WorkflowState.PLANNING: 3, WorkflowState.DOCUMENTATION: 3, WorkflowState.ANALYSIS: 3, WorkflowState.ARCHITECTURE: 3, WorkflowState.TASK_CREATION: 3,
            WorkflowState.IMPLEMENTATION: 4, WorkflowState.TESTING: 5, WorkflowState.FIXING: 5,
            WorkflowState.REVIEWING: 6, WorkflowState.UX_REVIEW: 6, WorkflowState.SECURITY_REVIEW: 6,
            WorkflowState.READY_FOR_HUMAN: 7, WorkflowState.COMPLETED: 11, WorkflowState.BLOCKED: 0, WorkflowState.FAILED: 0,
        }
        current = order.get(s, 0)
        if s == WorkflowState.WAITING_FOR_QUOTA:
            # Quota waiting must preserve the actual workflow stage instead of
            # looking like the project jumped back to intake.
            paused_from = None
            try:
                st = self.service.db.get_state(project.id)
                paused_from = st.paused_from if st else None
            except Exception:
                paused_from = None
            current = order.get(paused_from, current)
        lines = ["<b>🗺️ خريطة الطريق لحد ما البرنامج يبقى جاهز</b>"]
        for idx, name, states in stages:
            n = int(idx) - 1
            if s == WorkflowState.COMPLETED:
                mark = "✅"
            elif n < current:
                mark = "✅"
            elif n == current:
                mark = "🔵"
            else:
                mark = "⬜"
            suffix = " ← <b>أنت هنا</b>" if mark == "🔵" else ""
            lines.append(f"{mark} {idx}. {name}{suffix}")
        if s == WorkflowState.WAITING_FOR_QUOTA:
            lines.append("⏸️ <b>الحالة:</b> المصنع واقف مؤقتًا بسبب حصة الـAI، وسيكمل تلقائيًا من نفس المرحلة عند عودة الحصة.")
        elif s == WorkflowState.BLOCKED:
            lines.append("⚠️ <b>فيه عائق:</b> المدير هيحدد المشكلة والخطوة المطلوبة بدل ما يكمل بشكل أعمى.")
        elif s == WorkflowState.FAILED:
            lines.append("❌ <b>فيه فشل:</b> سيتم تسجيل السبب وإعادة المحاولة/الإصلاح حسب الـworkflow.")
        elif s == WorkflowState.COMPLETED:
            lines.append("\n📊 <b>التقدم:</b> 12/12 — مكتمل 🎉")
        else:
            lines.append(f"\n📊 <b>التقدم:</b> {current + 1}/12 مراحل رئيسية")
            lines.append(f"📌 <b>المتبقي:</b> {max(0, 11-current)} مراحل رئيسية، والعدد ممكن يزيد لو ظهرت إصلاحات أو موافقات.")
        return "\n".join(lines)

    def status_message(self, project) -> str:
        state = self.service.db.get_state(project.id)
        events = self.service.db.list_events(project.id, 20)
        last = events[-1] if events else None
        last_agent = state.timestamps.get("last_agent") if state else None
        lines = [
            "👔 <b>#MANAGER</b> تحديث المشروع",
            f"📦 <b>المشروع:</b> {project.name}",
            f"📍 <b>المرحلة:</b> {project.current_state.value}",
        ]
        if last_agent:
            lines.append(f"🤖 <b>آخر موظف اشتغل:</b> {last_agent}")
        if last:
            lines.append(f"🕒 <b>آخر حدث:</b> {last.event_type}")
        if project.current_state in {
            WorkflowState.DESIGNING, WorkflowState.PLANNING, WorkflowState.IMPLEMENTATION,
            WorkflowState.TESTING, WorkflowState.REVIEWING, WorkflowState.UX_REVIEW,
            WorkflowState.SECURITY_REVIEW, WorkflowState.FIXING,
        }:
            lines.append("🔄 <b>الحالة:</b> الفريق شغال حاليًا، وأي انتقال مهم أو مشكلة هبلغك بيها.")
        elif project.current_state in {
            WorkflowState.WAITING_FOR_REQUIREMENTS_APPROVAL,
            WorkflowState.WAITING_FOR_DESIGN_APPROVAL,
            WorkflowState.READY_FOR_HUMAN,
        }:
            lines.append("⏳ <b>الحالة:</b> مستني قرار منك.")
        elif project.current_state in {WorkflowState.BLOCKED, WorkflowState.FAILED}:
            lines.append("⚠️ <b>الحالة:</b> فيه عائق محتاج متابعة.")
        elif project.current_state == WorkflowState.COMPLETED:
            lines.append("✅ <b>الحالة:</b> المشروع مكتمل.")
        lines.append("")
        lines.append(self.progress_map(project))
        return "\n".join(lines)
