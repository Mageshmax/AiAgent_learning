"""
Lesson 7c: Vision and files (send images and PDFs to Claude).

KEY IDEA: A message's "content" does not have to be a string. It can be a
LIST OF BLOCKS, and a block can be text, an IMAGE, or a DOCUMENT (PDF / text):

    messages=[{"role": "user", "content": [
        {"type": "image",    "source": {...}},   # a picture
        {"type": "document", "source": {...}},   # a PDF or plain text
        {"type": "text",     "text": "What does this show?"},  # your question
    ]}]

Put the image / document BEFORE the question: Claude answers better that way.

Three ways to give Claude a file ("source"):
    1. base64   -> read the file, encode it as text, send it inside the request
                   {"type": "base64", "media_type": "image/png", "data": "<text>"}
    2. url      -> Anthropic downloads a PUBLIC link for you
                   {"type": "url", "url": "https://..."}
    3. file     -> upload ONCE with the Files API, then reuse the id in many calls
                   {"type": "file", "file_id": "file_..."}

Things to know:
    - Images: JPEG, PNG, GIF, WebP. Cost is about (width x height) / 750 tokens,
      so a 1000x1000 image is ~1,300 input tokens. Very large images are shrunk
      by the API anyway (long edge above ~1568 px), so resize them yourself first.
    - PDFs: Claude reads BOTH the text and a picture of every page, so charts
      and tables in a PDF work too. Each page costs text tokens + image tokens.
    - Limits: 32 MB per request, 600 PDF pages.
    - Citations: add "citations": {"enabled": True} to a document block and
      Claude tells you WHICH part of the document each sentence came from.

This lesson makes its own sample files with Pillow (already installed), so
you don't need any files of your own. They go in lesson_data/vision/.

Every demo makes real (paid) API calls; each costs about US$0.01-0.03.

Run:
    python 07c_vision_files.py          (menu)
    python 07c_vision_files.py 1        (run demo 1 only)
"""

import base64
import os
import sys
from pathlib import Path

import anthropic
from dotenv import find_dotenv, load_dotenv
from PIL import Image, ImageDraw, ImageFont

MODEL = "claude-opus-5-5"

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

DATA_DIR = Path(__file__).resolve().parent / "lesson_data" / "vision"
RECEIPT = DATA_DIR / "receipt.png"
CHART = DATA_DIR / "sales_chart.png"
REPORT_PDF = DATA_DIR / "report.pdf"

# The receipt items. Python knows the right total, so we can CHECK Claude.
RECEIPT_ITEMS = [("Filter coffee", 2, 40), ("Masala dosa", 3, 90), ("Idli (2 pcs)", 4, 35), ("Mango lassi", 2, 70)]
RECEIPT_TOTAL = sum(qty * price for _, qty, price in RECEIPT_ITEMS)

# A public image. Some sites (e.g. Wikimedia) block Anthropic's downloader and
# give a 400 "Unable to download the file"; python.org worked on 2026-09-30.
IMAGE_URL = "https://www.python.org/static/img/python-logo.png"


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def answer_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


def show(response) -> None:
    if response.stop_reason == "refusal":
        print("Claude refused this request.")
        return
    print(answer_text(response))
    print(f"\n   input tokens: {response.usage.input_tokens}  output tokens: {response.usage.output_tokens}")


# ---------------------------------------------------------------------------
# STEP A: Make the sample files (a receipt photo, a chart, a 2-page PDF).
# ---------------------------------------------------------------------------
def font(size: int):
    return ImageFont.load_default(size=size)


def make_sample_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. A shop receipt.
    img = Image.new("RGB", (520, 420), "white")
    d = ImageDraw.Draw(img)
    d.text((150, 20), "ANNAPOORNA CAFE", fill="black", font=font(26))
    d.text((170, 55), "Chennai  |  Bill #4471", fill="gray", font=font(16))
    y = 100
    for name, qty, price in RECEIPT_ITEMS:
        d.text((30, y), f"{name}", fill="black", font=font(20))
        d.text((300, y), f"{qty} x {price}", fill="black", font=font(20))
        d.text((430, y), f"{qty * price}", fill="black", font=font(20))
        y += 40
    d.line((30, y + 5, 490, y + 5), fill="black", width=2)
    d.text((30, y + 20), "TOTAL (Rs)", fill="black", font=font(24))
    d.text((420, y + 20), f"{RECEIPT_TOTAL}", fill="black", font=font(24))
    img.save(RECEIPT)

    # 2. A bar chart: monthly sales.
    months = [("Jan", 120), ("Feb", 95), ("Mar", 160), ("Apr", 140), ("May", 60), ("Jun", 180)]
    img = Image.new("RGB", (600, 400), "white")
    d = ImageDraw.Draw(img)
    d.text((170, 15), "Monthly sales (units)", fill="black", font=font(22))
    for i, (month, value) in enumerate(months):
        x = 60 + i * 85
        d.rectangle((x, 340 - value * 1.5, x + 50, 340), fill="steelblue")
        d.text((x + 8, 350), month, fill="black", font=font(18))
        d.text((x + 8, 340 - value * 1.5 - 25), str(value), fill="black", font=font(16))
    img.save(CHART)

    # 3. A 2-page PDF report (pages drawn as images, saved as one PDF).
    pages = []
    texts = [
        ["Q2 Report - Annapoorna Cafe", "", "Revenue grew 18% compared with Q1.",
         "The best-selling item was masala dosa.", "Two new staff joined in April."],
        ["Page 2 - Problems", "", "In May the gas supply failed for 6 days,",
         "so sales dropped to 60 units.", "Plan: keep a backup induction stove."],
    ]
    for lines in texts:
        page = Image.new("RGB", (800, 1000), "white")
        d = ImageDraw.Draw(page)
        for i, line in enumerate(lines):
            d.text((60, 80 + i * 50), line, fill="black", font=font(30 if i == 0 else 24))
        pages.append(page)
    pages[0].save(REPORT_PDF, save_all=True, append_images=pages[1:])

    print(f"Sample files ready in {DATA_DIR}")


def b64(path: Path) -> str:
    """Read a file and turn its bytes into base64 text (what the API expects)."""
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


# ---------------------------------------------------------------------------
# DEMO 1: One image (base64). Read a receipt and check the total.
# ---------------------------------------------------------------------------
def demo_image_base64():
    heading("DEMO 1: read a receipt image (base64)")
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64(RECEIPT)}},
                {"type": "text", "text": (
                    "List every item on this receipt with its line total. "
                    "Then add the line totals yourself and say if the printed TOTAL is correct. "
                    "End with a last line 'TOTAL: <number>'."
                )},
            ],
        }],
    )
    show(response)
    print(f"\nCorrect total (worked out by Python): {RECEIPT_TOTAL}")


# ---------------------------------------------------------------------------
# DEMO 2: Two images in one message + an image from a URL.
# Label the images ("Image 1:", "Image 2:") so you can refer to them.
# ---------------------------------------------------------------------------
def demo_two_images_and_url():
    heading("DEMO 2: two images in one message, then an image from a URL")
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Image 1:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64(RECEIPT)}},
                {"type": "text", "text": "Image 2:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64(CHART)}},
                {"type": "text", "text": "In one short line each: what is Image 1, and which month is best and worst in Image 2?"},
            ],
        }],
    )
    show(response)

    print("\n--- image from a URL (Anthropic downloads it; the link must be public) ---")
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "url", "url": IMAGE_URL}},
                    {"type": "text", "text": "What is this image? One sentence."},
                ],
            }],
        )
        show(response)
    except anthropic.BadRequestError as e:
        # Happens if the link is dead or the site blocks downloads.
        print(f"URL image failed (400): {e.message}")


# ---------------------------------------------------------------------------
# DEMO 3: A PDF (base64). Claude sees the text AND the page images.
# ---------------------------------------------------------------------------
def demo_pdf():
    heading("DEMO 3: ask questions about a PDF (base64)")
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64(REPORT_PDF)}},
                {"type": "text", "text": "Why did sales drop in May, and what is the plan? Say which page you found it on."},
            ],
        }],
    )
    show(response)


# ---------------------------------------------------------------------------
# DEMO 4: Files API. Upload once, reuse the file_id, delete at the end.
# With base64 you send the whole file in EVERY request; with the Files API
# you send a short id. (You still pay input tokens for the file each time.)
# ---------------------------------------------------------------------------
def demo_files_api():
    heading("DEMO 4: Files API (upload once, ask twice)")
    uploaded = client.files.upload(file=(REPORT_PDF.name, REPORT_PDF.read_bytes(), "application/pdf"))
    print(f"Uploaded: id={uploaded.id}  size={uploaded.size_bytes} bytes")

    try:
        for question in ("How much did revenue grow?", "Who joined in April?"):
            response = client.messages.create(
                model=MODEL,
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {"type": "file", "file_id": uploaded.id}},
                        {"type": "text", "text": f"{question} One sentence."},
                    ],
                }],
            )
            print(f"\nQ: {question}")
            show(response)
    finally:
        # Files stay stored until you delete them. Clean up.
        client.files.delete(uploaded.id)
        print(f"\nDeleted {uploaded.id}")


# ---------------------------------------------------------------------------
# DEMO 5: Citations. A plain-text document with citations switched on.
# The answer comes back as SEVERAL text blocks; a block that used the
# document has a .citations list with the exact quoted text.
# ---------------------------------------------------------------------------
POLICY = (
    "Refund policy. Food can be returned within 30 minutes if it is cold or wrong. "
    "Refunds are paid in cash only. Online orders are refunded to the original UPI account "
    "within 3 working days. We do not refund tips."
)


def demo_citations():
    heading("DEMO 5: citations (which sentence did the answer come from?)")
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "text", "media_type": "text/plain", "data": POLICY},
                    "title": "Cafe refund policy",
                    "citations": {"enabled": True},
                },
                {"type": "text", "text": "I ordered online and my food was cold. Can I get a refund, and how will I get the money?"},
            ],
        }],
    )
    for block in response.content:
        if block.type != "text":
            continue
        print(block.text, end="")
        for c in block.citations or []:
            print(f'  [source: "{c.cited_text.strip()}"]', end="")
    print()


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {
    "1": demo_image_base64,
    "2": demo_two_images_and_url,
    "3": demo_pdf,
    "4": demo_files_api,
    "5": demo_citations,
}

MENU = """
Pick a demo:
  1  Read a receipt image (base64)
  2  Two images in one message + image from a URL
  3  Ask questions about a PDF
  4  Files API: upload once, reuse the id
  5  Citations from a document
  a  Run all
  q  Quit"""

make_sample_files()

if len(sys.argv) > 1:
    for key in sys.argv[1:]:
        DEMOS[key]()
    sys.exit()

while True:
    print(MENU)
    choice = input("Choice: ").strip().lower()
    if choice == "q":
        break
    if choice == "a":
        for demo in DEMOS.values():
            demo()
    elif choice in DEMOS:
        DEMOS[choice]()
    else:
        print("Unknown choice.")
