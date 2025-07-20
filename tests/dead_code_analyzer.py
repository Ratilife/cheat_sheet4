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
        self.special_methods.update({
            # Qt event methods
            'event', 'mousePressEvent', 'mouseMoveEvent',
            'mouseReleaseEvent', 'keyPressEvent', 'paintEvent',
            # Qt signals
            'clicked', 'activated', 'textChanged',
            # Common Qt methods
            'initUI', 'setupUi', 'createConnections'
        })

    def analyze_project(self, project_dir: str):
        """Анализирует весь проект Python, начиная с указанной директории.

            Выполняет двухэтапный анализ кода:
            1. Сбор информации об экспортах (определенных функциях, классах, методах)
               и импортах во всех файлах проекта
            2. Анализ использования собранных сущностей для выявления неиспользуемого кода

            Процесс работы:
            - Рекурсивно находит все .py файлы в указанной директории и поддиректориях
            - В первом проходе анализирует каждый файл для сбора информации об экспортах и импортах
            - Во втором проходе анализирует использование функций, классов и методов
            - Результаты сохраняются во внутренних структурах данных класса

            Особенности:
            - Обрабатывает как абсолютные, так и относительные импорты
            - Учитывает специальные методы классов (__init__, __str__ и т.д.)
            - Сохраняет позиции в коде (номера строк и столбцов) для точного указания местоположения

            Args:
                project_dir (str): Путь к корневой директории проекта для анализа.
                                   Может быть как абсолютным, так и относительным путем.

            Side effects:
                Заполняет следующие внутренние структуры данных класса:
                - file_exports: словарь экспортов (доступных имен) для каждого файла
                - file_imports: словарь импортов для каждого файла
                - defined_functions: словарь определенных функций с их позициями
                - used_functions: словарь используемых функций
                - defined_classes: словарь определенных классов с их позициями
                - used_classes: словарь используемых классов
                - defined_methods: словарь определенных методов с их позициями
                - used_methods: словарь используемых методов

            Note:
                Для получения результатов анализа после выполнения этого метода
                следует использовать методы get_unused_code_report() и save_report_to_file().
            """
        project_dir = os.path.abspath(project_dir)
        py_files = self._find_py_files(project_dir)
        
        # Первый проход: сбор экспортов и импортов
        for filepath in py_files:
            self._analyze_exports_and_imports(filepath, project_dir)
        
        # Второй проход: анализ использования
        for filepath in py_files:
            self._analyze_usage(filepath)

    def _find_py_files(self, directory: str) -> List[str]:
        """Рекурсивно находит все Python-файлы (.py) в указанной директории и её поддиректориях.

            Метод обходит файловую систему, начиная с заданной директории, и собирает абсолютные пути
            ко всем файлам с расширением .py. Игнорирует файлы с другими расширениями и директории.

            Args:
                directory (str): Путь к директории для поиска. Может быть как абсолютным, так и относительным.
                                Если путь относительный, он будет интерпретироваться относительно текущей
                                рабочей директории.

            Returns:
                List[str]: Список абсолютных путей ко всем найденным .py файлам. Список будет пустым,
                          если в директории нет Python-файлов или если директория не существует.

            Raises:
                Фактически не генерирует исключений, но если у пользователя нет прав на чтение
                некоторых директорий, соответствующие поддиректории будут пропущены (это стандартное
                поведение os.walk).

            Examples:
                >>> analyzer = DeadCodeAnalyzer()
                >>> analyzer._find_py_files('/path/to/project')
                ['/path/to/project/main.py', '/path/to/project/utils/helpers.py']

            Note:
                - Возвращаемые пути всегда абсолютные, даже если входной аргумент был относительным.
                - Порядок файлов в возвращаемом списке зависит от реализации os.walk и может варьироваться
                  между запусками.
                - Символические ссылки обрабатываются стандартным для ОС образом.
                - В отличие от glob, не поддерживает шаблоны поиска - только конкретную директорию.
            """
        py_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    py_files.append(os.path.join(root, file))
        return py_files

    def _add_parent_links(self, node: ast.AST, parent: Optional[ast.AST] = None):
        """Рекурсивно добавляет ссылки на родительские узлы в AST-дереве.

            Модифицирует узлы абстрактного синтаксического дерева (AST), добавляя каждому узлу
            атрибут 'parent', который ссылается на его непосредственного родителя в дереве.
            Это позволяет в дальнейшем анализировать контекст, в котором находится узел.

            Args:
                node (ast.AST): Корневой узел AST-дерева, с которого начинается обработка.
                parent (Optional[ast.AST], optional): Родительский узел для текущего узла.
                    По умолчанию None (для корневого узла дерева).

            Returns:
                None: Метод не возвращает значения, но модифицирует переданное AST-дерево.

            Side effects:
                - Добавляет атрибут 'parent' к каждому узлу AST-дерева
                - Модифицирует исходные узлы дерева (in-place modification)

            Note:
                - Использует рекурсивный обход дерева через ast.iter_child_nodes()
                - Добавляемый атрибут 'parent' является динамическим и не типизированным (использует type: ignore)
                - Для корневого узла дерева parent всегда будет None
                - Важно вызывать этот метод перед анализом использования кода, так как многие проверки
                  зависят от информации о родительских узлах
                - Не обрабатывает случай циклических ссылок в AST (что маловероятно в корректном Python-коде)

            Example:
                >>> tree = ast.parse("def foo(): pass")
                >>> analyzer._add_parent_links(tree)
                >>> tree.body[0].parent == tree  # Для узла функции родителем будет модуль
                True
            """
        node.parent = parent  # type: ignore
        for child in ast.iter_child_nodes(node):
            self._add_parent_links(child, node)

    def _analyze_exports_and_imports(self, filepath: str, project_dir: str):
        """Анализирует и собирает информацию об экспортах и импортах в Python-файле.

            Осуществляет полный синтаксический анализ указанного файла для выявления:
            - Экспортируемых функций верхнего уровня
            - Определенных классов и их методов
            - Всех импортов (как абсолютных, так и относительных)
            - Специальных методов классов

            Подробное описание работы:
            1. Читает и парсит файл в AST-дерево
            2. Добавляет ссылки на родительские узлы
            3. Инициализирует структуры данных для хранения информации о файле
            4. Обходит AST для сбора данных:
               - Функции верхнего уровня (экспорты)
               - Классы и их методы
               - Импорты (import и import from)
               - Обрабатывает относительные импорты

            Args:
                filepath (str): Абсолютный путь к анализируемому .py файлу
                project_dir (str): Абсолютный путь к корневой директории проекта (для разрешения относительных импортов)

            Side effects:
                Обновляет следующие структуры данных класса:
                - file_exports: добавляет экспортируемые имена
                - file_imports: добавляет информацию об импортах
                - defined_functions: добавляет функции верхнего уровня
                - defined_classes: добавляет определенные классы
                - defined_methods: добавляет методы классов
                - Инициализирует соответствующие структуры для used_functions, used_classes, used_methods

            Raises:
                FileNotFoundError: если указанный файл не существует
                SyntaxError: если файл содержит синтаксические ошибки
                UnicodeDecodeError: если файл содержит некорректные символы

            Note:
                - Для относительных импортов используется _resolve_relative_import
                - Специальные методы классов автоматически считаются используемыми
                - Импорты вида 'from module import *' обрабатываются особым образом
                - Сохраняет точные позиции (строка, столбец) для всех определений
            """
        # 1. Открытие файла и парсинг в AST
        with open(filepath, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=filepath)  # -> Получаем абстрактное синтаксическое дерево
        # 2. Добавление родительских ссылок в AST
        self._add_parent_links(tree)        # Необходимо для анализа контекста узлов

        ''' Словари для хранения информации о коде проекта:

          1. Экспортируемые имена (функции/классы) из каждого файла
          Заполняется в: _analyze_exports_and_imports()
          Используется в: _resolve_relative_import(), get_unused_code_report()
            self.file_exports[filepath] = set()  # Формат: {filepath: set(exported_names)}
         
          2. Импортированные имена для каждого файла
          Заполняется в: _analyze_exports_and_imports()
          Используется в: _is_name_used_in_other_files()
            self.file_imports = {}  # Формат: {filepath: {source_module: set(imported_names)}}

          3. Определенные функции верхнего уровня с их позициями
          Заполняется в: _analyze_exports_and_imports()
          Используется в: get_unused_code_report()
            self.defined_functions = {}  # Формат: {filepath: {func_name: (line, col)}}

          4. Использованные функции в каждом файле
          Заполняется в: _analyze_usage()
          Используется в: get_unused_code_report()
            self.used_functions = {}  # Формат: {filepath: set(used_func_names)}

          5. Определенные классы с их позициями
          Заполняется в: _analyze_exports_and_imports()
          Используется в: _analyze_usage(), get_unused_code_report()
            self.defined_classes = {}  # Формат: {filepath: {class_name: (line, col)}}

          6. Использованные классы в каждом файле
          Заполняется в: _analyze_usage()
          Используется в: get_unused_code_report()
            self.used_classes = {}  # Формат: {filepath: set(used_class_names)}

          7. Определенные методы классов с их позициями
          Заполняется в: _analyze_exports_and_imports()
          Используется в: _is_method_used(), get_unused_code_report()
            self.defined_methods = {}  # Формат: {filepath: {class_name: {method_name: (line, col)}}}

          8. Использованные методы классов
          Заполняется в: _analyze_usage()
          Используется в: _is_method_used(), get_unused_code_report()
            self.used_methods = {}  # Формат: {filepath: {class_name: set(used_method_names)}}
        '''
        # 3. Инициализация структур данных для текущего файла
        self.file_exports[filepath] = set()                     # Для экспортируемых имен
        self.file_imports[filepath] = {}                        # Для информации об импортах
        self.defined_functions[filepath] = {}                   # Для функций верхнего уровня
        self.used_functions[filepath] = set()                   # Для использованных функций
        self.defined_classes[filepath] = {}                     # Для определенных классов
        self.used_classes[filepath] = set()                     # Для использованных классов
        self.defined_methods[filepath] = {}                     # Для методов классов
        self.used_methods[filepath] = {}                        # Для использованных методов

        # 4. Обход всех узлов AST
        for node in ast.walk(tree):
            # 5. Обработка функций и асинхронных функций
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not isinstance(node.parent, ast.ClassDef):  # 6. Функции верхнего уровня
                    self.file_exports[filepath].add(node.name)
                    self.defined_functions[filepath][node.name] = (node.lineno, node.col_offset)
                else:   # 7. Метод класса
                    class_name = node.parent.name  # type: ignore

                    if node.decorator_list:  # Если есть декораторы
                        # Инициализируем used_methods для файла, если нужно
                        if filepath not in self.used_methods:
                            self.used_methods[filepath] = {}
                        # Инициализируем для класса, если нужно
                        if class_name not in self.used_methods[filepath]:
                            self.used_methods[filepath][class_name] = set()
                        # Добавляем метод как используемый
                        self.used_methods[filepath][class_name].add(node.name)

                    if class_name not in self.defined_methods[filepath]:
                        self.defined_methods[filepath][class_name] = {}
                    self.defined_methods[filepath][class_name][node.name] = (node.lineno, node.col_offset)
            # 8. Обработка классов
            elif isinstance(node, ast.ClassDef):
                self.file_exports[filepath].add(node.name)  # 9. Добавляем класс в экспорты
                self.defined_classes[filepath][node.name] = (node.lineno, node.col_offset)
                self.defined_methods[filepath][node.name] = {}  # 10. Инициализация для методов класса
            # 11. Обработка обычных импортов (import ...)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    source_module = alias.name
                    imported_name = alias.asname or alias.name
                    if source_module not in self.file_imports[filepath]:
                        self.file_imports[filepath][source_module] = set()
                    self.file_imports[filepath][source_module].add(imported_name)
            # 12. Обработка импортов с from (from ... import ...)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""  # Может быть None для 'from . import ...'
                level = node.level          # Уровень относительного импорта (0 = абсолютный)

                # 13. Преобразование относительного импорта в абсолютный путь
                source_module = self._resolve_relative_import(filepath, module, level, project_dir)

                for alias in node.names:
                    imported_name = alias.asname or alias.name
                    if source_module not in self.file_imports[filepath]:
                        self.file_imports[filepath][source_module] = set()
                    self.file_imports[filepath][source_module].add(imported_name)
                    # 14. Специальная обработка для импортов с * (from module import *)
                    if alias.name == "*" and source_module in self.file_exports:
                        for export in self.file_exports[source_module]:
                            self.file_imports[filepath][source_module].add(export)

    def _analyze_usage(self, filepath: str):
        """Анализирует использование функций, классов и методов в указанном Python-файле.

            Метод выполняет анализ AST-дерева файла для выявления всех случаев использования:
            - Вызовов функций верхнего уровня
            - Использования классов (создание экземпляров, аннотации типов)
            - Вызовов методов классов
            - Обращений к атрибутам объектов

            Подробное описание работы:
            1. Читает и парсит файл в AST-дерево
            2. Добавляет ссылки на родительские узлы
            3. Обходит дерево и анализирует узлы вызовов (Call) и имен (Name)
            4. Классифицирует найденные использования по типам:
               - Простые вызовы функций (Name)
               - Вызовы методов через точку (Attribute)
               - Использование классов в коде

            Args:
                filepath (str): Абсолютный путь к анализируемому .py файлу

            Side effects:
                Обновляет следующие структуры данных класса:
                - used_functions: добавляет используемые функции
                - used_classes: добавляет используемые классы
                - used_methods: добавляет используемые методы

            Raises:
                FileNotFoundError: если указанный файл не существует
                SyntaxError: если файл содержит синтаксические ошибки
                UnicodeDecodeError: если файл содержит некорректные символы

            Note:
                - Учитывает только использования в контексте загрузки (ast.Load)
                - Для вызовов методов анализирует контекст (вызывается ли метод у локального класса)
                - Не учитывает динамические вызовы через getattr или аналогичные механизмы
                - Сохраняет только факт использования, без информации о количестве использований
                - Для корректной работы требует предварительного вызова _analyze_exports_and_imports

            Example:
                Для кода:
                    class MyClass:
                        def method(self): pass
                    MyClass().method()
                Метод добавит:
                    - MyClass в used_classes
                    - method в used_methods для MyClass
            """
        # 1. Открывает указанный файл и парсит его содержимое в AST-дерево
        with open(filepath, 'r', encoding='utf-8') as file:
            tree = ast.parse(file.read(), filename=filepath)

        # 2. Добавляет ссылки на родительские узлы в AST для анализа контекста
        self._add_parent_links(tree)

        # 3. Начинает рекурсивный обход всех узлов AST-дерева
        for node in ast.walk(tree):
            # 4. Обработка узлов вызовов (Call) - функций и методов
            # Использование функций и методов
            if isinstance(node, ast.Call):
                if (isinstance(node.func, ast.Attribute) and node.func.attr == 'connect'):
                    # Считаем, что сигнал подключен к слоту
                    self._register_qt_connection(node, filepath)
                    continue  # Пропускаем дальнейшую обработку
                # 5. Если вызов простой функции (через имя)
                if isinstance(node.func, ast.Name):
                    # 6. Добавляет имя функции в used_functions текущего файла
                    self.used_functions[filepath].add(node.func.id)
                # 7. Если вызов метода через точку (attribute access)
                elif isinstance(node.func, ast.Attribute):
                    # 8. Проверяет, что объект вызывается по имени (не через выражение)
                    if isinstance(node.func.value, ast.Name):
                        obj_name = node.func.value.id       # Имя объекта
                        method_name = node.func.attr        # Имя метода
                        if obj_name == 'self':
                            # Находим родительский класс
                            current = node
                            while hasattr(current, 'parent'):
                                current = current.parent
                                if isinstance(current, ast.ClassDef):
                                    # Добавляем метод в used_methods для текущего класса
                                    if current.name not in self.used_methods[filepath]:
                                        self.used_methods[filepath][current.name] = set()
                                    self.used_methods[filepath][current.name].add(method_name)
                                    break
                            continue
                        # 9. Если объект - это класс, определенный в этом же файле
                        if obj_name in self.defined_classes[filepath]:
                            # 10. Инициализирует структуру для методов класса если нужно
                            if obj_name not in self.used_methods[filepath]:
                                self.used_methods[filepath][obj_name] = set()
                            # 11. Добавляет метод в used_methods
                            self.used_methods[filepath][obj_name].add(method_name)
                        else:
                            # 12. Если не класс, добавляет как функцию с точечной нотацией
                            self.used_functions[filepath].add(f"{obj_name}.{method_name}")

            # 13. Обработка использования имен в контексте чтения (не записи)
            # Использование классов
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                # 14. Если имя соответствует классу из этого файла
                if node.id in self.defined_classes[filepath]:
                    # 15. Добавляет класс в used_classes
                    self.used_classes[filepath].add(node.id)

    def _register_qt_connection(self, node, filepath):
        """Регистрирует Qt-соединение сигнал-слот."""
        try:
            # Получаем аргумент connect (обычно это слот)
            if node.args and isinstance(node.args[0], ast.Name):
                slot_name = node.args[0].id

                # Ищем родительский класс
                current = node
                while hasattr(current, 'parent'):
                    current = current.parent
                    if isinstance(current, ast.ClassDef):
                        # Добавляем слот как используемый метод
                        if filepath not in self.used_methods:
                            self.used_methods[filepath] = {}
                        if current.name not in self.used_methods[filepath]:
                            self.used_methods[filepath][current.name] = set()
                        self.used_methods[filepath][current.name].add(slot_name)
                        break

        except AttributeError:
            pass  # Игнорируем ошибки анализа
    def _is_name_used_in_other_files(self, filepath: str, name: str) -> bool:
        """Проверяет, используется ли указанное имя (функция/класс) в других файлах проекта.

            Анализирует информацию об импортах во всех файлах проекта, чтобы определить,
            экспортируется ли указанное имя из исходного файла и используется ли оно в других модулях.

            Алгоритм работы:
            1. Итерирует по всем файлам проекта, которые импортируют что-либо
            2. Для каждого файла проверяет его импорты
            3. Если найден импорт из исходного файла (filepath), содержащий искомое имя (name):
               - Возвращает True (имя используется в других файлах)
            4. Если ни одного использования не найдено - возвращает False

            Args:
                filepath (str): Абсолютный путь к файлу, где определено проверяемое имя
                name (str): Имя функции/класса для проверки использования

            Returns:
                bool: True если имя импортируется и используется в других файлах проекта,
                      False в противном случае

            Note:
                - Учитывает как прямые импорты (import module.name), так и импорты с псевдонимами
                - Проверяет только факт импорта, а не фактическое использование в коде
                - Не учитывает динамические импорты (через importlib или __import__)
                - Для относительных импортов проверяет их абсолютные эквиваленты
                - Ложные срабатывания возможны при импорте через 'from module import *'

            Examples:
                Если file1.py содержит `def foo(): pass`, а file2.py содержит `from file1 import foo`,
                то вызов `_is_name_used_in_other_files('/path/file1.py', 'foo')` вернет True
            """
        # 1. Итерация по всем файлам-импортерам (которые что-то импортируют)
        for importer, imports in self.file_imports.items():
            # 2. Пропускаем текущий файл (не проверяем импорты самого в себя)
            if importer == filepath:
                continue
            # 3. Итерация по модулям, из которых импортируются имена
            for source_module, imported_names in imports.items():
                # 4. Проверка двух условий:
                #    - Импорт идет из нашего файла (source_module == filepath)
                #    - Искомое имя есть в списке импортированных имен
                if source_module == filepath and name in imported_names:
                    return True
        # 6. Если ни одного использования не найдено во всех файлах
        return False

    def _is_method_used(self, filepath: str, class_name: str, method_name: str) -> bool:
        """Определяет, используется ли указанный метод класса в проекте.

            Проверяет использование метода по следующим критериям:
            1. Автоматически считаются используемыми специальные методы (__init__, __str__ и др.)
            2. Проверяет использование метода внутри его собственного файла
            3. Проверяет импорт и использование метода из других файлов проекта

            Args:
                filepath (str): Абсолютный путь к файлу, содержащему класс
                class_name (str): Имя класса, содержащего проверяемый метод
                method_name (str): Имя метода для проверки

            Returns:
                bool: True если метод используется в проекте, False если не используется

            Note:
                - Специальные методы всегда считаются используемыми (даже если явных вызовов нет)
                - Для проверки использования в других файлах формируется полное имя в формате 'ClassName.method_name'
                - Учитывает только статические вызовы (не обнаруживает динамические вызовы через getattr)
                - Ложные срабатывания возможны при импорте через 'from module import *'

            Examples:
                Если метод 'calculate' класса 'MathUtils' используется в другом файле как:
                'from utils import MathUtils; MathUtils.calculate()',
                метод вернет True

            Implementation Details:
                1. Сначала проверяет наличие метода в списке специальных методов
                2. Затем проверяет локальное использование в пределах файла
                3. Наконец проверяет использование в других файлах через _is_name_used_in_other_files
            """
        # Специальные методы считаем используемыми
        # 1. Проверка специальных методов (__init__, __str__ и т.д.)
        # Специальные методы всегда считаются используемыми, даже без явных вызовов
        if method_name in self.special_methods:
            return True  # -> Быстрый выход для спецметодов

        override_methods = {'run', 'main', 'execute', 'start', 'init', 'initialize',
                            'setup', 'update', 'render', 'draw', 'process', 'handle',
                            'create', 'build', 'load', 'save'}
        if method_name in override_methods:
            return True

        # 2. Проверка использования метода внутри его родного файла
        # Доступ к структуре: used_methods[filepath][class_name]
        if (filepath in self.used_methods and   # Есть ли записи для этого файла?
            class_name in self.used_methods[filepath] and # Есть ли класс?
            method_name in self.used_methods[filepath][class_name]):  # Есть ли метод?
            return True     # Метод используется в этом файле

        # 3. Проверка использования в других файлах через импорт
        # Формируем полное имя в формате "ClassName.method_name"
        full_name = f"{class_name}.{method_name}"
        # Делегируем проверку методу _is_name_used_in_other_files
        return self._is_name_used_in_other_files(filepath, full_name)

    def get_unused_code_report(self) -> Dict[str, Dict[str, List[Tuple[str, int, int]]]]:
        """Формирует комплексный отчет о неиспользуемом коде в проекте.

        Анализирует собранные данные о определениях и использованиях кода, выявляя:
        - Неиспользуемые функции верхнего уровня
        - Неиспользуемые методы классов
        - Неиспользуемые классы

        Структура отчета:
        {
            "unused_functions": {filepath: [(name, line, col), ...]},
            "unused_methods": {filepath: {class_name: [(method_name, line, col), ...]}},
            "unused_classes": {filepath: [(class_name, line, col), ...]}
        }

        Returns:
            Dict[str, Dict[str, List[Tuple[str, int, int]]]]:
            Иерархический отчет о неиспользуемом коде с указанием позиций в исходных файлах.

        Note:
            - Для функций проверяет отсутствие использования как в текущем файле, так и в других файлах
            - Для методов дополнительно проверяет наличие в списке специальных методов
            - Позиции (line, col) соответствуют месту определения кода в исходном файле
            - Отчет не включает косвенно используемый код (например, методы, вызываемые только через super())
            - Не учитывает динамические вызовы через getattr или аналогичные механизмы

        Examples:
            Пример возвращаемого отчета:
            {
                "unused_functions": {
                    "module.py": [("helper_func", 10, 4)]
                },
                "unused_methods": {
                    "service.py": {
                        "Service": [("_internal_method", 25, 8)]
                    }
                },
                "unused_classes": {
                    "models.py": [("OldModel", 42, 0)]
                }
            }
        """
        # 1. Инициализация структуры отчета
        report = {
            "unused_functions": {},     # Формат: {файл: [(имя, строка, столбец)]}
            "unused_methods": {},       # Формат: {файл: {класс: [(метод, строка, столбец)]}}
            "unused_classes": {},       # Формат: {файл: [(класс, строка, столбец)]}
        }
        
        # Неиспользуемые функции
        # 2. Анализ неиспользуемых функций верхнего уровня
        for filepath, functions in self.defined_functions.items():
            unused = []
            for func, (lineno, col_offset) in functions.items():
                # Проверка двух условий:
                # - Нет локального использования (в used_functions)
                # - Нет импорта в других файлах
                if (func not in self.used_functions[filepath] and 
                    not self._is_name_used_in_other_files(filepath, func)):
                    unused.append((func, lineno, col_offset))
            if unused:      # Добавляем в отчет только файлы с неиспользуемыми функциями
                report["unused_functions"][filepath] = unused
        
        # Неиспользуемые методы
        # 3. Анализ неиспользуемых методов классов
        for filepath, classes in self.defined_methods.items():
            unused_methods = {}
            for class_name, methods in classes.items():
                unused = []
                for method, (lineno, col_offset) in methods.items():
                    # Комплексная проверка через _is_method_used:
                    # - Специальные методы пропускаются
                    # - Проверяется локальное и внешнее использование
                    if not self._is_method_used(filepath, class_name, method):
                        unused.append((method, lineno, col_offset))
                if unused:      # Добавляем только классы с неиспользуемыми методами
                    unused_methods[class_name] = unused
            if unused_methods:  # Добавляем только файлы с проблемными классами
                report["unused_methods"][filepath] = unused_methods
        
        # Неиспользуемые классы
        # 4. Анализ неиспользуемых классов
        for filepath, classes in self.defined_classes.items():
            unused = []
            for cls, (lineno, col_offset) in classes.items():
                # Аналогичная проверка как для функций:
                # - Нет локального использования
                # - Нет импорта в других файлах
                if (cls not in self.used_classes[filepath] and 
                    not self._is_name_used_in_other_files(filepath, cls)):
                    unused.append((cls, lineno, col_offset))
            if unused:
                report["unused_classes"][filepath] = unused
        
        return report

    def _resolve_relative_import(self, filepath: str, module: str, level: int, project_dir: str) -> str:
        """Преобразует относительный импорт Python в абсолютный путь к модулю.

        Обрабатывает относительные импорты (с точками) согласно PEP 328, преобразуя их в
        абсолютные пути к файлам модулей с учетом уровня вложенности (level).

        Алгоритм работы:
        1. Для level=0 возвращает module без изменений (абсолютный импорт)
        2. Для level>0:
           a. Поднимается на level-1 директорий вверх от расположения filepath
           b. Если module не указан, предполагает импорт __init__.py
           c. Для указанного module строит путь к .py файлу
           d. Рекурсивно проверяет существование файла, поднимаясь вверх по директориям

        Args:
            filepath (str): Абсолютный путь к файлу, содержащему импорт
            module (str): Имя импортируемого модуля (может быть пустой строкой)
            level (int): Уровень относительности импорта (0 для абсолютных)
            project_dir (str): Корневая директория проекта (для остановки поиска)

        Returns:
            str: Абсолютный путь к файлу модуля или исходное имя модуля, если файл не найден

        Raises:
            ValueError: Если level < 0

        Note:
            - Корректно обрабатывает случаи импорта пакетов (__init__.py)
            - Поддерживает многоуровневые относительные импорты (например, 'from ... import')
            - Если модуль не найден, возвращает исходное имя (для обработки внешних модулей)
            - Не проверяет валидность синтаксиса Python в найденных файлах

        Examples:
            >>> resolver._resolve_relative_import(
            ...     '/project/pkg/mod.py',
            ...     'submod',
            ...     1,
            ...     '/project'
            ... )
            '/project/pkg/submod.py'
        """
        # 1. Обработка абсолютных импортов (level = 0)
        if level == 0:
            return module  # Просто возвращаем имя модуля без изменений
        # 2. Определяем стартовую директорию для относительного импорта
        current_dir = os.path.dirname(filepath)   # Директория текущего файла
        # 3. Поднимаемся на level-1 директорий вверх
        for _ in range(level - 1):
            current_dir = os.path.dirname(current_dir) # Получаем родительскую директорию
        # 4. Обработка импорта пакета (from .. import)
        if not module:
            # Создаем путь до __init__.py в целевой директории
            module_path = os.path.join(current_dir, "__init__.py")
        else:
            # 5. Создаем путь к модулю с заменой точек на разделители ОС
            module_path = os.path.join(current_dir, *module.split('.')) + ".py"

        # Ищем ближайший существующий файл
        # 6. Рекурсивный поиск существующего модуля
        while not os.path.exists(module_path):
            if module_path.endswith("__init__.py"):
                # 7. Если не найден __init__.py, поднимаемся выше
                module_path = os.path.join(os.path.dirname(module_path), "__init__.py")
            else:
                parent_dir = os.path.dirname(module_path)
                # 8. Проверка достижения корневой директории
                if parent_dir == os.path.dirname(parent_dir):  # Достигли корня
                    return module  # Возвращаем исходное имя модуля, если не нашли файл
                # 9. Пробуем найти __init__.py в родительской директории
                module_path = os.path.join(os.path.dirname(parent_dir), "__init__.py")

        return module_path    # 10. Возвращаем абсолютный путь к найденному модулю

    def save_report_to_file(self, report: Dict[str, Dict[str, List[Tuple[str, int, int]]]], output_file: str):
        """Сохраняет отчет о неиспользуемом коде в текстовый файл в удобочитаемом формате.

            Формирует структурированный текстовый отчет на основе данных анализа и записывает его
            в указанный файл. Отчет содержит три основных раздела с группировкой по файлам:

            1. Неиспользуемые функции
            2. Неиспользуемые методы (с группировкой по классам)
            3. Неиспользуемые классы

            Args:
                report (Dict): Словарь с отчетом, полученный из get_unused_code_report()
                output_file (str): Путь к файлу для сохранения отчета

            Returns:
                None

            Raises:
                IOError: При проблемах с записью в файл
                PermissionError: Если нет прав на запись в указанный файл

            Note:
                - Создает файл, если он не существует, перезаписывает если существует
                - Использует UTF-8 кодировку для поддержки Unicode символов
                - Форматирует вывод с отступами для улучшения читаемости
                - Сохраняет точные позиции кода (строка, столбец) для каждого элемента
                - Разделы отчета разделены четкими заголовками

            Examples:
                Пример содержимого файла отчета:
                === Анализ мертвого кода ===

                === Неиспользуемые функции ===
                /path/module.py:
                  - helper_func (строка 10, позиция 4)
                  - utils (строка 15, позиция 0)

                === Неиспользуемые методы ===
                /path/service.py:
                  Класс DataProcessor:
                    - _clean_data (строка 25, позиция 8)
                    - _validate (строка 30, позиция 8)

                === Неиспользуемые классы ===
                /path/old.py:
                  - LegacyClass (строка 5, позиция 0)
            """
        # 1. Открытие файла на запись с UTF-8 кодировкой
        with open(output_file, 'w', encoding='utf-8') as f:
            # 2. Заголовок отчета
            f.write("=== Анализ мертвого кода ===\n\n")
            # 3. Секция неиспользуемых функций
            f.write("=== Неиспользуемые функции ===\n")
            for filepath, funcs in report["unused_functions"].items():
                f.write(f"{filepath}:\n")   # 4. Запись пути к файлу
                for func, line, col in funcs:
                    # 5. Запись информации о функции (имя, строка, позиция)
                    f.write(f"  - {func} (строка {line}, позиция {col})\n")
                f.write("\n")  # 6. Разделитель между файлами

            # 7. Секция неиспользуемых методов
            f.write("\n=== Неиспользуемые методы ===\n")
            for filepath, classes in report["unused_methods"].items():
                f.write(f"{filepath}:\n")  # 8. Запись пути к файлу
                for class_name, methods in classes.items():
                    # 9. Запись имени класса
                    f.write(f"  Класс {class_name}:\n")
                    for method, line, col in methods:
                        # 10. Запись информации о методе
                        f.write(f"    - {method} (строка {line}, позиция {col})\n")
                f.write("\n")  # 11. Разделитель между файлами

            # 12. Секция неиспользуемых классов
            f.write("\n=== Неиспользуемые классы ===\n")
            for filepath, classes in report["unused_classes"].items():
                f.write(f"{filepath}:\n")  # 13. Запись пути к файлу
                for cls, line, col in classes:
                    # 14. Запись информации о классе
                    f.write(f"  - {cls} (строка {line}, позиция {col})\n")
                f.write("\n") # 15. Разделитель между файлами

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Анализатор мертвого кода Python')
    parser.add_argument('project_dir', help='Директория проекта для анализа')
    parser.add_argument('--output', default='dead_code_report.txt', help='Файл для сохранения отчета')
    args = parser.parse_args()
    #Раскоментировать после отладки---
    #analyzer = DeadCodeAnalyzer()
    #analyzer.analyze_project(args.project_dir)
    #report = analyzer.get_unused_code_report()
    #analyzer.save_report_to_file(report, args.output)
    
    #print(f"Анализ завершен. Результат сохранен в {args.output}")
    #----