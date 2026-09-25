from pathlib import Path
import sys
import pytest
from factory.config import Settings
from factory.providers.registry import build_provider
from factory.providers.http import OpenAICompatibleProvider
from factory.providers.base import LLMResponse
from factory.providers.mock import MockProvider
from factory.tools.filesystem import WorkspaceFS
from factory.tools.shell import run, _argv
from factory.adapters.flutter import FlutterAdapter

def test_mock_provider_structured_output():
    p=MockProvider()
    out=p.generate_json('system','prompt',{'type':'object','properties':{'ok':{'type':'boolean'},'items':{'type':'array'}}})
    assert out == {'ok':True,'items':[]}

def test_real_provider_requires_key(tmp_path):
    s=Settings(tmp_path/'db',tmp_path/'w','INFO','openai','model',None)
    with pytest.raises(RuntimeError, match='API key required'):
        build_provider(s)

def test_real_provider_configuration_without_network():
    p=OpenAICompatibleProvider('dummy','model','https://example.invalid',timeout=1,max_retries=0)
    assert p.model == 'model'
    assert p.base_url == 'https://example.invalid'

def test_developer_filesystem_is_workspace_bound(tmp_path):
    fs=WorkspaceFS(tmp_path,'developer')
    fs.write('app.py','print(1)')
    assert fs.read('app.py') == 'print(1)'
    with pytest.raises(PermissionError): fs.write('../escape.py','x')

def test_developer_cannot_delete_files():
    # Permission layer rejects deletion for developer role before touching the filesystem.
    from factory.permissions import PermissionDenied
    with pytest.raises(PermissionDenied):
        from factory.tools.filesystem import WorkspaceFS
        fs=WorkspaceFS('/tmp/software-factory-perm-test','developer'); fs.delete('missing.txt')

def test_shell_rejects_operators(tmp_path):
    with pytest.raises(PermissionError): run('developer','python -c "print(1)" && echo bad',tmp_path)


def test_python_commands_use_factory_interpreter():
    argv = _argv('python -m pytest -q')
    assert argv[0] == sys.executable
    assert argv[1:] == ['-m', 'pytest', '-q']

def test_flutter_adapter_commands():
    a=FlutterAdapter()
    assert a.install_dependencies()=='flutter pub get'
    assert a.format()=='dart format .'
    assert a.analyze()=='flutter analyze'
    assert a.test()=='flutter test'
    assert a.build()=='flutter build apk --debug'


def test_flutter_adapter_validation_lifecycle_commands():
    a = FlutterAdapter()
    assert a.validation_commands() == [
        ('dependencies', 'flutter pub get'),
        ('format', 'dart format .'),
        ('static_analysis', 'flutter analyze'),
        ('unit_tests', 'flutter test'),
        ('build_validation', 'flutter build apk --debug'),
    ]


def test_real_provider_configuration_uses_ai_timeout_and_base_url():
    from factory.config import Settings
    from factory.providers.registry import build_provider
    s=Settings(__import__('pathlib').Path('db'), __import__('pathlib').Path('ws'), 'INFO', 'openai-compatible', 'model', 'secret', command_timeout=77, api_base_url='https://example.test/v1', ai_timeout=13, mode='real')
    p=build_provider(s)
    assert p.timeout == 13
    assert p.base_url == 'https://example.test/v1'


def test_real_provider_missing_api_key_is_rejected(tmp_path):
    from factory.providers.http import OpenAICompatibleProvider
    import pytest
    with pytest.raises(ValueError, match='API key'):
        OpenAICompatibleProvider('', 'model', 'https://example.test/v1')


def test_http_provider_timeout_and_http_error_are_sanitized(monkeypatch):
    from factory.providers.http import OpenAICompatibleProvider
    import urllib.error
    p=OpenAICompatibleProvider('super-secret-key','model','https://example.test/v1',timeout=1,max_retries=0)
    def fail(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, 'bad', {}, __import__('io').BytesIO(b'Bearer super-secret-key'))
    monkeypatch.setattr('urllib.request.urlopen', fail)
    import pytest
    with pytest.raises(RuntimeError) as exc:
        p.generate('system','prompt')
    assert 'super-secret-key' not in str(exc.value)
    assert '[REDACTED]' in str(exc.value)


def test_structured_response_schema_validation():
    from factory.providers.base import AIProvider, LLMResponse
    class P(AIProvider):
        def generate(self, system, prompt, *, timeout=None): return LLMResponse('{"ok":"wrong"}', 'm')
    import pytest
    with pytest.raises(ValueError, match='must be a boolean'):
        P().generate_json('s','p',{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']})


def test_mock_provider_remains_available():
    from factory.providers.mock import MockProvider
    assert MockProvider().generate_json('s','p',{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']})['ok'] is True


def test_openai_compatible_provider_local_http_smoke(monkeypatch):
    import json
    from factory.providers.http import OpenAICompatibleProvider
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return json.dumps({'choices':[{'message':{'content':'{"ok":true,"message":"local smoke"}'}}], 'model':'local'}).encode()
    def fake_urlopen(req, timeout):
        assert req.full_url.endswith('/chat/completions')
        assert req.headers.get('Authorization') == 'Bearer secret'
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    p=OpenAICompatibleProvider('secret','model','https://example.test/v1',timeout=2,max_retries=0)
    out=p.generate_json('s','p',{'type':'object','properties':{'ok':{'type':'boolean'},'message':{'type':'string'}},'required':['ok','message']})
    assert out == {'ok':True,'message':'local smoke'}
