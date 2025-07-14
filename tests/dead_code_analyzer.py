import ast
import os
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path

class DeadCodeAnalyzer:
    def __init__(self):
        # Для хранения информации внутри файлов
        self.file_exports: Dict[str, Set[str]] = {}  # {filepath: {exported_names}}
        self.file_imports: Dict[str, Dict[str, Set[str]]] = {}  # {filepath: {source_module: {imported_names}}}
        self.defined_functions: Dict[str, Set[str]] = {}  # {filepath: {function_names}}
        self.used_functions: Dict[str, Set[str]] = {}  # {filepath: {function_names}}
        self.defined_classes: Dict[str, Set[str]] = {}  # {filepath: {class_names}}
        self.used_classes: Dict[str, Set[str]] = {}  # {filepath: {class_names}}
        self.defined_variables: Dict[str, Set[str]] = {}  # {filepath: {variable_names}}
        self.used_variables: Dict[str, Set[str]] = {}  # {filepath: {variable_names}}
        self.special_methods = {
            '__init__', '__new__', '__del__', 
            '__str__', '__repr__', '__eq__', 
            '__lt__', '__gt__', '__hash__'
        }

    def analyze_project(self, project_dir: str):
        """Анализирует весь проект, начиная с указанной директории"""
        project_dir = os.path.abspath(project_dir)
        py_files = self._find_py_files(project_dir)
        
        # Первый проход: сбор экспортов и импортов
        for filepath in py_files:
            self._analyze_exports_and_imports(filepath, project_dir)
        
        # Второй проход: анализ использования
        for filepath in py_files:
            self._analyze_usage(filepath)

    def _find_py_files(self, directory: str) -> List[str]:
        """Находит все .py файлы в директории и поддиректориях"""
        py_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    py_files.append(os.path.join(root, file))
        return py_files

    def _analyze_exports_and_imports(self, filepath: str, project_dir: str):
        """Анализирует экспорты и импорты в файле"""
        with open(filepath, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=filepath)
        
        self.file_exports[filepath] = set()
        self.file_imports[filepath] = {}
        self.defined_functions[filepath] = set()
        self.used_functions[filepath] = set()
        self.defined_classes[filepath] = set()
        self.used_classes[filepath] = set()
        self.defined_variables[filepath] = set()
        self.used_variables[filepath] = set()

        for node in ast.walk(tree):
            # Сбор экспортов (функции и классы верхнего уровня)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.parent and not isinstance(node.parent, ast.ClassDef):  # Только функции верхнего уровня
                    self.file_exports[filepath].add(node.name)
                    self.defined_functions[filepath].add(node.name)
            
            elif isinstance(node, ast.ClassDef):
                self.file_exports[filepath].add(node.name)
                self.defined_classes[filepath].add(node.name)
                
                # Специальные методы классов считаем используемыми
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name in self.special_methods:
                            self.used_functions[filepath].add(f"{node.name}.{item.name}")
            
            # Сбор импортов
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    source_module = alias.name
                    imported_name = alias.asname or alias.name
                    if source_module not in self.file_imports[filepath]:
                        self.file_imports[filepath][source_module] = set()
                    self.file_imports[filepath][source_module].add(imported_name)
            
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = node.level  # Уровень относительного импорта
                source_module = self._resolve_relative_import(filepath, module, level, project_dir)
                
                for alias in node.names:
                    imported_name = alias.asname or alias.name
                    full_import = f"{module}.{alias.name}" if module else alias.name
                    
                    if source_module not in self.file_imports[filepath]:
                        self.file_imports[filepath][source_module] = set()
                    self.file_imports[filepath][source_module].add(imported_name)
                    
                    # Если импортируется всё (from module import *)
                    if alias.name == "*":
                        if source_module in self.file_exports:
                            for export in self.file_exports[source_module]:
                                self.file_imports[filepath][source_module].add(export)

    def _resolve_relative_import(self, filepath: str, module: str, level: int, project_dir: str) -> Optional[str]:
        """Преобразует относительный импорт в абсолютный путь"""
        if level == 0:
            return module
        
        current_dir = os.path.dirname(filepath)
        for _ in range(level - 1):
            current_dir = os.path.dirname(current_dir)
        
        if not module:
            module_path = os.path.join(current_dir, "__init__.py")
        else:
            module_path = os.path.join(current_dir, *module.split('.')) + ".py"
        
        # Ищем ближайший существующий файл
        while not os.path.exists(module_path):
            if module_path.endswith("__init__.py"):
                module_path = os.path.join(os.path.dirname(module_path), "__init__.py")
            else:
                parent_dir = os.path.dirname(module_path)
                if parent_dir == os.path.dirname(parent_dir):  # Достигли корня
                    return None
                module_path = os.path.join(os.path.dirname(parent_dir), "__init__.py")
        
        return module_path

    def _analyze_usage(self, filepath: str):
        """Анализирует использование имен в файле"""
        with open(filepath, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=filepath)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self.used_variables[filepath].add(node.id)
            
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.used_functions[filepath].add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        obj_name = node.func.value.id
                        method_name = node.func.attr
                        self.used_functions[filepath].add(f"{obj_name}.{method_name}")

    def _is_name_used_in_other_files(self, filepath: str, name: str) -> bool:
        """Проверяет, используется ли имя в других файлах"""
        for importer, imports in self.file_imports.items():
            if importer == filepath:
                continue
                
            for source_module, imported_names in imports.items():
                if source_module == filepath and name in imported_names:
                    return True
        return False

    def get_unused_code_report(self) -> Dict[str, Dict[str, List[str]]]:
        """Возвращает отчет о неиспользуемом коде"""
        report = {
            "unused_imports": {},
            "unused_functions": {},
            "unused_classes": {},
            "unused_variables": {}
        }
        
        # Неиспользуемые импорты
        for filepath, imports in self.file_imports.items():
            unused_imports = []
            for source_module, imported_names in imports.items():
                for name in imported_names:
                    if name not in self.used_variables[filepath] and not self._is_name_used_in_other_files(source_module, name):
                        unused_imports.append(f"{source_module}:{name}")
            if unused_imports:
                report["unused_imports"][filepath] = unused_imports
        
        # Неиспользуемые функции
        for filepath, functions in self.defined_functions.items():
            unused_functions = []
            for func in functions:
                if (func not in self.used_functions[filepath] and 
                    not self._is_name_used_in_other_files(filepath, func) and
                    not any(f"{cls}.{func}" in self.used_functions[filepath] for cls in self.defined_classes[filepath])):
                    unused_functions.append(func)
            if unused_functions:
                report["unused_functions"][filepath] = unused_functions
        
        # Неиспользуемые классы
        for filepath, classes in self.defined_classes.items():
            unused_classes = []
            for cls in classes:
                if (cls not in self.used_classes[filepath] and 
                    not self._is_name_used_in_other_files(filepath, cls)):
                    unused_classes.append(cls)
            if unused_classes:
                report["unused_classes"][filepath] = unused_classes
        
        # Неиспользуемые переменные
        for filepath, variables in self.defined_variables.items():
            unused_vars = [v for v in variables if v not in self.used_variables[filepath]]
            if unused_vars:
                report["unused_variables"][filepath] = unused_vars
        
        return report

    def save_report_to_file(self, report: Dict[str, Dict[str, List[str]]], output_file: str):
        """Сохраняет отчет в файл"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=== Анализ мертвого кода ===\n\n")
            
            f.write("=== Неиспользуемые импорты ===\n")
            for filepath, imports in report["unused_imports"].items():
                f.write(f"{filepath}:\n")
                for imp in imports:
                    f.write(f"  - {imp}\n")
                f.write("\n")
            
            f.write("\n=== Неиспользуемые функции ===\n")
            for filepath, funcs in report["unused_functions"].items():
                f.write(f"{filepath}:\n")
                for func in funcs:
                    f.write(f"  - {func}\n")
                f.write("\n")
            
            f.write("\n=== Неиспользуемые классы ===\n")
            for filepath, classes in report["unused_classes"].items():
                f.write(f"{filepath}:\n")
                for cls in classes:
                    f.write(f"  - {cls}\n")
                f.write("\n")
            
            f.write("\n=== Неиспользуемые переменные ===\n")
            for filepath, vars in report["unused_variables"].items():
                f.write(f"{filepath}:\n")
                for var in vars:
                    f.write(f"  - {var}\n")
                f.write("\n")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Анализатор мертвого кода Python')
    parser.add_argument('project_dir', help='Директория проекта для анализа')
    parser.add_argument('--output', default='dead_code_report.txt', help='Файл для сохранения отчета')
    args = parser.parse_args()
    
    analyzer = DeadCodeAnalyzer()
    analyzer.analyze_project(args.project_dir)
    report = analyzer.get_unused_code_report()
    analyzer.save_report_to_file(report, args.output)
    
    print(f"Анализ завершен. Результат сохранен в {args.output}")