import ast
import os
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path
import argparse


class DeadCodeAnalyzer:
    def __init__(self):
        self.file_exports: Dict[str, Set[str]] = {}
        self.file_imports: Dict[str, Dict[str, Set[str]]] = {}
        self.defined_functions: Dict[str, Dict[str, Tuple[int, int]]] = {}
        self.used_functions: Dict[str, Set[str]] = {}
        self.defined_classes: Dict[str, Dict[str, Tuple[int, int]]] = {}
        self.used_classes: Dict[str, Set[str]] = {}
        self.defined_methods: Dict[str, Dict[str, Dict[str, Tuple[int, int]]]] = {}
        self.used_methods: Dict[str, Dict[str, Set[str]]] = {}
        self.todo_comments: Dict[str, Dict[str, List[Tuple[str, int]]]] = {}

        # Специальные методы, которые считаются используемыми по умолчанию
        self.special_methods = {
            '__init__', '__new__', '__del__', '__str__', '__repr__',
            '__eq__', '__lt__', '__gt__', '__hash__', '__call__',
            # Qt методы
            'event', 'mousePressEvent', 'mouseMoveEvent', 'mouseReleaseEvent',
            'keyPressEvent', 'paintEvent', 'closeEvent',
            # Qt сигналы
            'clicked', 'activated', 'textChanged', 'buttonsChanged',
            # Общие методы
            'initUI', 'setupUi', 'createConnections'
        }

    def analyze_project(self, project_dir: str):
        """Анализирует весь проект на наличие мертвого кода."""
        project_dir = os.path.abspath(project_dir)
        py_files = self._find_py_files(project_dir)

        # Первый проход: сбор экспортов, импортов и TODO комментариев
        for filepath in py_files:
            self._analyze_exports_and_imports(filepath, project_dir)
            self._find_todo_comments(filepath)

        # Второй проход: анализ использования
        for filepath in py_files:
            self._analyze_usage(filepath)

    def _find_todo_comments(self, filepath: str):
        """Находит все TODO комментарии в файле."""
        with open(filepath, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        self.todo_comments[filepath] = {}

        for i, line in enumerate(lines, 1):
            if 'TODO' in line:
                # Извлекаем имя метода/функции из комментария TODO
                parts = line.split('TODO')
                if len(parts) > 1:
                    comment = parts[1].strip()
                    if 'мертвый код' in comment or 'dead code' in comment:
                        # Пытаемся найти имя метода в строке
                        method_name = self._extract_method_name_from_comment(comment)
                        if method_name:
                            if 'methods' not in self.todo_comments[filepath]:
                                self.todo_comments[filepath]['methods'] = []
                            self.todo_comments[filepath]['methods'].append((method_name, i))

    def _extract_method_name_from_comment(self, comment: str) -> Optional[str]:
        """Извлекает имя метода из комментария TODO."""
        # Пример: "TODO мертвый код возможно удалить"
        # Ищем шаблоны типа "метод X", "функция Y"
        if 'метод' in comment:
            parts = comment.split('метод')
            if len(parts) > 1:
                return parts[1].split()[0].strip()
        elif 'method' in comment:
            parts = comment.split('method')
            if len(parts) > 1:
                return parts[1].split()[0].strip()
        return None

    def _find_py_files(self, directory: str) -> List[str]:
        """Рекурсивно находит все .py файлы в директории."""
        py_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    py_files.append(os.path.join(root, file))
        return py_files

    def _add_parent_links(self, node: ast.AST, parent: Optional[ast.AST] = None):
        """Добавляет ссылки на родительские узлы в AST."""
        node.parent = parent  # type: ignore
        for child in ast.iter_child_nodes(node):
            self._add_parent_links(child, node)

    def _analyze_exports_and_imports(self, filepath: str, project_dir: str):
        """Анализирует экспорты и импорты в файле."""
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
                if not isinstance(node.parent, ast.ClassDef):
                    self.file_exports[filepath].add(node.name)
                    self.defined_functions[filepath][node.name] = (node.lineno, node.col_offset)
                else:
                    class_name = node.parent.name  # type: ignore

                    if class_name not in self.defined_methods[filepath]:
                        self.defined_methods[filepath][class_name] = {}
                    self.defined_methods[filepath][class_name][node.name] = (node.lineno, node.col_offset)

                    # Если метод имеет декораторы, считаем его используемым
                    if node.decorator_list:
                        if class_name not in self.used_methods[filepath]:
                            self.used_methods[filepath][class_name] = set()
                        self.used_methods[filepath][class_name].add(node.name)

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
        """Анализирует использование функций, классов и методов в файле."""
        with open(filepath, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=filepath)

        self._add_parent_links(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'connect':
                    self._register_qt_connection(node, filepath)
                    continue

                if isinstance(node.func, ast.Name):
                    self.used_functions[filepath].add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        obj_name = node.func.value.id
                        method_name = node.func.attr

                        if obj_name == 'self':
                            current = node
                            while hasattr(current, 'parent'):
                                current = current.parent
                                if isinstance(current, ast.ClassDef):
                                    if current.name not in self.used_methods[filepath]:
                                        self.used_methods[filepath][current.name] = set()
                                    self.used_methods[filepath][current.name].add(method_name)
                                    break
                            continue

                        if obj_name in self.defined_classes[filepath]:
                            if obj_name not in self.used_methods[filepath]:
                                self.used_methods[filepath][obj_name] = set()
                            self.used_methods[filepath][obj_name].add(method_name)
                        else:
                            self.used_functions[filepath].add(f"{obj_name}.{method_name}")

            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in self.defined_classes[filepath]:
                    self.used_classes[filepath].add(node.id)

    def _register_qt_connection(self, node, filepath):
        """Регистрирует Qt соединения сигнал-слот."""
        try:
            if node.args and isinstance(node.args[0], ast.Name):
                slot_name = node.args[0].id

                current = node
                while hasattr(current, 'parent'):
                    current = current.parent
                    if isinstance(current, ast.ClassDef):
                        if filepath not in self.used_methods:
                            self.used_methods[filepath] = {}
                        if current.name not in self.used_methods[filepath]:
                            self.used_methods[filepath][current.name] = set()
                        self.used_methods[filepath][current.name].add(slot_name)
                        break
        except AttributeError:
            pass

    def get_unused_code_report(self) -> Dict[str, Dict[str, List[Tuple[str, int, int]]]]:
        """Формирует отчет о неиспользуемом коде."""
        report = {
            "unused_functions": {},
            "unused_methods": {},
            "unused_classes": {},
            "todo_comments": self.todo_comments
        }

        # Анализ неиспользуемых функций
        for filepath, functions in self.defined_functions.items():
            unused = []
            for func, (line, col) in functions.items():
                if(func not in self.used_functions[filepath] and not self._is_name_used_in_other_files(filepath, func)):
                    unused.append((func, line, col))
                    if unused:
                        report["unused_functions"][filepath] = unused

        # Анализ неиспользуемых методов
        for filepath, classes in self.defined_methods.items():
            unused_methods = {}
            for class_name, methods in classes.items():
                unused = []
                for method, (line, col) in methods.items():
                    if not self._is_method_used(filepath, class_name, method):
                        unused.append((method, line, col))
                if unused:
                    unused_methods[class_name] = unused
            if unused_methods:
                report["unused_methods"][filepath] = unused_methods

        # Анализ неиспользуемых классов
        for filepath, classes in self.defined_classes.items():
            unused = []
        for cls, (line, col) in classes.items():
            if(cls not in self.used_classes[filepath] and
                not self._is_name_used_in_other_files(filepath, cls)):
                unused.append((cls, line, col))
            if unused:
                report["unused_classes"][filepath] = unused

        return report

    def _is_method_used(self, filepath: str, class_name: str, method_name: str) -> bool:
        """Проверяет, используется ли метод."""
        if method_name in self.special_methods:
            return True

        # Проверяем TODO комментарии
        if filepath in self.todo_comments and 'methods' in self.todo_comments[filepath]:
            for name, _ in self.todo_comments[filepath]['methods']:
                if name == method_name:
                    return False  # Помечен как мертвый код

        if (filepath in self.used_methods and
                class_name in self.used_methods[filepath] and
                method_name in self.used_methods[filepath][class_name]):
            return True

        full_name = f"{class_name}.{method_name}"
        return self._is_name_used_in_other_files(filepath, full_name)

    def _is_name_used_in_other_files(self, filepath: str, name: str) -> bool:
        """Проверяет, используется ли имя в других файлах."""
        for importer, imports in self.file_imports.items():
            if importer == filepath:
                continue
            for source_module, imported_names in imports.items():
                if source_module == filepath and name in imported_names:
                    return True
        return False

    def _resolve_relative_import(self, filepath: str, module: str, level: int, project_dir: str) -> str:
        """Преобразует относительный импорт в абсолютный путь."""
        if level == 0:
            return module

        current_dir = os.path.dirname(filepath)
        for _ in range(level - 1):
            current_dir = os.path.dirname(current_dir)

        if not module:
            module_path = os.path.join(current_dir, "__init__.py")
        else:
            module_path = os.path.join(current_dir, *module.split('.')) + ".py"

        while not os.path.exists(module_path):
            if module_path.endswith("__init__.py"):
                module_path = os.path.join(os.path.dirname(module_path), "__init__.py")
            else:
                parent_dir = os.path.dirname(module_path)
                if parent_dir == os.path.dirname(parent_dir):
                    return module
                module_path = os.path.join(os.path.dirname(parent_dir), "__init__.py")

        return module_path

    def save_report_to_file(self, report: Dict[str, Dict[str, List[Tuple[str, int, int]]]], output_file: str):
        """Сохраняет отчет в файл."""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=== Анализ мертвого кода ===\n\n")
            # Отчет по TODO комментариям
            f.write("=== Методы, помеченные как мертвый код ===\n")
            for filepath, data in report["todo_comments"].items():
                if 'methods' in data and data['methods']:
                    f.write(f"{filepath}:\n")
                    for method, line in data['methods']:
                        f.write(f"  - {method} (помечен TODO на строке {line})\n")
                f.write("\n")

        # Остальные разделы отчета...
        f.write("\n=== Неиспользуемые функции ===\n")
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


        parser = argparse.ArgumentParser(description='Анализатор мертвого кода Python')
        parser.add_argument('project_dir', help='Директория проекта для анализа')
        parser.add_argument('--output', default='dead_code_report.txt', help='Файл для сохранения отчета')
        args = parser.parse_args()

        analyzer = DeadCodeAnalyzer()
        analyzer.analyze_project(args.project_dir)
        report = analyzer.get_unused_code_report()
        analyzer.save_report_to_file(report, args.output)

        print(f"Анализ завершен. Результат сохранен в {args.output}")