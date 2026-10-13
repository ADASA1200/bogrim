"""בדיקה ל-regression של תקלה אמיתית שנצפתה ב-Windows: pywebview בונה את
ה-API שחשוף ל-JS (window.pywebview.api) על ידי סריקה רקורסיבית (reflection)
של כל התכונות הלא-קריאות באובייקט ה-js_api, ומדלג באופן מפורש על שמות
שמתחילים ב-_ (ראו webview/util.py::inject_pywebview, שבדיוק הפונקציה
_walk_like_pywebview למטה משכפלת במדויק). לפני התיקון, HostAPI/ViewerAPI
חשפו webview.Window האמיתי בתכונה בשם win (לא _win) - בצד Windows זה גרם
לסריקה לרדת לתוך ה-Form הגולמי (win.native) ועד לעץ ה-Accessibility/COM
שלו, ולהיתקע ב-RecursionError אמיתי כי תכונות כמו Rectangle.Empty מחזירות
אובייקט *חדש* בכל קריאה - כך שההגנה מפני מעגלים לפי id() אף פעם לא נדלקת.
"""
from __future__ import annotations

import inspect

from rdesk.aio import AsyncRunner
from rdesk.capture import SyntheticScreen
from rdesk.inject import NullInjector
from rdesk import webapp


def _walk_like_pywebview(obj, base_name: str = "", functions=None, exposed_objects=None, calls=None):
    """שכפול מדויק של get_functions() הפנימית ב-webview/util.py::inject_pywebview -
    אותה לוגיקת רקורסיה, אותה הגנת-מעגלים לפי id(), ואותו try/except שתופס
    וממשיך בלי לקרוס (זה בדיוק מה שמסביר למה ההודעות המקוריות הופיעו
    כ-ERROR רשום ולא כקריסה חד-משמעית של כל התהליך). calls הוא מונה שמספר
    כמה פעמים הפונקציה קראה לעצמה בפועל - הדרך הנכונה לבדוק "האם זה נכנס
    לרקורסיה כבדה" בלי להסתמך על חריגה חמקמקה שתלויה ב-sys.setrecursionlimit
    הנוכחי, כדי שלא לבדוק בלי תלות בחלון pywebview אמיתי (שלא קיים בכלל
    בסנדבוקס לינוקס הזה)."""
    if functions is None:
        functions = {}
    if exposed_objects is None:
        exposed_objects = []
    if calls is None:
        calls = [0]
    calls[0] += 1
    if calls[0] > 10_000:   # תחליף בטוח ל-RecursionError האמיתי, בלי לגעת ב-sys.setrecursionlimit
        return functions

    obj_id = id(obj)
    if obj_id in exposed_objects:
        return functions
    exposed_objects.append(obj_id)

    for name in dir(obj):
        full_name = f"{base_name}.{name}" if base_name else name
        try:
            if name.startswith("_"):
                continue
            attr = getattr(obj, name)
            if inspect.ismethod(attr) or inspect.isfunction(attr):
                functions[full_name] = True
            elif inspect.isclass(attr) or (isinstance(attr, object) and not callable(attr) and hasattr(attr, "__module__")):
                _walk_like_pywebview(attr, full_name, functions, exposed_objects, calls)
        except Exception:
            continue
    return functions


class _PathologicalNative:
    """מדמה תכונת .NET כמו Rectangle.Empty: מחזירה בכל קריאה מופע *חדש*,
    כך שההגנה לפי id() של pywebview אף פעם לא תופסת את המעגל."""

    @property
    def Empty(self):
        return _PathologicalNative()


def test_walker_recurses_unboundedly_into_a_public_attribute():
    """מוכיח שהמנגנון שגרם לתקלה האמיתית אכן קיים: תכונה פומבית (בלי _)
    שמחזיקה אובייקט פתולוגי כזה (כמו Rectangle.Empty האמיתי) גורמת לסריקה
    להיכנס לרקורסיה בלתי-חסומה - בדיוק כמו שקרה בפועל עם
    win.native.AccessibilityObject.Bounds.Empty.Empty.Empty... (ו-pywebview
    האמיתי תופס וממשיך בלי להתרסק, בדיוק כמו ה-try/except כאן, אבל רק אחרי
    שבוזבז זמן/CPU משמעותי - זה ה"כבד" שתואר)."""
    class FakeApiWithPublicWindow:
        def __init__(self):
            self.win = _PathologicalNative()  # בכוונה: בלי קו תחתי, מדגים את התקלה

    calls = [0]
    _walk_like_pywebview(FakeApiWithPublicWindow(), calls=calls)
    # לא מגיע כלל להתקרה המלאכותית (10,000) - ה-RecursionError האמיתי של
    # פייתון נתפס קודם, בכל רמה, ע"י ה-try/except (בדיוק כמו בלוג האמיתי:
    # "ERROR pywebview: Error while processing ...: maximum recursion depth
    # exceeded"), מה שממחיש כמה רמות עומק זה בכל זאת מספיק לבזבז לפני שנתפס.
    assert calls[0] > 900


def test_walker_skips_underscore_prefixed_window_attribute():
    """התיקון: אותו אובייקט פתולוגי, אבל מאחורי שם שמתחיל ב-_ (כמו _win
    ב-HostAPI/ViewerAPI האמיתיים) - הסריקה חייבת לדלג עליו לגמרי ולא לקרוס."""
    class FakeApiWithPrivateWindow:
        def __init__(self):
            self._win = _PathologicalNative()

    calls = [0]
    functions = _walk_like_pywebview(FakeApiWithPrivateWindow(), calls=calls)
    assert functions == {}
    assert calls[0] == 1   # רק הקריאה החיצונית - אף פעם לא ירד לתוך _win


def _make_host_api(tmp_path, runner, monkeypatch):
    monkeypatch.setattr(webapp.config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(webapp.config, "CONFIG_FILE", tmp_path / "config.json")
    webapp.config.save({"id": "135791357"})
    return webapp.HostAPI(None, runner, injector=NullInjector(), screen=SyntheticScreen())


def test_real_host_api_window_attribute_is_never_walked(tmp_path, monkeypatch):
    """בדיקה על המחלקה האמיתית (HostAPI): גם כשיש חלון "אמיתי" (מדומה כאן
    בפתולוגי) מוצמד ל-_win כמו שקורה בפועל ב-open_host_window, הסריקה
    שה-API חושף ל-JS לא נוגעת בו ולא קורסת."""
    runner = AsyncRunner()
    try:
        api = _make_host_api(tmp_path, runner, monkeypatch)
        api._win = _PathologicalNative()
        functions = _walk_like_pywebview(api)
        assert "getState" in functions  # שיטות JS-API אמיתיות עדיין נחשפות כרגיל
        assert not any("native" in name.lower() or "Empty" in name for name in functions)
    finally:
        runner.stop()


def test_real_viewer_api_window_attribute_is_never_walked():
    runner = AsyncRunner()
    try:
        api = webapp.ViewerAPI(runner, preset=None)
        api._win = _PathologicalNative()
        functions = _walk_like_pywebview(api)
        assert "viewerConnect" in functions
        assert not any("native" in name.lower() or "Empty" in name for name in functions)
    finally:
        runner.stop()
