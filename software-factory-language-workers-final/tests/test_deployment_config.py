from pathlib import Path
import yaml

ROOT=Path(__file__).parents[1]

def test_compose_has_private_bot_and_language_workers():
    data=yaml.safe_load((ROOT/'docker-compose.yml').read_text())
    services=set(data['services'])
    assert {'bot','worker-python','worker-node','worker-java','worker-flutter'} <= services
    assert data['volumes']['factory_data'] is None
    for name in ('worker-python','worker-node','worker-java','worker-flutter'):
        assert data['services'][name]['restart'] == 'unless-stopped'
        assert 'factory_data:/data' in data['services'][name]['volumes']

def test_no_runtime_secrets_in_repository_files():
    forbidden=('123456:ABCDEF','TELEGRAM_BOT_TOKEN=123')
    forbidden_prefix='sk' + '-' 
    for p in ROOT.rglob('*'):
        if not p.is_file() or p == Path(__file__) or '.git' in p.parts or '__pycache__' in p.parts: continue
        if p.suffix in {'.py','.yml','.yaml','.env','.md','.sh','.ps1','.toml'}:
            text=p.read_text(encoding='utf-8',errors='ignore')
            assert not any(x in text for x in forbidden) or forbidden_prefix in text, p
