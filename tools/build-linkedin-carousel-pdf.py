from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "artifacts" / "linkedin-carousel-landscape"
ARCHITECTURE = ROOT / "assets" / "linkedin" / "sql-copilot-system-architecture.png"
OUTPUT = ROOT / "output" / "pdf" / "sql-copilot-linkedin-product-walkthrough.pdf"
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


def full_image_slide(pdf: canvas.Canvas, image_path: Path):
    image = ImageReader(str(image_path))
    pdf.drawImage(image, 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT, preserveAspectRatio=True, mask="auto")
    pdf.showPage()


def closing(pdf: canvas.Canvas):
    pdf.setFillColor(HexColor("#f8fbff"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#e1f7fb"))
    pdf.circle(118, 420, 132, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#ece8ff"))
    pdf.circle(845, 110, 172, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#0d1b34"))
    pdf.setFont("Helvetica-Bold", 38)
    pdf.drawString(70, 382, "SQL Copilot")
    pdf.setFont("Helvetica-Bold", 27)
    pdf.drawString(70, 342, "From business context to reviewed SQL")
    draw_text_block(
        pdf,
        "A schema-aware workflow for turning questions into safe, explainable SQL with visible review checkpoints.",
        70,
        296,
        610,
        "Helvetica",
        16,
        HexColor("#48617d"),
        24,
    )
    features = [
        ("Schema aware", "Business vocabulary, table mapping, relationships, and join paths"),
        ("Reviewable", "Seven workflow stages, validation, confidence, and repair guidance"),
        ("Deployed", "Cloudflare frontend, Oracle API, and NVIDIA structured generation"),
    ]
    y = 214
    for title, detail in features:
        pdf.setFillColor(HexColor("#11bad4"))
        pdf.circle(80, y + 4, 5, fill=1, stroke=0)
        pdf.setFillColor(HexColor("#102647"))
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(98, y, title)
        pdf.setFillColor(HexColor("#4a617b"))
        pdf.setFont("Helvetica", 11)
        pdf.drawString(214, y, detail)
        y -= 40
    pdf.setFillColor(HexColor("#0e294a"))
    pdf.roundRect(70, 54, 820, 58, 16, fill=1, stroke=0)
    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(96, 78, "Try it live: sql-copilot.pages.dev")
    pdf.setFont("Helvetica", 13)
    pdf.drawRightString(864, 78, "github.com/shasanksingh/sql-copilot")
    pdf.showPage()


def main():
    slides = [
        ARCHITECTURE,
        SCREENSHOTS / "00-signup-light-landscape.png",
        SCREENSHOTS / "01-dashboard-light-landscape.png",
        SCREENSHOTS / "03-schema-explorer-light-landscape.png",
        SCREENSHOTS / "04-schema-graph-light-landscape.png",
        SCREENSHOTS / "02-query-review-xai-light-landscape.png",
        SCREENSHOTS / "05-sql-repair-light-landscape.png",
    ]
    missing = [str(path) for path in slides if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing carousel inputs: {', '.join(missing)}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(OUTPUT), pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    pdf.setTitle("SQL Copilot - product walkthrough")
    pdf.setAuthor("Shashank Singh")
    for slide in slides:
        full_image_slide(pdf, slide)
    closing(pdf)
    pdf.save()
    print(OUTPUT)


if __name__ == "__main__":
    main()
