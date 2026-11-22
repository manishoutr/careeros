"""Resume parsing.

Two paths, one contract:
* Claude path (when a key is configured): the Messages API extracts structured
  data, which is validated against ProfileData before use.
* Offline path: transparent heuristics - a skills lexicon, section headers,
  and "Title at Company (period)" experience lines.

The heuristics are intentionally simple and documented: parsing accuracy is a
measured, honest limitation, and the UI lets the user correct every field.
"""
import io
import re
from typing import List, Optional

from ..schemas import EducationItem, ExperienceItem, ProfileData
from .llm import llm

# Lexicon of skills we recognise offline. Extending this list is the
# documented way to improve offline parsing recall.
SKILLS_LEXICON = [
    "python", "java", "javascript", "typescript", "c++", "c#", "c", "go", "rust",
    "kotlin", "swift", "php", "ruby", "r", "matlab", "scala",
    "sql", "postgresql", "mysql", "sqlite", "mongodb", "redis", "elasticsearch",
    "react", "next.js", "node.js", "express", "fastapi", "django", "flask",
    "spring", "rails", ".net",
    "html", "css", "tailwind", "bootstrap",
    "docker", "kubernetes", "terraform", "aws", "gcp", "azure", "ci/cd",
    "git", "github", "linux", "bash",
    "machine learning", "deep learning", "nlp", "computer vision",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "spark", "hadoop", "kafka", "airflow",
    "graphql", "rest", "microservices", "system design",
    "data structures", "algorithms", "oop", "testing", "pytest", "selenium",
    "excel", "power bi", "tableau", "figma", "jira", "agile",
]

_SECTION_RE = re.compile(
    r"^\s*(experience|work experience|employment|education|skills|projects|"
    r"summary|profile|certifications?)\s*:?\s*$", re.IGNORECASE)

_EXP_LINE_RE = re.compile(
    r"^(?P<title>[^(),|@]+?)\s*(?:@|at|,|\|)\s*(?P<company>[^()|]+?)"
    r"(?:\s*\((?P<period>[^)]*)\))?\s*$")

_DEGREE_RE = re.compile(
    r"\b(b\.?tech|b\.?e\.?|b\.?sc|m\.?tech|m\.?sc|mca|bca|mba|ph\.?d|"
    r"bachelor|master|diploma|high school|intermediate|class\s*x{1,2})\b",
    re.IGNORECASE)

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def extract_text(file_bytes: bytes, filename: str) -> str:
    """PDF via pypdf; TXT/MD decoded as UTF-8. Anything else is rejected
    by the API layer before we get here."""
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return file_bytes.decode("utf-8", errors="replace")


def _years_from_period(period: str) -> float:
    """Estimate years of experience from a period string.
    Handles '(2 years)', '(Jun 2024 - Aug 2025)', '(2023 - Present)'."""
    if not period:
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+?\s*)(?:years?|yrs?)", period, re.I)
    if m:
        return float(m.group(1))
    dates = re.findall(
        r"(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?(\d{4})",
        period.lower())
    if len(dates) >= 2:
        (m1, y1), (m2, y2) = dates[0], dates[-1]
        start = int(y1) * 12 + _MONTHS.get(m1[:3], 1)
        end_word = period.lower()
        if "present" in end_word or "current" in end_word:
            import datetime
            now = datetime.date.today()
            end = now.year * 12 + now.month
        else:
            end = int(y2) * 12 + _MONTHS.get(m2[:3], 12)
        return round(max(0, end - start) / 12.0, 1)
    return 0.0


def _split_sections(lines: List[str]) -> dict:
    sections: dict = {"__header__": []}
    current = "__header__"
    for line in lines:
        if _SECTION_RE.match(line):
            current = _SECTION_RE.match(line).group(1).lower()
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def parse_resume_text(text: str) -> ProfileData:
    """Deterministic offline parser. Also used as the fallback when Claude
    output fails validation."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    sections = _split_sections(lines)

    name = sections["__header__"][0] if sections["__header__"] else ""

    lowered = text.lower()
    skills = sorted({s for s in SKILLS_LEXICON
                     if re.search(r"(?<![a-z0-9+#.])" + re.escape(s) + r"(?![a-z0-9])", lowered)})

    experience: List[ExperienceItem] = []
    exp_lines = sections.get("experience") or sections.get("work experience") or []
    for ln in exp_lines:
        if ln.startswith(("-", "*", "•")):
            continue  # bullet detail lines stay out of the structured entry
        m = _EXP_LINE_RE.match(ln)
        if m and len(m.group("title")) < 80:
            period = (m.group("period") or "").strip()
            experience.append(ExperienceItem(
                title=m.group("title").strip(" -"),
                company=m.group("company").strip(" -"),
                period=period,
                years=_years_from_period(period),
            ))

    education: List[EducationItem] = []
    edu_lines = sections.get("education") or []
    for ln in edu_lines:
        if _DEGREE_RE.search(ln):
            parts = re.split(r"\s*[-,|]\s*", ln)
            education.append(EducationItem(
                degree=parts[0].strip(),
                institution=parts[1].strip() if len(parts) > 1 else "",
                year=(re.search(r"(19|20)\d{2}", ln) or [""])[0]
                     if re.search(r"(19|20)\d{2}", ln) else "",
            ))
    # Fallback: scan the whole document if no education section matched.
    if not education:
        for ln in lines:
            if _DEGREE_RE.search(ln):
                education.append(EducationItem(degree=ln.strip(), institution="", year=""))
                break

    return ProfileData(name=name, skills=skills, experience=experience,
                       education=education)


_EXTRACTION_SYSTEM = (
    "You extract structured candidate data from resumes. Return only fields "
    "that are explicitly present in the text. Never invent skills, employers, "
    "qualifications or achievements. Use the exact JSON shape requested.")


def parse_resume(text: str) -> ProfileData:
    """Claude-first parsing with schema validation, offline fallback."""
    prompt = (
        "Extract the candidate profile from this resume as JSON with keys: "
        "name (string), skills (list of strings), experience (list of "
        "{title, company, period, years}), education (list of {degree, "
        "institution, year}), preferences ({locations: [], roles: []}). "
        "Only include information stated in the resume.\n\nRESUME:\n" + text[:12000])
    result = llm.complete_json(_EXTRACTION_SYSTEM, prompt, ProfileData)
    if result is not None:
        return result
    return parse_resume_text(text)
