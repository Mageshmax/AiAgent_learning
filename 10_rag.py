"""
Lesson 10: RAG (Retrieval-Augmented Generation): answer from YOUR documents.

KEY IDEA: Claude doesn't know your shop's policies, your notes or your
company wiki. You can't paste ALL of it into every prompt (too big, too
costly: lesson 8). So:

    1. INDEX (once):     split documents into small CHUNKS -> turn each chunk
                         into a VECTOR (a list of numbers) -> store them
    2. RETRIEVE (per question): turn the question into a vector too, find the
                         chunks whose vectors are most SIMILAR (cosine similarity)
    3. GENERATE:         send ONLY those few chunks + the question to Claude,
                         and tell it to answer from them (with citations)

    documents -> chunks -> vectors -> [vector store]
                                          |
    question -> vector -> top-k similar chunks -> Claude -> answer + sources

About the vectors ("embeddings"):
    This lesson uses TF-IDF: a vector of word counts, weighted so rare words
    matter more. It needs only numpy, runs offline and is free. Its weakness:
    it matches WORDS, not MEANING. "money back" does not match "refund".
    Real apps use an EMBEDDING MODEL, whose vectors capture meaning, e.g.
    Voyage AI (Anthropic's recommended provider: pip install voyageai) or a
    local model (pip install sentence-transformers). Only `embed()` changes;
    the rest of the pipeline stays the same.

Two ways to use retrieval:
    - Classic RAG (demo 3): YOUR code searches, then calls Claude once.
    - Agentic RAG (demo 4): give Claude a `search_docs` TOOL. It decides what
      to search, can search again with other words, and combine results.

The sample documents (a made-up grocery shop) are written to
lesson_data/docs/ the first time you run this. Add your own .md / .txt files
there and choose demo 1 again to re-index.

Run:
    python 10_rag.py        (menu)
    python 10_rag.py 1 2    (demos 1 and 2)
"""

import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

import anthropic
import numpy as np
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"
TOP_K = 3              # chunks sent to Claude per search
CHUNK_CHARS = 600      # max characters per chunk
MIN_SCORE = 0.05       # below this a chunk is treated as "not relevant"

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

DATA_DIR = Path(__file__).resolve().parent / "lesson_data"
DOCS_DIR = DATA_DIR / "docs"
INDEX_DIR = DATA_DIR / "rag_index"


def heading(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


# ---------------------------------------------------------------------------
# Sample documents (written once, then they are ordinary files you can edit).
# ---------------------------------------------------------------------------
SAMPLE_DOCS = {
    "delivery.md": """# Delivery
## Areas and times
We deliver inside Chennai city limits the same day for orders placed before 2 pm.
Orders after 2 pm arrive the next morning between 7 and 11 am.
Outside Chennai we deliver anywhere in Tamil Nadu in 2 to 3 working days.

## Charges
Delivery is free for orders of Rs 999 or more. Smaller orders pay Rs 49 inside Chennai
and Rs 99 elsewhere in Tamil Nadu. Express delivery within 90 minutes costs Rs 149
and is only available in Adyar, Mylapore, T. Nagar and Velachery.
""",
    "returns.md": """# Returns and refunds
## What can be returned
Unopened items can be returned within 7 days of delivery. Opened food items cannot be
returned, unless they were damaged, spoiled or past their expiry date on arrival.
For damaged items, send a photo through the app within 48 hours.

## Refunds
Refunds go back to the original payment method within 5 working days.
Cash-on-delivery orders are refunded as store credit, or to a UPI id you give us.
Delivery charges are refunded only if the whole order was wrong or damaged.
""",
    "loyalty.md": """# Pantry Points loyalty programme
Every Rs 100 you spend earns 2 Pantry Points. 100 points are worth Rs 50 off a future order.
Points expire 12 months after you earn them. Gold members (spent over Rs 25,000 in a year)
earn double points and get free express delivery twice a month.
Points cannot be earned on gift cards and cannot be exchanged for cash.
""",
    "payments.md": """# Payments
We accept UPI, debit and credit cards, net banking and cash on delivery.
Cash on delivery is available for orders up to Rs 3,000.
Card payments over Rs 5,000 need an OTP. We never ask for your OTP or PIN on the phone:
if someone calls asking for it, hang up and report it to support.
Invoices with GST details can be downloaded from the Orders page in the app.
""",
    "company.md": """# About Chennai Pantry
Chennai Pantry was started in 2019 by two friends in Mylapore as a single grocery store.
Today we run a warehouse in Guindy and deliver around 3,000 orders a day.
Support is open 7 am to 10 pm every day on chat, and 9 am to 6 pm on the phone (044-4000-1234).
We are hiring delivery partners and warehouse staff: apply at careers@chennaipantry.example.
""",
}


def write_sample_docs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    if not any(DOCS_DIR.iterdir()):
        for name, text in SAMPLE_DOCS.items():
            (DOCS_DIR / name).write_text(text)
        print(f"Wrote {len(SAMPLE_DOCS)} sample documents to {DOCS_DIR}")


# ---------------------------------------------------------------------------
# STEP 1: Chunking. Split each document at headings / blank lines, then pack
# paragraphs into chunks of at most CHUNK_CHARS. Each chunk remembers its
# file and heading, so answers can cite a source.
# ---------------------------------------------------------------------------
def chunk_document(path: Path) -> list[dict]:
    chunks, heading_text, buffer = [], path.stem, ""

    def flush():
        nonlocal buffer
        if buffer.strip():
            chunks.append({"source": path.name, "heading": heading_text, "text": buffer.strip()})
        buffer = ""

    for block in re.split(r"\n\s*\n", path.read_text()):
        for line in block.splitlines():
            if line.startswith("#"):
                flush()
                heading_text = line.lstrip("# ").strip()
            else:
                if len(buffer) + len(line) > CHUNK_CHARS:
                    flush()
                buffer += line + "\n"
    flush()
    return chunks


# ---------------------------------------------------------------------------
# STEP 2: Vectors. TF-IDF with numpy. To use a real embedding model, replace
# build_vectorizer / embed with calls to that model.
# ---------------------------------------------------------------------------
STOP_WORDS = set("a an and are as at be by can for from i if in is it of on or our the to we what when with you your do does my how".split())


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP_WORDS]


def build_vectorizer(texts: list[str]) -> dict:
    """Vocabulary + IDF weights learned from all chunks."""
    doc_freq = Counter(word for t in texts for word in set(tokenize(t)))
    vocab = sorted(doc_freq)
    n = len(texts)
    return {"vocab": vocab, "idf": [math.log((1 + n) / (1 + doc_freq[w])) + 1 for w in vocab]}


def embed(texts: list[str], vectorizer: dict) -> np.ndarray:
    """Each text -> one row vector, length 1 (so a dot product = cosine similarity)."""
    index = {w: i for i, w in enumerate(vectorizer["vocab"])}
    idf = np.array(vectorizer["idf"])
    matrix = np.zeros((len(texts), len(index)))
    for row, text in enumerate(texts):
        for word, count in Counter(tokenize(text)).items():
            if word in index:
                matrix[row, index[word]] = count
    matrix *= idf
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


# ---------------------------------------------------------------------------
# STEP 3: The vector store: the chunks + their vectors, saved to disk.
# ---------------------------------------------------------------------------
def build_index() -> None:
    chunks = [c for path in sorted(DOCS_DIR.glob("*")) if path.suffix in (".md", ".txt") for c in chunk_document(path)]
    texts = [f"{c['heading']}\n{c['text']}" for c in chunks]
    vectorizer = build_vectorizer(texts)
    vectors = embed(texts, vectorizer)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_DIR / "vectors.npy", vectors)
    (INDEX_DIR / "chunks.json").write_text(json.dumps({"chunks": chunks, "vectorizer": vectorizer}, indent=1))
    print(f"Indexed {len(chunks)} chunks from {len(set(c['source'] for c in chunks))} files. Vector size: {vectors.shape[1]}")


def load_index():
    if not (INDEX_DIR / "vectors.npy").exists():
        build_index()
    data = json.loads((INDEX_DIR / "chunks.json").read_text())
    return data["chunks"], data["vectorizer"], np.load(INDEX_DIR / "vectors.npy")


def search(query: str, k: int = TOP_K) -> list[dict]:
    """Return the k most similar chunks, best first, each with a score."""
    chunks, vectorizer, vectors = load_index()
    scores = vectors @ embed([query], vectorizer)[0]  # cosine similarity with every chunk
    best = np.argsort(scores)[::-1][:k]
    return [{**chunks[i], "score": float(scores[i])} for i in best if scores[i] >= MIN_SCORE]


# ---------------------------------------------------------------------------
# DEMO 1: Build the index.
# ---------------------------------------------------------------------------
def demo_index():
    heading("DEMO 1: chunk + embed + store (no API calls)")
    build_index()
    chunks, _, _ = load_index()
    for c in chunks[:4]:
        print(f"\n[{c['source']} > {c['heading']}]\n{c['text'][:160]}...")


# ---------------------------------------------------------------------------
# DEMO 2: Retrieval only. See which chunks come back, and where TF-IDF fails.
# ---------------------------------------------------------------------------
def demo_search():
    heading("DEMO 2: retrieval (no API calls)")
    for query in (
        "How long do refunds take?",
        "Is there express delivery in Velachery?",
        "Can I get my money back for an opened packet?",  # 'money back' vs 'refund': weak word match
        "What is the capital of France?",                  # nothing relevant
    ):
        print(f"\nQ: {query}")
        results = search(query)
        if not results:
            print("   (no relevant chunks)")
        for r in results:
            print(f"   {r['score']:.2f}  {r['source']} > {r['heading']}")
    print("\nNote the scores: exact words score high; different words with the same meaning score low.")
    print("That gap is what a real embedding model closes.")


# ---------------------------------------------------------------------------
# DEMO 3: Classic RAG. Search, then send the chunks as DOCUMENTS with
# citations on, so every claim points to its source text (lesson 7c).
# ---------------------------------------------------------------------------
RAG_SYSTEM = (
    "You answer customer questions for Chennai Pantry using ONLY the provided documents. "
    "If the documents don't contain the answer, say you don't know and suggest contacting support. "
    "Be brief."
)


def answer_with_rag(question: str) -> None:
    results = search(question)
    print(f"Q: {question}\n   retrieved: {[f'{r['source']} > {r['heading']}' for r in results]}")
    documents = [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": r["text"]},
            "title": f"{r['source']} > {r['heading']}",
            "citations": {"enabled": True},
        }
        for r in results
    ]
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=RAG_SYSTEM,
        messages=[{"role": "user", "content": documents + [{"type": "text", "text": question}]}],
    )
    sources = []
    answer = ""
    for block in response.content:
        if block.type == "text":
            answer += block.text
            for c in block.citations or []:
                if c.document_title not in sources:
                    sources.append(c.document_title)
    print(f"A: {answer.strip()}")
    print(f"   sources: {sources or 'none'}\n")


def demo_rag():
    heading("DEMO 3: classic RAG with citations")
    for question in (
        "I ordered at 4 pm in Chennai. When will it arrive, and do I pay for delivery on a Rs 800 order?",
        "How many points do I get for a Rs 2,000 order, and when do they expire?",
        "Do you sell organic vegetables?",
    ):
        answer_with_rag(question)


# ---------------------------------------------------------------------------
# DEMO 4: Agentic RAG. Claude gets a search tool and decides what to look up.
# It can search twice with different words when the first search misses.
# ---------------------------------------------------------------------------
TOOLS = [{
    "name": "search_docs",
    "description": (
        "Keyword search over Chennai Pantry's policy documents (delivery, returns, refunds, loyalty points, "
        "payments, company info). Returns the most relevant passages with their source. It matches WORDS, "
        "so if a search finds nothing useful, try again with other words (e.g. 'refund' instead of 'money back')."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "A few keywords."}},
        "required": ["query"],
        "additionalProperties": False,
    },
}]


def run_search_tool(query: str) -> str:
    results = search(query)
    print(f"   🔎 search_docs({query!r}) -> {[r['source'] for r in results]}")
    if not results:
        return "No relevant passages found."
    return "\n\n".join(f"[{r['source']} > {r['heading']}]\n{r['text']}" for r in results)


def agentic_answer(messages: list, question: str) -> str:
    messages.append({"role": "user", "content": question})
    for _ in range(8):
        response = client.messages.create(
            model=MODEL, max_tokens=4000, output_config={"effort": "low"},
            system=RAG_SYSTEM + " Search the documents before answering; mention the source file.",
            tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "content": run_search_tool(**b.input)}
            for b in response.content if b.type == "tool_use"
        ]})
    return "(stopped: too many searches)"


def demo_agentic():
    heading("DEMO 4: agentic RAG (Claude searches for itself)")
    print("Try: 'Can I get my money back on a cash order?'  Type 'exit' to go back.\n")
    messages = []
    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() == "exit":
            return
        print(f"Claude: {agentic_answer(messages, question)}\n")


# ---------------------------------------------------------------------------
# Menu.
# ---------------------------------------------------------------------------
DEMOS = {"1": demo_index, "2": demo_search, "3": demo_rag, "4": demo_agentic}

MENU = """
Pick a demo:
  1  Build the index            (free)
  2  Search only                (free)
  3  Classic RAG with citations (3 small calls)
  4  Agentic RAG chat
  q  Quit"""

write_sample_docs()

if len(sys.argv) > 1:
    for key in sys.argv[1:]:
        DEMOS[key]()
    sys.exit()

while True:
    print(MENU)
    choice = input("Choice: ").strip().lower()
    if choice == "q":
        break
    if choice in DEMOS:
        DEMOS[choice]()
    else:
        print("Unknown choice.")
