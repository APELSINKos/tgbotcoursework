"""Automated test run for the Student Task Manager application (product of another team).

The script starts the real application, works with its window the way a user would
(presses buttons, types into fields, chooses rows and list values) and compares what
is visible in the window and in the data file with the expected results taken from
the technical specification of the product.

Usage:  python stm_autotest.py <product folder> <output folder>

Every test gets its own copy of the product with its own data file, so the tests do
not depend on each other. Standard message boxes are intercepted: their text goes to
the protocol, and the answer to a confirmation question is chosen by the test step.
Screenshots need the Pillow package; without it the run works, just without pictures.
"""

import ctypes
import hashlib
import importlib.util
import itertools
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

MODULE_FILE = "student_task_manager.py"

# Labels of the fields in the task window
F_TITLE = "Название задачи:"
F_SUBJECT = "Предмет:"
F_DATE = "Срок (ДД.ММ.ГГГГ):"
F_PRIORITY = "Приоритет:"
F_STATUS = "Статус:"

TODAY = date.today()
DAY = timedelta(days=1)


def fmt(day):
    return day.strftime("%d.%m.%Y")


def task(title, deadline, status="Не начато", subject="Другое", priority="Средний"):
    return {"title": title, "subject": subject, "deadline": deadline,
            "priority": priority, "status": status}


# The same three tasks the product is shipped with, but the dates are counted from today
DEMO = [
    task("Сдать практическую работу №1", fmt(TODAY + 6 * DAY), "В работе", "Тестирование ПО", "Высокий"),
    task("Подготовить отчёт по базе данных", fmt(TODAY + 14 * DAY), "Не начато", "Базы данных", "Средний"),
    task("Повторить модель AnyLogic", fmt(TODAY + 2 * DAY), "Не начато", "AnyLogic", "Низкий"),
]
FUTURE = fmt(TODAY + 30 * DAY)


def walk(widget):
    """The widget and everything inside it."""
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def label_text(label):
    """Text shown by a label, also when the text comes from a variable."""
    variable = str(label.cget("textvariable"))
    return str(label.getvar(variable)) if variable else str(label.cget("text"))


def neighbour(container, text):
    """The widget placed in the grid right after the label with the given text."""
    for label in walk(container):
        if not isinstance(label, ttk.Label) or label.winfo_manager() != "grid":
            continue
        if str(label.cget("text")) != text:
            continue
        place = label.grid_info()
        for widget in label.master.winfo_children():
            if widget is label or widget.winfo_manager() != "grid":
                continue
            other = widget.grid_info()
            if int(other["row"]) == int(place["row"]) and int(other["column"]) == int(place["column"]) + 1:
                return widget
    raise LookupError(f"no field next to the label {text!r}")


def find_button(container, text):
    for widget in walk(container):
        if isinstance(widget, ttk.Button) and str(widget.cget("text")) == text:
            return widget
    raise LookupError(f"no button {text!r}")


def window_box(window):
    """Outer rectangle of a top-level window on the screen, with its title bar."""
    frame = int(window.wm_frame(), 16)
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(frame, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    return rect.left, rect.top, rect.right, rect.bottom


class StartError(Exception):
    """The application could not start."""


class App:
    """One running copy of the application and the actions a user can do with it."""

    current = None   # the copy that receives the intercepted message boxes
    counter = itertools.count(1)

    def __init__(self, workdir, shots_dir, test_id):
        self.workdir = workdir
        self.shots_dir = shots_dir
        self.test_id = test_id
        self.messages = []       # (kind, title, text) of every message box
        self.answer_yes = True   # answer to a confirmation question
        self.refused = False     # the task window did not accept the data
        self.problems = []
        self.shots = []
        App.current = self

        path = os.path.join(workdir, MODULE_FILE)
        spec = importlib.util.spec_from_file_location(f"stm_copy_{next(App.counter)}", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            self.root = module.StudentTaskManager()
        except Exception as error:
            if tk._default_root is not None:
                tk._default_root.destroy()
            raise StartError(f"{type(error).__name__}: {error}") from error

        self.root.geometry("+80+60")
        self.root.attributes("-topmost", True)
        self.tree = next(w for w in walk(self.root) if isinstance(w, ttk.Treeview))
        self.root.update()

    # ---------- what the user sees ----------

    def rows(self):
        return [tuple(str(v) for v in self.tree.item(i, "values")) for i in self.tree.get_children()]

    def titles(self):
        return [row[0] for row in self.rows()]

    def highlighted(self):
        """Titles of the rows that are shown with a coloured background."""
        result = []
        for item in self.tree.get_children():
            colours = [self.tree.tag_configure(tag, "background") for tag in self.tree.item(item, "tags")]
            if any(str(colour) for colour in colours):
                result.append(str(self.tree.item(item, "values")[0]))
        return result

    def stats(self):
        """The statistics line as a dictionary: {'Всего': 3, 'Выполнено': 0, 'Просрочено': 0}."""
        for widget in walk(self.root):
            if isinstance(widget, ttk.Label) and label_text(widget).startswith("Всего:"):
                return {name: int(value) for name, value in re.findall(r"(\w+): (\d+)", label_text(widget))}
        raise LookupError("no statistics line")

    def details_label(self):
        """The label that shows the title of the selected task."""
        for widget in walk(self.root):
            if isinstance(widget, ttk.Label) and label_text(widget) == "Выбранная задача:":
                return [w for w in widget.master.winfo_children() if w is not widget][0]
        raise LookupError("no 'selected task' area")

    def stored(self):
        """Tasks saved in the data file."""
        with open(os.path.join(self.workdir, "data", "tasks.json"), encoding="utf-8") as file:
            return json.load(file)

    def stored_titles(self):
        return [item.get("title") for item in self.stored()]

    # ---------- what the user does ----------

    def press(self, text):
        find_button(self.root, text).invoke()
        self.root.update()

    def select(self, title):
        for item in self.tree.get_children():
            if str(self.tree.item(item, "values")[0]) == title:
                self.tree.selection_set(item)
                self.tree.focus(item)
                self.root.update()
                return
        raise LookupError(f"no row {title!r}")

    def search(self, text):
        field = neighbour(self.root, "Поиск:")
        field.delete(0, "end")
        field.insert(0, text)
        self.press("Найти")

    def search_text(self):
        return neighbour(self.root, "Поиск:").get()

    def choose(self, label, value):
        """Pick a value in one of the drop-down lists of the main window."""
        box = neighbour(self.root, label)
        box.set(value)
        self.root.update()
        box.event_generate("<<ComboboxSelected>>")
        self.root.update()

    def dialog(self, button, fields=None, shot=False):
        """Plan the work in the task window that the next button press opens:
        fill the fields, then press 'Сохранить' or 'Отмена'."""
        self.refused = False

        def work():
            windows = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
            if not windows:
                return
            window = windows[-1]
            try:
                window.update()
                for label, value in (fields or {}).items():
                    widget = neighbour(window, label)
                    if isinstance(widget, ttk.Combobox):
                        widget.set(value)
                    else:
                        widget.delete(0, "end")
                        widget.insert(0, value)
                window.update()
                if shot:
                    self.shot("dialog", window)
                find_button(window, button).invoke()
                if window.winfo_exists():        # the data was not accepted, the window is still open
                    self.refused = True
                    find_button(window, "Отмена").invoke()
            except Exception as error:
                self.problems.append(f"{type(error).__name__}: {error}")
                if window.winfo_exists():
                    window.destroy()

        self.root.after(300, work)

    def add(self, fields, button="Сохранить", shot=False):
        self.dialog(button, fields, shot)
        self.press("Добавить")

    def edit(self, title, fields, button="Сохранить"):
        self.select(title)
        self.dialog(button, fields)
        self.press("Изменить")

    def delete(self, title, confirm=True):
        self.select(title)
        self.answer_yes = confirm
        self.press("Удалить")

    def shot(self, suffix="", extra=None):
        """Save a picture of the window (and of the task window, if it is open)."""
        if ImageGrab is None:
            return None
        self.root.lift()
        self.root.update()
        time.sleep(0.45)
        self.root.update()
        boxes = [window_box(self.root)] + ([window_box(extra)] if extra is not None else [])
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
        name = self.test_id + (f"_{suffix}" if suffix else "") + ".png"
        ImageGrab.grab(bbox=box, all_screens=True).save(os.path.join(self.shots_dir, name))
        self.shots.append(name)
        return name

    def close(self):
        """The same as closing the window."""
        if self.root.winfo_exists():
            self.root.destroy()


def intercept(kind, result):
    def fake(title=None, message=None, **_options):
        app = App.current
        app.messages.append((kind, str(title), str(message)))
        return app.answer_yes if result is None else result
    return fake


messagebox.showerror = intercept("ошибка", "ok")
messagebox.showinfo = intercept("сообщение", "ok")
messagebox.showwarning = intercept("предупреждение", "ok")
messagebox.askyesno = intercept("вопрос", None)


class Session:
    """Prepares a private copy of the product for a test and starts the application."""

    def __init__(self, product_dir, shots_dir, test_id):
        self.product_dir = product_dir
        self.shots_dir = shots_dir
        self.test_id = test_id
        self.workdir = tempfile.mkdtemp(prefix="stm_test_")
        self.app = None
        self.shots = []
        shutil.copy(os.path.join(product_dir, MODULE_FILE), self.workdir)

    def start(self, tasks=None, raw=None, no_data=False):
        """tasks - list for the data file; raw - exact text of the data file;
        no_data - start without the data folder at all."""
        data_dir = os.path.join(self.workdir, "data")
        if no_data:
            shutil.rmtree(data_dir, ignore_errors=True)
        elif tasks is not None or raw is not None:
            os.makedirs(data_dir, exist_ok=True)
            with open(os.path.join(data_dir, "tasks.json"), "w", encoding="utf-8") as file:
                file.write(raw if raw is not None else json.dumps(tasks, ensure_ascii=False, indent=2))
        return self.restart()

    def restart(self):
        """Close the application (if it is open) and start it again with the same data."""
        self.finish()
        self.app = App(self.workdir, self.shots_dir, self.test_id)
        return self.app

    def finish(self):
        if self.app is not None:
            self.shots += self.app.shots
            self.app.close()
            self.app = None

    def remove(self):
        self.finish()
        shutil.rmtree(self.workdir, ignore_errors=True)


def quoted(items):
    return ", ".join(f"«{item}»" for item in items) if items else "пусто"


TESTS = []


def test(test_id, requirement, title, technique, steps, expected):
    def register(function):
        TESTS.append({"id": test_id, "requirement": requirement, "title": title, "technique": technique,
                      "steps": steps, "expected": expected, "run": function})
        return function
    return register


# ======================================================================
#  FR-01, FR-02: list of tasks and adding a task
# ======================================================================

@test("TC-01", "FR-01", "Отображение сохранённых задач", "Тестирование вариантов использования",
      "Запустить приложение с тремя сохранёнными задачами",
      "В таблице три строки; название, предмет, срок, приоритет и статус совпадают с сохранёнными")
def tc01(s):
    app = s.start(DEMO)
    expected = [(t["title"], t["subject"], t["deadline"], t["priority"], t["status"]) for t in DEMO]
    app.shot()
    return f"В таблице строк: {len(app.rows())}; значения {'совпадают' if app.rows() == expected else 'НЕ совпадают'} с сохранёнными", app.rows() == expected


@test("TC-02", "FR-02", "Добавление задачи с корректными данными", "Эквивалентное разбиение",
      "«Добавить» → название «Лабораторная работа 2», предмет «Базы данных», срок через 30 дней, приоритет «Высокий», статус «В работе» → «Сохранить»",
      "Задача появляется в таблице со всеми введёнными значениями и записывается в файл данных")
def tc02(s):
    app = s.start(DEMO)
    app.add({F_TITLE: "Лабораторная работа 2", F_SUBJECT: "Базы данных", F_DATE: FUTURE,
             F_PRIORITY: "Высокий", F_STATUS: "В работе"})
    row = ("Лабораторная работа 2", "Базы данных", FUTURE, "Высокий", "В работе")
    in_table, in_file = row in app.rows(), "Лабораторная работа 2" in app.stored_titles()
    return f"В таблице: {'есть' if in_table else 'нет'}; в файле данных: {'есть' if in_file else 'нет'}", in_table and in_file


# ======================================================================
#  FR-03: the title is required
# ======================================================================

def try_title(s, value):
    app = s.start(DEMO)
    app.add({F_TITLE: value, F_DATE: FUTURE})
    added = len(app.rows()) - len(DEMO)
    text = [m[2] for m in app.messages]
    return app, added, text


@test("TC-03", "FR-03", "Пустое название при добавлении", "Анализ граничных значений",
      "«Добавить» → название оставить пустым, срок корректный → «Сохранить»",
      "Сохранение запрещено, выводится сообщение об обязательном поле, задача не создаётся")
def tc03(s):
    app, added, text = try_title(s, "")
    app.shot()
    actual = ("Задача с пустым названием сохранена: в таблице появилась строка без названия, сообщений нет"
              if added else f"Задача не создана; сообщение: {quoted(text)}")
    return actual, added == 0


@test("TC-04", "FR-03", "Название из одних пробелов", "Анализ граничных значений",
      "«Добавить» → название «   » (три пробела), срок корректный → «Сохранить»",
      "Сохранение запрещено: название без значащих символов равносильно пустому")
def tc04(s):
    app, added, text = try_title(s, "   ")
    actual = ("Задача с названием из пробелов сохранена, сообщений нет"
              if added else f"Задача не создана; сообщение: {quoted(text)}")
    return actual, added == 0


@test("TC-05", "FR-03", "Название из одного символа", "Анализ граничных значений",
      "«Добавить» → название «А», срок корректный → «Сохранить»",
      "Задача создаётся: минимально допустимое название принимается")
def tc05(s):
    app, added, _ = try_title(s, "А")
    return f"Создано задач: {added}; название в таблице: {quoted(app.titles()[-1:])}", added == 1 and app.titles()[-1] == "А"


# ======================================================================
#  FR-04: format of the date
# ======================================================================

def try_dates(s, values):
    """Add a task with every date in turn; returns (accepted, refused, messages)."""
    app = s.start(DEMO)
    accepted, refused, messages = [], [], set()
    for number, value in enumerate(values, start=1):
        before = len(app.rows())
        app.messages.clear()
        app.add({F_TITLE: f"Проверка даты {number}", F_DATE: value})
        (accepted if len(app.rows()) > before else refused).append(value)
        messages.update(m[2] for m in app.messages)
    return app, accepted, refused, sorted(messages)


@test("TC-06", "FR-04", "Корректная дата на границе календаря", "Анализ граничных значений",
      "«Добавить» → сроки «29.02.2028» (високосный год) и «31.12.2026» → «Сохранить»",
      "Обе даты принимаются, задачи создаются")
def tc06(s):
    app, accepted, refused, _ = try_dates(s, ["29.02.2028", "31.12.2026"])
    return f"Принято: {quoted(accepted)}; отклонено: {quoted(refused)}", not refused


@test("TC-07", "FR-04", "Несуществующая дата", "Анализ граничных значений",
      "«Добавить» → сроки «31.02.2026», «29.02.2026», «00.10.2026», «15.13.2026» → «Сохранить»",
      "Каждая дата отклоняется сообщением об ошибке, задача не сохраняется, приложение продолжает работать")
def tc07(s):
    app, accepted, refused, messages = try_dates(s, ["31.02.2026", "29.02.2026", "00.10.2026", "15.13.2026"])
    return f"Отклонено: {quoted(refused)}; принято: {quoted(accepted)}; сообщение: {quoted(messages)}", not accepted and bool(messages)


@test("TC-08", "FR-04", "Дата в другом формате и не дата", "Эквивалентное разбиение",
      "«Добавить» → сроки «2026-09-25», «25/09/2026», «abc», пустая строка → «Сохранить»",
      "Каждое значение отклоняется сообщением об ошибке, задача не сохраняется")
def tc08(s):
    app, accepted, refused, messages = try_dates(s, ["2026-09-25", "25/09/2026", "abc", ""])
    return f"Отклонено значений: {len(refused)} из 4; принято: {quoted(accepted)}; сообщение: {quoted(messages)}", not accepted and bool(messages)


@test("TC-09", "FR-04", "Дата без ведущих нулей", "Анализ граничных значений",
      "«Добавить» → срок «1.9.2027» → «Сохранить»",
      "Значение не в формате ДД.ММ.ГГГГ: отклоняется либо приводится к виду «01.09.2027»")
def tc09(s):
    app, accepted, refused, _ = try_dates(s, ["1.9.2027"])
    shown = [row[2] for row in app.rows() if row[0] == "Проверка даты 1"]
    ok = bool(refused) or shown == ["01.09.2027"]
    actual = "Значение отклонено" if refused else f"Задача сохранена, срок в таблице и в файле: {quoted(shown)}"
    return actual, ok


# ======================================================================
#  FR-05: editing, cancelling
# ======================================================================

@test("TC-10", "FR-05", "Изменение названия и приоритета", "Тестирование вариантов использования",
      "Выбрать «Повторить модель AnyLogic» → «Изменить» → название «Повторить модель AnyLogic (глава 3)», приоритет «Высокий» → «Сохранить»",
      "В таблице и в файле данных новые значения; остальные задачи не изменились")
def tc10(s):
    app = s.start(DEMO)
    new = "Повторить модель AnyLogic (глава 3)"
    app.edit("Повторить модель AnyLogic", {F_TITLE: new, F_PRIORITY: "Высокий"})
    row = [r for r in app.rows() if r[0] == new]
    ok = bool(row) and row[0][3] == "Высокий" and new in app.stored_titles() and len(app.stored()) == 3
    return f"Строка в таблице: {quoted(row[0]) if row else 'не найдена'}; задач в файле: {len(app.stored())}", ok


@test("TC-11", "FR-05, FR-04", "Некорректная дата при изменении", "Эквивалентное разбиение",
      "Выбрать задачу → «Изменить» → срок «99.99.2026» → «Сохранить»",
      "Сообщение об ошибке; срок задачи в таблице и в файле остаётся прежним")
def tc11(s):
    app = s.start(DEMO)
    app.edit(DEMO[0]["title"], {F_DATE: "99.99.2026"})
    kept = app.rows()[0][2] == DEMO[0]["deadline"] and app.stored()[0]["deadline"] == DEMO[0]["deadline"]
    return f"Сообщение: {quoted([m[2] for m in app.messages])}; срок задачи: «{app.rows()[0][2]}»", kept and bool(app.messages)


@test("TC-12", "FR-05, FR-03", "Удаление названия при изменении", "Анализ граничных значений",
      "Выбрать задачу → «Изменить» → стереть название → «Сохранить»",
      "Сохранение запрещено, название задачи остаётся прежним")
def tc12(s):
    app = s.start(DEMO)
    app.edit(DEMO[0]["title"], {F_TITLE: ""})
    now = app.stored()[0]["title"]
    actual = "Название не изменилось" if now == DEMO[0]["title"] else f"Изменение сохранено: название задачи в файле данных теперь «{now}»"
    return actual, now == DEMO[0]["title"]


@test("TC-13", "NFR (отмена)", "Отмена добавления и изменения", "Тестирование переходов состояний",
      "«Добавить» → заполнить поля → «Отмена»; выбрать задачу → «Изменить» → поменять название → «Отмена»",
      "Таблица и файл данных не изменяются")
def tc13(s):
    app = s.start(DEMO)
    app.add({F_TITLE: "Не должна появиться", F_DATE: FUTURE}, button="Отмена")
    app.edit(DEMO[1]["title"], {F_TITLE: "Не должно сохраниться"}, button="Отмена")
    same = app.stored() == DEMO and app.titles() == [t["title"] for t in DEMO]
    return "Таблица и файл данных не изменились" if same else f"Данные изменились: {quoted(app.stored_titles())}", same


# ======================================================================
#  FR-06: deleting
# ======================================================================

ABC = [task("Задача А", FUTURE, "В работе"), task("Задача Б", FUTURE, "Не начато"), task("Задача В", FUTURE, "В работе")]


def lost_instead(app, original, chosen):
    """Say which task really disappeared from the data file."""
    lost = [t["title"] for t in original if t["title"] not in app.stored_titles()]
    if lost == [chosen]:
        return f"Удалена «{chosen}»; остались: {quoted(app.stored_titles())}"
    return f"Вместо «{chosen}» удалена {quoted(lost)}; в таблице и в файле остались: {quoted(app.stored_titles())}"


@test("TC-14", "FR-06, NFR (отмена)", "Отказ от удаления", "Тестирование переходов состояний",
      "Выбрать «Задача А» → «Удалить» → на вопрос о подтверждении ответить «Нет»",
      "Задаётся вопрос о подтверждении; после ответа «Нет» все задачи на месте")
def tc14(s):
    app = s.start(ABC)
    app.delete("Задача А", confirm=False)
    asked = any(m[0] == "вопрос" for m in app.messages)
    return f"Вопрос задан: {'да' if asked else 'нет'}; в файле: {quoted(app.stored_titles())}", asked and app.stored() == ABC


@test("TC-15", "FR-06", "Удаление последней задачи списка", "Анализ граничных значений",
      "Три задачи А, Б, В. Выбрать «Задача В» (последняя) → «Удалить» → «Да»",
      "Удалена только «Задача В»")
def tc15(s):
    app = s.start(ABC)
    app.delete("Задача В")
    return f"Остались: {quoted(app.titles())}", app.titles() == ["Задача А", "Задача Б"] == app.stored_titles()


@test("TC-16", "FR-06", "Удаление первой задачи списка", "Анализ граничных значений",
      "Три задачи А, Б, В. Выбрать «Задача А» (первая) → «Удалить» → «Да»",
      "Удалена только «Задача А», остались Б и В")
def tc16(s):
    app = s.start(ABC)
    app.select("Задача А")
    app.shot("before")
    app.delete("Задача А")
    app.shot("after")
    return lost_instead(app, ABC, "Задача А"), app.stored_titles() == ["Задача Б", "Задача В"]


@test("TC-17", "FR-06, FR-09", "Удаление при включённом фильтре", "Тестирование вариантов использования",
      "Три задачи: А («В работе»), Б («Не начато»), В («В работе»). Фильтр «Статус» = «В работе» → выбрать «Задача А» → «Удалить» → «Да» → «Сбросить»",
      "Удалена «Задача А»; скрытая фильтром «Задача Б» не затронута")
def tc17(s):
    app = s.start(ABC)
    app.choose("Статус:", "В работе")
    visible = app.titles()
    app.delete("Задача А")
    app.press("Сбросить")
    return f"Под фильтром были видны {quoted(visible)}. " + lost_instead(app, ABC, "Задача А"), app.stored_titles() == ["Задача Б", "Задача В"]


@test("TC-18", "FR-06", "Удаление единственной задачи", "Анализ граничных значений",
      "В списке одна задача. Выбрать её → «Удалить» → «Да»",
      "Список пуст, «Всего: 0», приложение продолжает работать")
def tc18(s):
    app = s.start([task("Единственная", FUTURE)])
    app.delete("Единственная")
    return f"Строк в таблице: {len(app.rows())}; «Всего: {app.stats()['Всего']}»", not app.rows() and app.stats()["Всего"] == 0 and app.stored() == []


@test("TC-19", "FR-05, FR-06, FR-07", "Операции без выбранной задачи", "Предположение об ошибках",
      "Не выбирая строку, нажать по очереди «Изменить», «Удалить», «Отметить выполненной»",
      "Каждый раз выводится подсказка выбрать задачу; данные не изменяются")
def tc19(s):
    app = s.start(DEMO)
    for button in ("Изменить", "Удалить", "Отметить выполненной"):
        app.press(button)
    texts = [m[2] for m in app.messages]
    return f"Сообщений: {len(texts)}, текст: {quoted(sorted(set(texts)))}; данные {'не изменились' if app.stored() == DEMO else 'ИЗМЕНИЛИСЬ'}", len(texts) == 3 and app.stored() == DEMO


# ======================================================================
#  FR-07: marking as done
# ======================================================================

@test("TC-20", "FR-07", "Отметка задачи выполненной", "Тестирование вариантов использования",
      "Выбрать задачу со статусом «Не начато» → «Отметить выполненной»",
      "Статус задачи в таблице и в файле данных — «Выполнено»; остальные задачи без изменений")
def tc20(s):
    app = s.start(DEMO)
    app.select(DEMO[1]["title"])
    app.press("Отметить выполненной")
    in_table = app.rows()[1][4]
    statuses = [t["status"] for t in app.stored()]
    return f"Статус в таблице: «{in_table}»; статусы в файле: {quoted(statuses)}", in_table == "Выполнено" and statuses == ["В работе", "Выполнено", "Не начато"]


# ======================================================================
#  FR-08: search
# ======================================================================

def found(s, query):
    app = s.app if s.app is not None else s.start(DEMO)
    app.search(query)
    return app, app.titles()


@test("TC-21", "FR-08", "Поиск по началу и по середине названия", "Эквивалентное разбиение",
      "Поиск «Сдать» → «Найти»; затем поиск «отчёт» → «Найти» (регистр как в названии)",
      "Каждый запрос находит ровно одну задачу с этим текстом в названии")
def tc21(s):
    _, first = found(s, "Сдать")
    _, second = found(s, "отчёт")
    ok = first == [DEMO[0]["title"]] and second == [DEMO[1]["title"]]
    return f"«Сдать» → найдено {len(first)}; «отчёт» → найдено {len(second)}", ok


@test("TC-22", "FR-08", "Поиск строчными буквами", "Эквивалентное разбиение",
      "Поиск «сдать» (в названии слово написано с заглавной буквы) → «Найти»",
      "Найдена задача «Сдать практическую работу №1»: поиск не зависит от регистра")
def tc22(s):
    app, titles = found(s, "сдать")
    app.shot()
    return f"Найдено задач: {len(titles)}" + (" — таблица пуста" if not titles else ""), titles == [DEMO[0]["title"]]


@test("TC-23", "FR-08", "Поиск прописными буквами", "Эквивалентное разбиение",
      "Поиск «ANYLOGIC» → «Найти»",
      "Найдена задача «Повторить модель AnyLogic»")
def tc23(s):
    _, titles = found(s, "ANYLOGIC")
    return f"Найдено задач: {len(titles)}", titles == [DEMO[2]["title"]]


@test("TC-24", "FR-08", "Поиск отсутствующего текста и сброс", "Эквивалентное разбиение",
      "Поиск «zzz» → «Найти»; затем «Сбросить»",
      "Таблица пуста, ошибок нет; после «Сбросить» поле поиска очищено и показаны все задачи")
def tc24(s):
    app, titles = found(s, "zzz")
    app.press("Сбросить")
    ok = not titles and len(app.rows()) == 3 and app.search_text() == "" and not app.messages
    return f"По запросу найдено: {len(titles)}; после сброса строк: {len(app.rows())}, поле поиска: «{app.search_text()}»", ok


# ======================================================================
#  FR-09, FR-10: filters
# ======================================================================

@test("TC-25", "FR-09", "Фильтр по статусу и фильтр по предмету", "Эквивалентное разбиение",
      "«Статус» = «Не начато»; затем «Сбросить» и «Предмет» = «AnyLogic»",
      "По статусу показаны две задачи «Не начато»; по предмету — одна задача предмета AnyLogic")
def tc25(s):
    app = s.start(DEMO)
    app.choose("Статус:", "Не начато")
    by_status = app.titles()
    app.press("Сбросить")
    app.choose("Предмет:", "AnyLogic")
    by_subject = app.titles()
    ok = by_status == [DEMO[1]["title"], DEMO[2]["title"]] and by_subject == [DEMO[2]["title"]]
    return f"По статусу: {len(by_status)} задачи; по предмету: {len(by_subject)} задача", ok


@test("TC-26", "FR-08, FR-09", "Поиск и два фильтра одновременно", "Таблица решений",
      "«Статус» = «Не начато», «Предмет» = «Базы данных», поиск «отчёт» → «Найти»; затем поиск «модель» → «Найти»",
      "Условия действуют совместно: первый запрос показывает одну задачу, второй — ни одной")
def tc26(s):
    app = s.start(DEMO)
    app.choose("Статус:", "Не начато")
    app.choose("Предмет:", "Базы данных")
    app.search("отчёт")
    first = app.titles()
    app.search("модель")
    second = app.titles()
    return f"Первый запрос: {len(first)}; второй: {len(second)}", first == [DEMO[1]["title"]] and second == []


@test("TC-27", "FR-10", "Фильтр после изменения статуса через «Изменить»", "Тестирование переходов состояний",
      "«Статус» = «В работе» (видна одна задача) → выбрать её → «Изменить» → статус «Выполнено» → «Сохранить»",
      "Задача сразу исчезает из выборки «В работе»")
def tc27(s):
    app = s.start(DEMO)
    app.choose("Статус:", "В работе")
    app.edit(DEMO[0]["title"], {F_STATUS: "Выполнено"})
    app.shot()
    rows = [(r[0], r[4]) for r in app.rows()]
    actual = "Выборка пуста" if not rows else f"Под фильтром «В работе» осталась строка со статусом «{rows[0][1]}»"
    return actual, not rows


@test("TC-28", "FR-10, FR-07", "Фильтр после «Отметить выполненной»", "Тестирование переходов состояний",
      "«Статус» = «Не начато» (видны две задачи) → выбрать первую → «Отметить выполненной»",
      "Отмеченная задача сразу исчезает из выборки «Не начато», остаётся одна строка")
def tc28(s):
    app = s.start(DEMO)
    app.choose("Статус:", "Не начато")
    app.select(DEMO[1]["title"])
    app.press("Отметить выполненной")
    statuses = [r[4] for r in app.rows()]
    return f"Под фильтром «Не начато» строк: {len(statuses)}, статусы: {quoted(statuses)}", statuses == ["Не начато"]


@test("TC-29", "FR-10, FR-02", "Фильтр после добавления задачи", "Тестирование переходов состояний",
      "«Статус» = «В работе» → «Добавить» задачу со статусом «Не начато»",
      "Новая задача не показывается, пока действует фильтр «В работе»; в файле она есть")
def tc29(s):
    app = s.start(DEMO)
    app.choose("Статус:", "В работе")
    app.add({F_TITLE: "Новая задача", F_DATE: FUTURE, F_STATUS: "Не начато"})
    return f"В выборке: {quoted(app.titles())}; в файле задач: {len(app.stored())}", "Новая задача" not in app.titles() and len(app.stored()) == 4


# ======================================================================
#  FR-11: sorting
# ======================================================================

@test("TC-30", "FR-11", "Сортировка по сроку через границу месяца и года", "Анализ граничных значений",
      "Задачи со сроками 30.09.2026, 01.10.2026, 15.09.2026, 01.01.2027, 31.12.2026 → «Сортировка» = «По сроку»",
      "Порядок календарный: 15.09.2026, 30.09.2026, 01.10.2026, 31.12.2026, 01.01.2027")
def tc30(s):
    dates = ["30.09.2026", "01.10.2026", "15.09.2026", "01.01.2027", "31.12.2026"]
    app = s.start([task(f"Срок {d}", d, status="Выполнено") for d in dates])
    app.choose("Сортировка:", "По сроку")
    app.shot()
    shown = [row[2] for row in app.rows()]
    right = sorted(dates, key=lambda d: datetime.strptime(d, "%d.%m.%Y"))
    return f"Порядок в таблице: {', '.join(shown)}", shown == right


@test("TC-31", "Раздел 1.5 ТЗ", "Сортировка по приоритету", "Эквивалентное разбиение",
      "Задачи с приоритетами «Низкий», «Высокий», «Средний» → «Сортировка» = «По приоритету»",
      "Порядок от высокого к низкому (направление в ТЗ не задано, принято как естественное)")
def tc31(s):
    app = s.start([task(f"Приоритет {p}", FUTURE, priority=p) for p in ("Низкий", "Высокий", "Средний")])
    app.choose("Сортировка:", "По приоритету")
    shown = [row[3] for row in app.rows()]
    return f"Порядок в таблице: {', '.join(shown)}", shown == ["Высокий", "Средний", "Низкий"]


@test("TC-32", "FR-11, FR-05", "Сортировка после изменения срока", "Тестирование переходов состояний",
      "Сроки 10, 20 и 25 число одного месяца, «Сортировка» = «По сроку» → у первой задачи изменить срок на 28 число",
      "Таблица сразу перестраивается: изменённая задача становится последней")
def tc32(s):
    month = (TODAY.replace(day=1) + 62 * DAY).strftime("%m.%Y")
    app = s.start([task(f"Задача {d}", f"{d}.{month}") for d in ("10", "20", "25")])
    app.choose("Сортировка:", "По сроку")
    app.edit("Задача 10", {F_DATE: f"28.{month}"})
    shown = [row[2][:2] for row in app.rows()]
    return f"Порядок сроков в таблице (числа месяца): {', '.join(shown)}", shown == ["20", "25", "28"]


# ======================================================================
#  FR-12: overdue tasks
# ======================================================================

def overdue_view(s, deadline, status="Не начато"):
    app = s.start([task("Проверяемая задача", deadline, status), task("Далёкая задача", FUTURE)])
    return app, "Проверяемая задача" in app.highlighted(), app.stats()["Просрочено"]


@test("TC-33", "FR-12", "Срок — вчера, задача не выполнена", "Анализ граничных значений",
      "Запустить приложение с задачей «Не начато», срок которой — вчерашняя дата",
      "Задача просрочена: строка выделена цветом, «Просрочено: 1»")
def tc33(s):
    app, marked, counter = overdue_view(s, fmt(TODAY - DAY))
    return f"Строка выделена: {'да' if marked else 'нет'}; «Просрочено: {counter}»", marked and counter == 1


@test("TC-34", "FR-12", "Срок — сегодня, задача не выполнена", "Анализ граничных значений",
      "Запустить приложение с задачей «Не начато», срок которой — сегодняшняя дата",
      "Задача не просрочена: строка не выделена, «Просрочено: 0»")
def tc34(s):
    app, marked, counter = overdue_view(s, fmt(TODAY))
    app.shot()
    return f"Строка выделена как просроченная: {'да' if marked else 'нет'}; «Просрочено: {counter}»", not marked and counter == 0


@test("TC-35", "FR-12", "Срок — завтра; срок — вчера, но задача выполнена", "Анализ граничных значений",
      "Запустить приложение с задачей со сроком на завтра; затем с выполненной задачей со сроком вчера",
      "В обоих случаях задача не просрочена: выделения нет, «Просрочено: 0»")
def tc35(s):
    _, marked1, counter1 = overdue_view(s, fmt(TODAY + DAY))
    _, marked2, counter2 = overdue_view(s, fmt(TODAY - DAY), "Выполнено")
    ok = not marked1 and not marked2 and counter1 == 0 and counter2 == 0
    return f"Завтра: выделена — {'да' if marked1 else 'нет'}, счётчик {counter1}; выполненная: выделена — {'да' if marked2 else 'нет'}, счётчик {counter2}", ok


@test("TC-36", "FR-12, FR-07, FR-13", "Просроченная задача отмечается выполненной", "Тестирование переходов состояний",
      "Задача со сроком вчера (выделена, «Просрочено: 1») → выбрать → «Отметить выполненной»",
      "Сразу: выделение снято, «Выполнено: 1», «Просрочено: 0»")
def tc36(s):
    app, _, _ = overdue_view(s, fmt(TODAY - DAY))
    app.select("Проверяемая задача")
    app.press("Отметить выполненной")
    app.shot()
    marked, stats = "Проверяемая задача" in app.highlighted(), app.stats()
    ok = not marked and stats["Выполнено"] == 1 and stats["Просрочено"] == 0
    return f"Статус в таблице «{app.rows()[0][4]}», строка выделена: {'да' if marked else 'нет'}; статистика: Выполнено {stats['Выполнено']}, Просрочено {stats['Просрочено']}", ok


# ======================================================================
#  FR-13: statistics
# ======================================================================

MIXED = [task("Выполненная", FUTURE, "Выполнено"), task("Просроченная", fmt(TODAY - 3 * DAY), "В работе"),
         task("Обычная", FUTURE, "Не начато")]


@test("TC-37", "FR-13", "Статистика при запуске", "Тестирование вариантов использования",
      "Запустить приложение с тремя задачами: одна выполнена, одна просрочена, одна обычная",
      "«Всего: 3  Выполнено: 1  Просрочено: 1»")
def tc37(s):
    stats = s.start(MIXED).stats()
    return f"Всего {stats['Всего']}, Выполнено {stats['Выполнено']}, Просрочено {stats['Просрочено']}", stats == {"Всего": 3, "Выполнено": 1, "Просрочено": 1}


@test("TC-38", "FR-13", "Статистика после добавления и удаления", "Тестирование переходов состояний",
      "Добавить задачу; затем удалить последнюю задачу списка",
      "После добавления «Всего: 4», после удаления снова «Всего: 3» — без перезапуска")
def tc38(s):
    app = s.start(MIXED)
    app.add({F_TITLE: "Четвёртая", F_DATE: FUTURE})
    after_add = app.stats()["Всего"]
    app.delete("Четвёртая")
    after_delete = app.stats()["Всего"]
    return f"После добавления: Всего {after_add}; после удаления: Всего {after_delete}", (after_add, after_delete) == (4, 3)


@test("TC-39", "FR-13, FR-07", "Статистика после «Отметить выполненной»", "Тестирование переходов состояний",
      "«Выполнено: 1» → выбрать задачу «Обычная» → «Отметить выполненной»",
      "Счётчик сразу показывает «Выполнено: 2»")
def tc39(s):
    app = s.start(MIXED)
    app.select("Обычная")
    app.press("Отметить выполненной")
    app.shot()
    shown = app.stats()["Выполнено"]
    app = s.restart()
    return f"Сразу после действия: «Выполнено: {shown}»; после перезапуска приложения: «Выполнено: {app.stats()['Выполнено']}»", shown == 2


@test("TC-40", "FR-13, FR-05", "Статистика после изменения статуса через «Изменить»", "Тестирование переходов состояний",
      "«Выполнено: 1, Просрочено: 1» → выбрать «Просроченная» → «Изменить» → статус «Выполнено» → «Сохранить»",
      "Счётчики сразу показывают «Выполнено: 2», «Просрочено: 0»")
def tc40(s):
    app = s.start(MIXED)
    app.edit("Просроченная", {F_STATUS: "Выполнено"})
    stats = app.stats()
    return f"Сразу после сохранения: Выполнено {stats['Выполнено']}, Просрочено {stats['Просрочено']}", stats["Выполнено"] == 2 and stats["Просрочено"] == 0


# ======================================================================
#  FR-14 and reliability: data file
# ======================================================================

@test("TC-41", "FR-14", "Сохранение между запусками", "Тестирование вариантов использования",
      "Добавить задачу, изменить другую, закрыть окно, запустить приложение снова",
      "После перезапуска в таблице те же задачи с теми же значениями")
def tc41(s):
    app = s.start(DEMO)
    app.add({F_TITLE: "Переживёт перезапуск", F_DATE: FUTURE})
    app.edit(DEMO[2]["title"], {F_PRIORITY: "Высокий"})
    before = app.stored()
    app = s.restart()
    shown = [dict(zip(("title", "subject", "deadline", "priority", "status"), row)) for row in app.rows()]
    return f"После перезапуска строк: {len(shown)}; данные {'совпадают' if shown == before else 'НЕ совпадают'} с сохранёнными", shown == before and len(shown) == 4


@test("TC-42", "NFR (файл данных)", "Первый запуск без файла данных", "Предположение об ошибках",
      "Удалить папку data и запустить приложение",
      "Приложение запускается с пустым списком; папка data и файл tasks.json создаются автоматически")
def tc42(s):
    app = s.start(no_data=True)
    exists = os.path.exists(os.path.join(s.workdir, "data", "tasks.json"))
    return f"Запуск успешен, строк: {len(app.rows())}; файл создан: {'да' if exists else 'нет'}", not app.rows() and exists


@test("TC-43", "NFR (файл данных)", "Повреждённый файл данных", "Предположение об ошибках",
      "Записать в data\\tasks.json обрывок «[{\"title\": \"Важная» (некорректный JSON), запустить приложение, добавить задачу",
      "Приложение не завершается аварийно, сообщает о проблеме с файлом и не уничтожает его содержимое без ведома пользователя")
def tc43(s):
    broken = '[{"title": "Важная'
    try:
        app = s.start(raw=broken)
    except StartError as error:
        return f"Приложение не запустилось: {error}", False
    messages = [m[2] for m in app.messages]
    app.add({F_TITLE: "После сбоя", F_DATE: FUTURE})
    with open(os.path.join(s.workdir, "data", "tasks.json"), encoding="utf-8") as file:
        lost = broken not in file.read()
    start = f"При запуске показано сообщение: {quoted(messages)}" if messages else "Запуск без каких-либо сообщений, список пуст"
    actual = start + "; после добавления задачи прежнее содержимое файла " + ("перезаписано без предупреждения" if lost else "сохранено")
    return actual, bool(messages) and not lost


@test("TC-44", "NFR (файл данных)", "Файл данных с неполной записью", "Предположение об ошибках",
      "Записать в data\\tasks.json корректный JSON с задачей без поля срока: [{\"title\": \"Без срока\"}], запустить приложение",
      "Приложение запускается (запись пропускается или показывается с пустыми полями), аварийного завершения нет")
def tc44(s):
    try:
        app = s.start(raw='[{"title": "Без срока"}]')
    except StartError as error:
        return f"Приложение не запускается, окно не появляется: необработанная ошибка {error}", False
    return f"Запуск успешен, строк в таблице: {len(app.rows())}", True


# ======================================================================
#  FR-15: long and unusual titles
# ======================================================================

@test("TC-45", "FR-15", "Очень длинное название", "Анализ граничных значений",
      "«Добавить» → название из 300 символов → «Сохранить» → выбрать эту задачу в таблице",
      "Название отображается корректно: переносится или аккуратно обрезается в пределах окна; размеры окна и расположение элементов не меняются")
def tc45(s):
    app = s.start(DEMO)
    size_before = (app.root.winfo_width(), app.root.winfo_height())
    long_title = ("Очень длинное название учебной задачи " * 8)[:300]
    app.add({F_TITLE: long_title, F_DATE: FUTURE})
    app.select(long_title)
    app.shot()
    label = app.details_label()
    need, have = label.winfo_reqwidth(), app.root.winfo_width()
    wraps = str(label.cget("wraplength")) not in ("", "0")
    same_size = (app.root.winfo_width(), app.root.winfo_height()) == size_before
    actual = (f"В области «Выбранная задача» название выводится одной строкой без переноса: тексту нужно {need} px "
              f"при ширине окна {have} px, правая часть названия не видна; размеры окна "
              + ("не изменились" if same_size else "ИЗМЕНИЛИСЬ"))
    return actual, (need <= have or wraps) and same_size


@test("TC-46", "FR-02, FR-14", "Специальные символы в названии", "Предположение об ошибках",
      "«Добавить» → название «<b>\"Тест\"</b> & 'x' \\ / №1 ✓» → «Сохранить» → перезапустить приложение",
      "Название сохраняется и показывается без искажений, файл данных остаётся корректным")
def tc46(s):
    title = "<b>\"Тест\"</b> & 'x' \\ / №1 ✓"
    app = s.start(DEMO)
    app.add({F_TITLE: title, F_DATE: FUTURE})
    app = s.restart()
    return f"После перезапуска название в таблице {'совпадает' if title in app.titles() else 'НЕ совпадает'} с введённым", title in app.titles()


# ======================================================================
#  Running
# ======================================================================

def environment(product_dir):
    with open(os.path.join(product_dir, MODULE_FILE), "rb") as file:
        digest = hashlib.sha256(file.read()).hexdigest()
    root = tk.Tk()
    root.withdraw()
    modified = datetime.fromtimestamp(os.path.getmtime(os.path.join(product_dir, MODULE_FILE)))
    info = {
        "Дата прогона": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "Операционная система": f"{platform.system()} {platform.release()} (сборка {platform.version()})",
        "Python": platform.python_version(),
        "Tk": str(root.tk.call("info", "patchlevel")),
        "Экран": f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}, масштаб {round(ctypes.windll.user32.GetDpiForSystem() / 96 * 100)}%",
        "Файл продукта": f"{MODULE_FILE}, изменён {modified.strftime('%d.%m.%Y %H:%M')}, SHA-256 {digest[:16]}…",
    }
    root.destroy()
    return info


def main(product_dir, out_dir):
    ctypes.windll.shcore.SetProcessDpiAwareness(1)   # screen coordinates and screenshots in real pixels
    shots_dir = os.path.join(out_dir, "screens")
    os.makedirs(shots_dir, exist_ok=True)
    env = environment(product_dir)

    results = []
    for case in TESTS:
        session = Session(product_dir, shots_dir, case["id"])
        try:
            actual, passed = case["run"](session)
            status = "Passed" if passed else "Failed"
        except Exception as error:          # the test itself could not be carried out
            actual, status = f"Тест не выполнен: {type(error).__name__}: {error}", "Blocked"
        problems = session.app.problems if session.app is not None else []
        session.remove()
        record = {key: case[key] for key in ("id", "requirement", "title", "technique", "steps", "expected")}
        record.update({"actual": actual, "status": status, "screens": session.shots, "problems": problems})
        results.append(record)
        print(f"{case['id']}  {status:<7} {case['title']}")

    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as file:
        json.dump({"environment": env, "tests": results}, file, ensure_ascii=False, indent=2)

    lines = ["ПРОТОКОЛ АВТОМАТИЗИРОВАННОГО ПРОГОНА ТЕСТОВ", "Объект: Student Task Manager", ""]
    lines += [f"{key}: {value}" for key, value in env.items()] + [""]
    for r in results:
        lines += [f"{r['id']} [{r['requirement']}] {r['title']}",
                  f"  техника:   {r['technique']}",
                  f"  шаги:      {r['steps']}",
                  f"  ожидалось: {r['expected']}",
                  f"  получено:  {r['actual']}",
                  f"  статус:    {r['status']}" + (f"   снимки: {', '.join(r['screens'])}" if r["screens"] else ""), ""]
    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("Passed", "Failed", "Blocked")}
    lines.append(f"ИТОГО: тестов {len(results)}, Passed {counts['Passed']}, Failed {counts['Failed']}, Blocked {counts['Blocked']}")
    with open(os.path.join(out_dir, "protocol.txt"), "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    print(lines[-1])


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]))
