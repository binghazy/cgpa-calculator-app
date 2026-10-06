"""Lossless workbook inspection and validated transcript import."""
from io import BytesIO
from pathlib import Path
import math
import re
import sys

# Supports the project-local installation used by the development launcher.
LOCAL_DEPS = Path(__file__).resolve().parent / ".deps"
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))

from openpyxl import load_workbook

GRADE_POINTS = {"A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0,
                "B-": 2.7, "C+": 2.3, "C": 2.0, "C-": 1.7, "D+": 1.3,
                "D": 1.0, "F": 0.0}
GRADE_OPTIONS = list(GRADE_POINTS) + ["P"]


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def validate_course(code, credits, grade):
    code = str(code or "").strip()
    grade = str(grade or "").strip().upper().replace("−", "-")
    if not code:
        raise ValueError("Course code is required.")
    if grade not in GRADE_OPTIONS:
        raise ValueError(f"{code}: unsupported grade {grade!r}.")
    try:
        credits = float(credits)
    except (TypeError, ValueError):
        raise ValueError(f"{code}: credits must be a number.") from None
    if not math.isfinite(credits) or credits < 0:
        raise ValueError(f"{code}: credits must be a finite, nonnegative number.")
    return {"code": code, "credits": credits, "grade": grade}


def read_transcript(source):
    """Read all sheets; preserve every raw cell and report every excluded row.

    Invalid course rows reject the import atomically. Non-course sheets remain
    available for inspection. A sheet name is the group when no term is supplied.
    """
    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    values = load_workbook(BytesIO(data), data_only=True)
    formulas = load_workbook(BytesIO(data), data_only=False)
    groups, sheets, reports, warnings, errors = {}, {}, [], [], []
    aliases = {
        "code": {"coursecode", "code", "course", "subjectcode"},
        "credits": {"creditsunits", "credits", "credithours", "units", "credit"},
        "grade": {"grade", "lettergrade"},
        "semester": {"semester", "term", "session"},
        "points": {"gradepoints", "qualitypoints"},
    }
    try:
        for sheet in values:
            raw = list(formulas[sheet.title].values)
            sheets[sheet.title] = raw
            rows = list(sheet.values)
            header = None
            mapping = {}
            for index, row in enumerate(rows):
                found = {field: next((i for i, value in enumerate(row)
                                     if normalized(value) in names), None)
                         for field, names in aliases.items()}
                if all(found[key] is not None for key in ("code", "credits", "grade")):
                    header, mapping = index, found
                    break
            count = 0
            if header is None:
                warnings.append(f"{sheet.title}: no course table found; all cells are available in Workbook data.")
            else:
                previous_term = None
                for index, row in enumerate(rows[header + 1:], header + 2):
                    if all(value is None or str(value).strip() == "" for value in row):
                        continue
                    def cell(field):
                        col = mapping[field]
                        return row[col] if col is not None else None
                    if all(normalized(cell(key)) in aliases[key] for key in ("code", "credits", "grade")):
                        warnings.append(f"{sheet.title}, row {index}: repeated header excluded.")
                        continue
                    code, credits, grade = cell("code"), cell("credits"), cell("grade")
                    location = f"{sheet.title}, row {index}"
                    if str(grade).strip().upper() == "P" and normalized(credits) in {"", "na"}:
                        credits = 0
                        warnings.append(f"{location}: pass course has no numeric credits; kept with 0 credits.")
                    try:
                        course = validate_course(code, credits, grade)
                    except ValueError as exc:
                        errors.append(f"{location}: {exc}")
                        continue
                    term = cell("semester")
                    if term is not None and str(term).strip():
                        previous_term = str(term).strip()
                    label = previous_term or sheet.title
                    course.update(source_sheet=sheet.title, source_row=index,
                                  original_credits=cell("credits"), grade_points=cell("points"))
                    points = cell("points")
                    if points is not None and course["grade"] != "P":
                        try:
                            matches = math.isclose(float(points), GRADE_POINTS[course["grade"]] * course["credits"], abs_tol=1e-7)
                        except (ValueError, TypeError):
                            matches = False
                        if not matches:
                            warnings.append(f"{location}: workbook grade points differ from the app's scale; original value retained.")
                    groups.setdefault(label, []).append(course)
                    count += 1
                if mapping["semester"] is None:
                    warnings.append(f"{sheet.title}: no semester column; courses are grouped by worksheet, without inferred dates.")
            reports.append({"Worksheet": sheet.title, "Data rows": max(0, len(rows) - (header + 1 if header is not None else 0)), "Courses imported": count})
        if errors:
            raise ValueError("Import stopped; correct these rows and retry:\n" + "\n".join(errors))
        if not groups:
            raise ValueError("No courses found. Include Course Code, Credits (Units), and Grade columns.")
        return {"semesters": [{"Semester": name, "Courses": courses} for name, courses in groups.items()],
                "sheets": sheets, "reports": reports, "warnings": warnings}
    finally:
        values.close()
        formulas.close()


def export_transcript(semesters):
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Transcript"
    sheet.append(["Semester", "Course Code", "Credits (Units)", "Grade", "Grade Points"])
    for semester in semesters:
        for course in semester["Courses"]:
            points = GRADE_POINTS.get(course["grade"])
            row = [semester["Semester"], course["code"], course["credits"], course["grade"],
                   points * course["credits"] if points is not None else None]
            sheet.append(row)
            # User-entered text must never become an Excel formula.
            for column in (1, 2, 4):
                sheet.cell(sheet.max_row, column).data_type = "s"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
