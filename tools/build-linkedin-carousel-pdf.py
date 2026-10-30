from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "artifacts" / "linkedin-carousel-landscape"
OUTPUT = ROOT / "output" / "pdf" / "sql-copilot-linkedin-carousel-light.pdf"
PAGE_WIDTH = 960
PAGE_HEIGHT = 540


def wrap(text: str, font: str, size: int, max_width: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        proposal = word if not current else f"{current} {word}"
        if stringWidth(proposal, font, size) <= max_width:
            current = proposal
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_text_block(pdf: canvas.Canvas, text: str, x: float, y: float, width: float, font: str, size: int, color, leading: int):
    pdf.setFont(font, size)
    pdf.setFillColor(color)
    for line in wrap(text, font, size, width):
        pdf.drawString(x, y, line)
        y -= leading
    return y


def cover(pdf: canvas.Canvas):
    pdf.setFillColor(HexColor("#f8fbff"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#e0f7fb"))
    pdf.circle(845, 435, 178, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#e8e5ff"))
    pdf.circle(875, 115, 128, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#0e294a"))
    pdf.roundRect(70, 389, 92, 92, 23, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#56e1f3"))
    pdf.circle(116, 435, 24, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#15233d"))
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(70, 344, "SQL Copilot")
    pdf.setFillColor(HexColor("#0d1b34"))
    pdf.setFont("Helvetica-Bold", 42)
    pdf.drawString(70, 286, "From business question")
    pdf.drawString(70, 236, "to reviewed SQL")
    draw_text_block(
        pdf,
        "A schema-aware workspace that combines structured generation, validation, and a clear review trail.",
        70,
        188,
        560,
        "Helvetica",
        17,
        HexColor("#48617d"),
        24,
    )
    cards = [
        ("Schema-aware", "Business terms, tables, and relationships"),
        ("7-step review", "Context, planning, validation, and response"),
        ("Production-ready", "Cloudflare frontend and Oracle API"),
    ]
    x = 70
    for title, detail in cards:
        pdf.setFillColor(white)
        pdf.roundRect(x, 60, 245, 76, 14, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#102647"))
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(x + 16, 108, title)
        draw_text_block(pdf, detail, x + 16, 87, 214, "Helvetica", 9.5, HexColor("#60748e"), 13)
        x += 265
    pdf.showPage()


def screenshot_slide(pdf: canvas.Canvas, image_path: Path):
    image = ImageReader(str(image_path))
    pdf.drawImage(image, 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT, preserveAspectRatio=True, mask="auto")
    pdf.showPage()


def closing(pdf: canvas.Canvas):
    pdf.setFillColor(HexColor("#f8fbff"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#e7fbff"))
    pdf.circle(120, 410, 120, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#e9e4ff"))
    pdf.circle(840, 120, 170, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#0d1b34"))
    pdf.setFont("Helvetica-Bold", 38)
    pdf.drawString(70, 382, "Built for clear, trusted")
    pdf.drawString(70, 336, "data exploration")
    bullets = [
        "Plain-language questions to read-only SQL",
        "NVIDIA structured generation with schema grounding",
        "Visible review scorecard and seven-stage workflow",
        "SQL Repair for syntax and connection troubleshooting",
    ]
    y = 270
    for item in bullets:
        pdf.setFillColor(HexColor("#12b9d3"))
        pdf.circle(80, y + 4, 5, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#344d69"))
        pdf.setFont("Helvetica", 16)
        pdf.drawString(98, y, item)
        y -= 39
    pdf.setFillColor(HexColor("#0e294a"))
    pdf.roundRect(70, 58, 820, 57, 16, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(95, 82, "Try it live: sql-copilot.pages.dev")
    pdf.setFont("Helvetica", 13)
    pdf.drawRightString(865, 82, "github.com/shasanksingh/sql-copilot")
    pdf.showPage()


def main():
    review = SCREENSHOTS / "02-query-review-xai-light-landscape.png"
    repair = SCREENSHOTS / "03-sql-repair-light-landscape.png"
    missing = [str(path) for path in (review, repair) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing screenshots: {', '.join(missing)}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(OUTPUT), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.setTitle("SQL Copilot - LinkedIn carousel")
    pdf.setAuthor("Shashank Singh")
    cover(pdf)
    screenshot_slide(pdf, review)
    screenshot_slide(pdf, repair)
    closing(pdf)
    pdf.save()
    print(OUTPUT)


if __name__ == "__main__":
    main()
