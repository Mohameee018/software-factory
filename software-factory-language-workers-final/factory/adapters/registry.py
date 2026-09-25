from factory.adapters.flutter import FlutterAdapter
from factory.adapters.python import PythonAdapter
from factory.adapters.node import NodeAdapter
from factory.adapters.java import JavaAdapter
ADAPTERS=[FlutterAdapter(),JavaAdapter(),NodeAdapter(),PythonAdapter()]
def detect(workspace):
    for a in ADAPTERS:
        if a.detect_project(workspace): return a
    return None
def by_name(name): return next((a for a in ADAPTERS if a.name==name),None)
