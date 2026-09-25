from __future__ import annotations

ROLE_TAGS = {
    'pm': '#PM',
    'project_manager': '#PM',
    'uiux': '#UIUX',
    'uiux_designer': '#UIUX',
    'architect': '#ARCHITECT',
    'developer': '#DEV',
    'dev': '#DEV',
    'tester': '#TESTER',
    'qa': '#TESTER',
    'reviewer': '#REVIEWER',
    'code_reviewer': '#REVIEWER',
    'security': '#SECURITY',
    'security_reviewer': '#SECURITY',
    'uxreview': '#UXREVIEW',
    'uiux_reviewer': '#UXREVIEW',
    'release': '#RELEASE',
}

TAG_TO_ROLE = {
    '#PM': 'pm', '#UIUX': 'uiux', '#ARCHITECT': 'architect', '#DEV': 'developer',
    '#TESTER': 'tester', '#REVIEWER': 'reviewer', '#SECURITY': 'security',
    '#UXREVIEW': 'uxreview', '#RELEASE': 'release',
}

def tag_for(role: str) -> str:
    return ROLE_TAGS.get((role or '').strip().casefold(), '#FACTORY')

def extract_target(text: str):
    import re
    m = re.match(r'^\s*(#(?:PM|UIUX|ARCHITECT|DEV|TESTER|REVIEWER|SECURITY|UXREVIEW|RELEASE|ALL))\\b\\s*(.*)$', text or '', re.I | re.S)
    if not m:
        return None, (text or '').strip()
    tag = '#' + m.group(1)[1:].upper()
    return tag, m.group(2).strip()
