from __future__ import annotations
from pathlib import Path
import base64
from factory.agents.base import Agent
from factory.models import AgentResult
SCHEMA={'type':'object','properties':{'design_summary':{'type':'string'},'design_system':{'type':'string'},'screens':{'type':'array','items':{'type':'string'}},'user_flow':{'type':'string'},'html_preview':{'type':'string'}},'required':['design_summary','design_system','screens','user_flow','html_preview']}
class UIUXAgent(Agent):
    name='UI/UX Designer Agent'; role='uiux_designer'
    instructions='Design professional, coherent, production-ready interfaces. Avoid generic AI-looking layouts. Respect platform conventions, accessibility, responsive behavior, hierarchy, spacing, typography, color, states and user flows.'
    def __init__(self,provider): self.provider=provider
    def run(self,context,task=None):
        w=Path(context.workspace); d=w/'docs'/'design'; d.mkdir(parents=True,exist_ok=True)
        feedback=(w/'docs'/'DESIGN_FEEDBACK.md').read_text(encoding='utf-8',errors='ignore') if (w/'docs'/'DESIGN_FEEDBACK.md').exists() else 'No human design feedback yet.'
        existing=(d/'DESIGN.md').read_text(encoding='utf-8',errors='ignore') if (d/'DESIGN.md').exists() else 'No previous design.'
        prompt=f"""Project request:
{context.project.description}

Human feedback:
{feedback[-12000:]}

Previous design:
{existing[-12000:]}

Create a professional UI/UX direction. Infer platform and audience. Define information architecture, navigation, key screens, empty/loading/error/success states, responsive behavior, accessibility, typography, spacing, colors, components and interactions. Avoid generic AI-looking design. Return a self-contained HTML preview with inline CSS only, polished enough to guide implementation."""
        images = None
        reference = d / 'reference.png'
        if reference.is_file():
            try:
                images = [{'mime_type': 'image/png', 'data': base64.b64encode(reference.read_bytes()).decode('ascii')}]
                prompt += "\nA reference screenshot is attached. Treat it as the visual source of truth for the requested direction; preserve its important structure and intent while improving implementation-ready details."
            except OSError:
                images = None
        try: data=self.provider.generate_json(self.instructions,prompt,SCHEMA,timeout=context.timeout,images=images)
        except Exception as e: return AgentResult(success=False,agent_name=self.name,summary='UI/UX design failed.',errors=[str(e)],next_action='fix')
        if getattr(self.provider,'is_mock',False):
            data={'design_summary':'Clean professional MVP interface focused on the primary user journey.','design_system':'Responsive layout, clear hierarchy, accessible contrast, consistent spacing and reusable components.','screens':['Home / Dashboard','Primary workflow','Settings / Help'],'user_flow':'Open → understand state → perform primary action → receive clear success/error feedback.','html_preview':'<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:Inter,Arial,sans-serif;background:#f5f7fb;margin:0;padding:40px;color:#172033}.card{max-width:900px;margin:auto;background:white;border-radius:20px;padding:32px;box-shadow:0 12px 40px #0001}.btn{display:inline-block;padding:12px 18px;border-radius:10px;background:#172033;color:white}</style></head><body><div class="card"><h1>Product Preview</h1><p>Professional responsive interface preview.</p><span class="btn">Primary action</span></div></body></html>'}
        design_md=f"# UI/UX Design\n\n## Summary\n{data['design_summary']}\n\n## Design System\n{data['design_system']}\n\n## Screens\n"+'\n'.join(f"- {x}" for x in data['screens'])+f"\n\n## User Flow\n{data['user_flow']}\n"
        (d/'DESIGN.md').write_text(design_md,encoding='utf-8'); (d/'preview.html').write_text(data['html_preview'],encoding='utf-8'); (w/'docs'/'DESIGN.md').write_text(design_md,encoding='utf-8')
        return AgentResult(success=True,agent_name=self.name,summary='Professional UI/UX design and HTML preview generated.',detailed_output={'design_summary':data['design_summary'],'screens':data['screens'],'preview':'docs/design/preview.html'},files_created=['docs/DESIGN.md','docs/design/DESIGN.md','docs/design/preview.html'],next_action='human_design_approval')
