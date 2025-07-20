import os
import ast
import re
import json
from typing import List, Dict, Set, Optional, Union


class DeadCodeFinder:
    """Анализатор мертвого кода в Python-проектах."""

    def __init__(self, root_dir: str, exclude_dirs: Optional[List[str]] = None):
        """
        Инициализация анализатора.

        :param root_dir: Корневая директория проекта.
        :param exclude_dirs: Список директорий для исключения (по умолчанию: __pycache__, venv, tests).
        """
        self.root_dir = root_dir
        self.exclude_dirs = exclude_dirs or ["__pycache__", "venv", "tests"]
        self.dead_code_report: Dict[str, Dict[str, List[str]]] = {}

    def get_py_files(self) -> List[str]:
        """Рекурсивно находит все .py-файлы в директории, исключая указанные папки."""
        py_files = []
        for root, dirs, files in os.walk(self.root_dir):
            # Исключаем ненужные директории
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for file in files:
                if file.endswith(".py"):
                    py_files.append(os.path.join(root, file))
        return py_files

    def parse_file(self, file_path: str) -> Optional[ast.Module]:
        """Парсит Python-файл в AST (абстрактное синтаксическое дерево)."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return ast.parse(f.read(), filename=file_path)
        except Exception as e:
            print(f"Ошибка при парсинге {file_path}: {e}")
            return None

    def _get_defined_functions(self, node: ast.AST) -> Set[str]:
        """Возвращает множество имен всех объявленных функций/методов в AST."""
        functions = set()
        for item in ast.walk(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.add(item.name)
        return functions

    def _get_called_functions(self, node: ast.AST) -> Set[str]:
        """Возвращает множество имен всех вызываемых функций в AST."""
        calls = set()
        for item in ast.walk(node):
            if isinstance(item, ast.Call) and isinstance(item.func, ast.Name):
                calls.add(item.func.id)
        return calls

    def find_unused_functions(self, ast_tree: ast.Module) -> List[str]:
        """Находит функции, которые объявлены, но нигде не вызываются."""
        defined = self._get_defined_functions(ast_tree)
        called = self._get_called_functions(ast_tree)
        return sorted(defined - called)

    def find_todo_comments(self, file_path: str) -> List[str]:
        """Ищет комментарии с пометкой 'мертвый код' или 'dead code'."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        pattern = r"#.*(TODO|FIXME).*мертвый код|dead code"
        return re.findall(pattern, content, re.IGNORECASE)

    def analyze_file(self, file_path: str):
        """Анализирует файл на наличие мертвого кода."""
        ast_tree = self.parse_file(file_path)
        if not ast_tree:
            return

        unused_funcs = self.find_unused_functions(ast_tree)
        todo_comments = self.find_todo_comments(file_path)

        if unused_funcs or todo_comments:
            self.dead_code_report[file_path] = {
                "unused_functions": unused_funcs,
                "todo_comments": todo_comments,
            }

    def generate_report(self, output_format: str = "console") -> Union[None, str]:
        """Генерирует отчет в консоли или JSON."""
        if not self.dead_code_report:
            print("Мертвый код не обнаружен.")
            return None

        if output_format == "json":
            report = json.dumps(self.dead_code_report, indent=4, ensure_ascii=False)
            with open("dead_code_report.json", "w", encoding="utf-8") as f:
                f.write(report)
            return "Отчет сохранен в dead_code_report.json"

        print("\n=== Найден мертвый код ===")
        for file, issues in self.dead_code_report.items():
            print(f"\nФайл: {file}")
            if issues["unused_functions"]:
                print("  Неиспользуемые функции:")
                for func in issues["unused_functions"]:
                    print(f"    - {func}")
            if issues["todo_comments"]:
                print("  TODO-комментарии:")
                for comment in issues["todo_comments"]:
                    print(f"    - {comment.strip()}")

    def run_analysis(self):
        """Запускает полный анализ проекта."""
        py_files = self.get_py_files()
        for file in py_files:
            self.analyze_file(file)
        return self.dead_code_report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Поиск мертвого кода в Python-проекте.")
    parser.add_argument("--path", help="Путь к проекту", default=".")
    parser.add_argument("--format", help="Формат отчета (console/json)", default="console")
    args = parser.parse_args()

    analyzer = DeadCodeFinder(args.path)
    analyzer.run_analysis()
    analyzer.generate_report(args.format)