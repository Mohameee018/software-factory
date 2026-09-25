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
    key=(role or '').strip().casefold()
    if key in ROLE_TAGS: return ROLE_TAGS[key]
    normalized=key.replace(' ','').replace('/','').replace('-','').replace('_','')
    if 'uiux' in normalized or ('ui' in normalized and 'ux' in normalized): return '#UIUX'
    if 'security' in normalized: return '#SECURITY'
    if 'review' in normalized and ('ui' in normalized or 'ux' in normalized): return '#UXREVIEW'
    if 'review' in normalized: return '#REVIEWER'
    if 'develop' in normalized or normalized in {'dev','coder'}: return '#DEV'
    if 'test' in normalized or normalized in {'qa','qualityassurance'}: return '#TESTER'
    if 'architect' in normalized or 'analyst' in normalized: return '#ARCHITECT'
    if 'planner' in normalized or 'projectmanager' in normalized: return '#PM'
    if 'release' in normalized: return '#RELEASE'
    return '#FACTORY'

def extract_target(text: str):
    import re
    m = re.match(r'^\s*(#(?:PM|UIUX|ARCHITECT|DEV|TESTER|REVIEWER|SECURITY|UXREVIEW|RELEASE|ALL))\b\s*(.*)$', text or '', re.I | re.S)
    if not m:
        return None, (text or '').strip()
    tag = '#' + m.group(1)[1:].upper()
    return tag, m.group(2).strip()
