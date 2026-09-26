from pathlib import Path
from factory.agents.base import Agent
from factory.models import AgentResult
from factory.adapters.registry import detect
from factory.tools.testing import execute

class TesterAgent(Agent):
    name='Test / QA Agent'; role='tester'; instructions='Run real adapter-defined validation and preserve exact evidence.'
    def run(self,context,task=None):
        a=detect(context.workspace)
        if not a:
            return AgentResult(success=False,agent_name=self.name,summary='Unsupported project type; no safe worker environment is available.',errors=['Unsupported project type.'],next_action='blocked')
        results=[]
        
        try:
            commands=a.validation_commands(context.workspace)
        except TypeError:
            commands=a.validation_commands()
        for kind,cmd in commands:
            try:
                r=execute('tester',kind,cmd,context.workspace,context.timeout)
                results.append((kind,cmd,r.exit_code,r.stdout,r.stderr,r.duration_seconds))
                if r.exit_code:
                    break
            except Exception as e:
                return AgentResult(success=False,agent_name=self.name,summary='Test command failed to execute.',errors=[str(e)],commands_executed=[x[1] for x in results],tests_run=[x[0] for x in results])
        failed=[x for x in results if x[2]!=0]
        report=['# QA Test Report','', 'PASS' if not failed else 'FAIL','']
        for kind,cmd,code,stdout,stderr,duration in results:
            report.append(f'## {kind} | exit={code} | {duration:.2f}s')
            report.append(f'`{cmd}`'); report.append(''); report.append(stdout[-6000:]); report.append(stderr[-3000:])
        (Path(context.workspace)/'docs').mkdir(parents=True,exist_ok=True)
        (Path(context.workspace)/'docs'/'TEST_REPORT.md').write_text('\n'.join(report),encoding='utf-8')
        return AgentResult(success=not failed,agent_name=self.name,summary='QA cycle completed.' if not failed else 'QA found failures.',detailed_output={'results':results},commands_executed=[x[1] for x in results],tests_run=[x[0] for x in results],errors=[f'{x[1]}\n{x[4]}' for x in failed],next_action='review' if not failed else 'fix',files_created=['docs/TEST_REPORT.md'],completion_evidence=['docs/TEST_REPORT.md'])
