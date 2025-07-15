import ast
import os
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path

class DeadCodeAnalyzer:
    def __init__(self):
        self.file_exports: Dict[str, Set[str]] = {}
        self.file_imports: Dict[str, Dict[str, Set[str]]] = {}
        self.defined_functions: Dict[str, Dict[str, Tuple[int, int]]] = {}  # {filepath: {func_name: (lineno, col_offset)}}
        self.used_functions: Dict[str, Set[str]] = {}
        self.defined_classes: Dict[str, Dict[str, Tuple[int, int]]] = {}
        self.used_classes: Dict[str, Set[str]] = {}
        self.defined_methods: Dict[str, Dict[str, Dict[str, Tuple[int, int]]]] = {}  # {filepath: {class_name: {method_name: (lineno, col_offset)}}}
        self.used_methods: Dict[str, Dict[str, Set[str]]] = {}  # {filepath: {class_name: {method_name}}}
        self.special_methods = {
            '__init__', '__new__', '__del__', '__str__', '__repr__', 
            '__eq__', '__lt__', '__gt__', '__hash__', '__call__'
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

    def _add_parent_links(self, node: ast.AST, parent: Optional[ast.AST] = None):
        """Добавляет ссылки на родительские узлы в AST"""
        node.parent = parent  # type: ignore
        for child in ast.iter_child_nodes(node):
            self._add_parent_links(child, node)

    def _analyze_exports_and_imports(self, filepath: str, project_dir: str):
        """Анализирует экспорты и импорты в файле"""
        with open(filepath, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=filepath)

        self._add_parent_links(tree)
        
        self.file_exports[filepath] = set()
        self.file_imports[filepath] = {}
        self.defined_functions[filepath] = {}
        self.used_functions[filepath] = set()
        self.defined_classes[filepath] = {}
        self.used_classes[filepath] = set()
        self.defined_methods[filepath] = {}
        self.used_methods[filepath] = {}

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not isinstance(node.parent, ast.ClassDef):  # Функции верхнего уровня
                    self.file_exports[filepath].add(node.name)
                    self.defined_functions[filepath][node.name] = (node.lineno, node.col_offset)
                else:  # Методы классов
                    class_name = node.parent.name  # type: ignore
                    if class_name not in self.defined_methods[filepath]:
                        self.defined_methods[filepath][class_name] = {}
                    self.defined_methods[filepath][class_name][node.name] = (node.lineno, node.col_offset)

            elif isinstance(node, ast.ClassDef):
                self.file_exports[filepath].add(node.name)
                self.defined_classes[filepath][node.name] = (node.lineno, node.col_offset)
                self.defined_methods[filepath][node.name] = {}

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    source_module = alias.name
                    imported_name = alias.asname or alias.name
                    if source_module not in self.file_imports[filepath]:
                        self.file_imports[filepath][source_module] = set()
                    self.file_imports[filepath][source_module].add(imported_name)

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = node.level
                source_module = self._resolve_relative_import(filepath, module, level, project_dir)

                for alias in node.names:
                    imported_name = alias.asname or alias.name
                    if source_module not in self.file_imports[filepath]:
                        self.file_imports[filepath][source_module] = set()
                    self.file_imports[filepath][source_module].add(imported_name)

                    if alias.name == "*" and source_module in self.file_exports:
                        for export in self.file_exports[source_module]:
                            self.file_imports[filepath][source_module].add(export)

    def _analyze_usage(self, filepath: str):
        """Анализирует использование имен в файле"""
        with open(filepath, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=filepath)

        self._add_parent_links(tree)

        for node in ast.walk(tree):
            # Использование функций и методов
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.used_functions[filepath].add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        obj_name = node.func.value.id
                        method_name = node.func.attr
                        if obj_name in self.defined_classes[filepath]:
                            if obj_name not in self.used_methods[filepath]:
                                self.used_methods[filepath][obj_name] = set()
                            self.used_methods[filepath][obj_name].add(method_name)
                        else:
                            self.used_functions[filepath].add(f"{obj_name}.{method_name}")

            # Использование классов
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in self.defined_classes[filepath]:
                    self.used_classes[filepath].add(node.id)

    def _is_name_used_in_other_files(self, filepath: str, name: str) -> bool:
        """Проверяет, используется ли имя в других файлах"""
        for importer, imports in self.file_imports.items():
            if importer == filepath:
                continue
                
            for source_module, imported_names in imports.items():
                if source_module == filepath and name in imported_names:
                    return True
        return False

    def _is_method_used(self, filepath: str, class_name: str, method_name: str) -> bool:
        """Проверяет, используется ли метод"""
        # Специальные методы считаем используемыми
        if method_name in self.special_methods:
            return True
            
        # Проверяем использование внутри файла
        if (filepath in self.used_methods and 
            class_name in self.used_methods[filepath] and 
            method_name in self.used_methods[filepath][class_name]):
            return True
            
        # Проверяем использование в других файлах
        full_name = f"{class_name}.{method_name}"
        return self._is_name_used_in_other_files(filepath, full_name)

    def get_unused_code_report(self) -> Dict[str, Dict[str, List[Tuple[str, int, int]]]]:
        '''Возвращает отчет о неиспользуемом коде с указанием позиции в коде'''

        report = {
            "unused_functions": {},
            "unused_methods": {},
            "unused_classes": {},
        }
        
        # Неиспользуемые функции
        for filepath, functions in self.defined_functions.items():
            unused = []
            for func, (lineno, col_offset) in functions.items():
                if (func not in self.used_functions[filepath] and 
                    not self._is_name_used_in_other_files(filepath, func)):
                    unused.append((func, lineno, col_offset))
            if unused:
                report["unused_functions"][filepath] = unused
        
        # Неиспользуемые методы
        for filepath, classes in self.defined_methods.items():
            unused_methods = {}
            for class_name, methods in classes.items():
                unused = []
                for method, (lineno, col_offset) in methods.items():
                    if not self._is_method_used(filepath, class_name, method):
                        unused.append((method, lineno, col_offset))
                if unused:
                    unused_methods[class_name] = unused
            if unused_methods:
                report["unused_methods"][filepath] = unused_methods
        
        # Неиспользуемые классы
        for filepath, classes in self.defined_classes.items():
            unused = []
            for cls, (lineno, col_offset) in classes.items():
                if (cls not in self.used_classes[filepath] and 
                    not self._is_name_used_in_other_files(filepath, cls)):
                    unused.append((cls, lineno, col_offset))
            if unused:
                report["unused_classes"][filepath] = unused
        
        return report

    def _resolve_relative_import(self, filepath: str, module: str, level: int, project_dir: str) -> str:
        """Преобразует относительный импорт в абсолютный путь к модулю"""
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
                    return module  # Возвращаем исходное имя модуля, если не нашли файл
                module_path = os.path.join(os.path.dirname(parent_dir), "__init__.py")

        return module_path

    def save_report_to_file(self, report: Dict[str, Dict[str, List[Tuple[str, int, int]]]], output_file: str):
        """Сохраняет отчет в файл с указанием позиции в коде"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=== Анализ мертвого кода ===\n\n")
            
            f.write("=== Неиспользуемые функции ===\n")
            for filepath, funcs in report["unused_functions"].items():
                f.write(f"{filepath}:\n")
                for func, line, col in funcs:
                    f.write(f"  - {func} (строка {line}, позиция {col})\n")
                f.write("\n")
            
            f.write("\n=== Неиспользуемые методы ===\n")
            for filepath, classes in report["unused_methods"].items():
                f.write(f"{filepath}:\n")
                for class_name, methods in classes.items():
                    f.write(f"  Класс {class_name}:\n")
                    for method, line, col in methods:
                        f.write(f"    - {method} (строка {line}, позиция {col})\n")
                f.write("\n")
            
            f.write("\n=== Неиспользуемые классы ===\n")
            for filepath, classes in report["unused_classes"].items():
                f.write(f"{filepath}:\n")
                for cls, line, col in classes:
                    f.write(f"  - {cls} (строка {line}, позиция {col})\n")
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