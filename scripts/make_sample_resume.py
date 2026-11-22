"""Generate sample_data/sample_resume.pdf for the demo path.

Run: python scripts/make_sample_resume.py
The PDF is a fake candidate - the demo never touches real personal data.
The same content lives in sample_data/sample_resume.txt so the parser's
behaviour can be tested without PDF rendering in the loop.
"""
from pathlib import Path

SAMPLE_TEXT = """Aarav Sharma
Bhubaneswar, India | aarav.sharma@example.com

Skills
Python, FastAPI, PostgreSQL, Docker, React, JavaScript, Git, Linux, Pandas, SQL, Machine Learning, Redis

Experience
Backend Intern at Odisha Web Works (Jun 2025 - Aug 2025)
- Built FastAPI endpoints backed by PostgreSQL for a college events app
- Wrote pytest suites that caught regressions before release
Open Source Contributor at CampusDev Club (Jan 2025 - Present)
- Reviewed pull requests and fixed bugs in a React dashboard

Education
B.Tech Computer Science, Odisha University of Technology and Research, 2027
"""


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "sample_data"
    out.mkdir(exist_ok=True)
    (out / "sample_resume.txt").write_text(SAMPLE_TEXT, encoding="utf-8")

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(out / "sample_resume.pdf"), pagesize=A4)
    width, height = A4
    y = height - 60
    for line in SAMPLE_TEXT.splitlines():
        if y < 60:
            pdf.showPage()
            y = height - 60
        pdf.drawString(60, y, line)
        y -= 16
    pdf.save()
    print(f"wrote {out / 'sample_resume.pdf'} and sample_resume.txt")


if __name__ == "__main__":
    main()
