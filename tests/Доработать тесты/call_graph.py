import ast
import os
import graphviz
from typing import Dict, List, Set, Tuple

class CallGraphAnalyzer:
    def __init__(self):
        self.graph = {}  # {caller: {callees}}
        self.current_function = None
        self.imports = {}  # {module: {alias: real_name}}
        self.class_methods = {}  # {class_name: {method_name}}

    def analyze_file(self, filepath: str):
        with open(filepath, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=filepath)
        
        # Сначала собираем все импорты
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if filepath not in self.imports:
                        self.imports[filepath] = {}
                    self.imports[filepath][alias.name] = alias.name
            
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if filepath not in self.imports:
                        self.imports[filepath] = {}
                    self.imports[filepath][alias.name] = f"{module}.{alias.name}"
            
            elif isinstance(node, ast.ClassDef):
                self._analyze_class(node, filepath)
        
        # Затем анализируем вызовы
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self.current_function = f"{filepath}:{node.name}"
                self.graph[self.current_function] = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        self._analyze_call(child, filepath)
                self.current_function = None

    def _analyze_class(self, node: ast.ClassDef, filepath: str):
        class_name = node.name
        full_class_name = f"{filepath}:{class_name}"
        self.class_methods[full_class_name] = set()
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_name = item.name
                self.class_methods[full_class_name].add(method_name)
                full_method_name = f"{full_class_name}.{method_name}"
                self.graph[full_method_name] = set()
                
                # Анализируем вызовы внутри метода
                self.current_function = full_method_name
                for child in ast.walk(item):
                    if isinstance(child, ast.Call):
                        self._analyze_call(child, filepath)
                self.current_function = None

    def _analyze_call(self, node: ast.Call, filepath: str):
        if not self.current_function:
            return
            
        if isinstance(node.func, ast.Name):
            # Простой вызов функции (func())
            callee = node.func.id
            self.graph[self.current_function].add(f"{filepath}:{callee}")
            
        elif isinstance(node.func, ast.Attribute):
            # Вызов метода (obj.method())
            if isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id
                method_name = node.func.attr
                
                # Проверяем, является ли это вызовом метода класса
                for class_name, methods in self.class_methods.items():
                    if method_name in methods:
                        self.graph[self.current_function].add(f"{class_name}.{method_name}")
                        return
                
                # Или вызовом импортированной функции
                if filepath in self.imports and obj_name in self.imports[filepath]:
                    imported = self.imports[filepath][obj_name]
                    self.graph[self.current_function].add(f"{imported}.{method_name}")

    def analyze_project(self, project_dir: str):
        for root, _, files in os.walk(project_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    self.analyze_file(filepath)

    def visualize(self, output_file: str = "call_graph"):
        dot = graphviz.Digraph(comment='Call Graph', format='png')
        
        # Добавляем узлы
        for node in self.graph:
            dot.node(node, node.split(':')[-1])
        
        # Добавляем рёбра
        for caller, callees in self.graph.items():
            for callee in callees:
                dot.edge(caller, callee)
        
        # Сохраняем граф
        dot.render(output_file, view=True)

if __name__ == "__main__":
    analyzer = CallGraphAnalyzer()
    analyzer.analyze_project(".")  # Анализируем текущую директорию
    analyzer.visualize()  # Создаём визуализацию графа