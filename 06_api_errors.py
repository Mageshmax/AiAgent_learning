"""
Lesson 6: API error handling.

KEY IDEA: Two kinds of things go wrong when you call the Claude API.

    1. YOUR request is wrong  -> retrying won't help, fix the code or settings
           400 BadRequestError        (bad parameters, e.g. empty messages)
           401 AuthenticationError    (wrong / missing API key)
           403 PermissionDeniedError  (your key isn't allowed to do this)
           404 NotFoundError          (model name typo)
           413 RequestTooLargeError   (too much input)

    2. A TEMPORARY problem  -> wait a little and try again
           429 RateLimitError         (too many requests per minute)
           500 InternalServerError    (problem on Anthropic's side)
           529 OverloadedError        (API is busy)
           APITimeoutError            (no answer in time)
           APIConnectionError         (no internet / can't reach the server)

GOOD NEWS: the SDK already RETRIES the temporary ones for you (2 times by
default, waiting longer each time = "exponential backoff"). You only decide:
    - how many retries:  anthropic.Anthropic(max_retries=3)
    - how long to wait:  anthropic.Anthropic(timeout=60.0)   (seconds)
    - what to tell the user when it STILL fails  -> try / except
q
Every demo below triggers a REAL error. Failed requests aren't billed, so
demos 1-5 cost nothing. Only demo 7 (chat) makes normal, paid calls.

Run:
    python 06_api_errors.py
"""

import logging
import os
import sys
import time

import anthropic
from dotenv import find_dotenv, load_dotenv

MODEL = "claude-opus-5-5"

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

# The client we use for real work: retry temporary errors 3 times,
# and give up on a single attempt after 60 seconds.
client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=60.0)

HELLO = [{"role": "user", "content": "Say hello in 3 words."}]


# ---------------------------------------------------------------------------
# STEP A: One function that knows how to handle every error.
# ---------------------------------------------------------------------------
def short_message(e: anthropic.APIStatusError) -> str:
    """The API's own error message, without the long raw JSON around it."""
    try:
        return e.body["error"]["message"]
    except (TypeError, KeyError):
        return e.message


# ORDER MATTERS: Python uses the FIRST `except` that matches, so put specific
# errors before general ones (APITimeoutError is a kind of APIConnectionError,
# and every status error is a kind of APIStatusError).
def safe_ask(messages: list, api_client=client, model: str = MODEL, **options):
    """Call Claude. Return (answer, None) on success or (None, friendly_error) on failure."""
    try:
        response = api_client.messages.create(
            model=model, max_tokens=16000, messages=messages, **options
        )
    # --- 1. Your request is wrong: don't retry, explain how to fix it ---
    except anthropic.AuthenticationError:
        return None, "401: API key is wrong or revoked. Check ANTHROPIC_API_KEY in .env."
    except anthropic.PermissionDeniedError as e:
        return None, f"403: your key isn't allowed to do this. {short_message(e)}"
    except anthropic.NotFoundError as e:
        return None, f"404: not found (is the model name spelled right?). {short_message(e)}"
    except anthropic.RequestTooLargeError:
        return None, "413: request too large. Send less text (trim the chat history)."
    except anthropic.BadRequestError as e:
        return None, f"400: bad request. {short_message(e)} (request id: {e.request_id})"
    # --- 2. Temporary problem: the SDK ALREADY retried, and it still failed ---
    except anthropic.RateLimitError as e:
        wait = e.response.headers.get("retry-after", "a few")
        return None, f"429: too many requests. Try again in {wait} seconds."
    except anthropic.OverloadedError:
        return None, "529: Claude is overloaded right now. Try again in a minute."
    except anthropic.InternalServerError as e:
        return None, f"{e.status_code}: server error at Anthropic. Try again later."
    except anthropic.APITimeoutError:
        return None, "Timeout: Claude didn't answer in time. Try again, or raise `timeout`."
    except anthropic.APIConnectionError:
        return None, "Connection error: can't reach the API. Check your internet."
    # --- 3. Anything else from the API (a status code not listed above) ---
    except anthropic.APIStatusError as e:
        return None, f"{e.status_code}: {short_message(e)}"

    # The call worked, but still check WHY Claude stopped.
    if response.stop_reason == "refusal":
        return None, "Claude declined to answer this request."
    answer = "".join(b.text for b in response.content if b.type == "text")
    if response.stop_reason == "max_tokens":
        answer += "\n(answer was cut off: raise max_tokens)"
    return answer, None


# ---------------------------------------------------------------------------
# STEP B: Demos. Each one breaks ONE thing on purpose.
# ---------------------------------------------------------------------------
def show(title: str, answer, error) -> None:
    print(f"\n=== {title} ===")
    print(f"    ✅ Claude: {answer}" if error is None else f"    ❌ {error}")


def demo_bad_key():
    bad_client = anthropic.Anthropic(api_key="sk-ant-this-is-not-a-real-key")
    show("1. Wrong API key (401)", *safe_ask(HELLO, api_client=bad_client))


def demo_bad_model():
    show("2. Model name typo (404)", *safe_ask(HELLO, model="claude-opus-99"))


def demo_bad_request():
    # An empty messages list: there is nothing to answer.
    show("3. Bad request (400)", *safe_ask([]))


def demo_retries():
    # Point the client at a port where nothing is listening, so every try fails.
    # Turn on the SDK's log to SEE each retry and its growing wait time.
    print("\n=== 4. Automatic retries (connection error) ===")
    for retries in (0, 3):
        broken = anthropic.Anthropic(
            api_key=api_key, base_url="http://127.0.0.1:9", max_retries=retries
        )
        print(f"  max_retries={retries}:")
        logging.getLogger("anthropic").setLevel(logging.INFO)
        started = time.time()
        _, error = safe_ask(HELLO, api_client=broken)
        logging.getLogger("anthropic").setLevel(logging.WARNING)
        print(f"    ❌ {error}  (gave up after {time.time() - started:.1f}s)")


def demo_timeout():
    # 0.01 seconds is far too short for any answer; no retries so it fails fast.
    fast_client = anthropic.Anthropic(api_key=api_key, timeout=0.01, max_retries=0)
    show("5. Timeout", *safe_ask(HELLO, api_client=fast_client))


def demo_success():
    show("6. Everything correct", *safe_ask(HELLO))


# ---------------------------------------------------------------------------
# STEP C: A chat that never crashes (NEW: undo the question if the call fails).
# ---------------------------------------------------------------------------
def chat():
    print("\nChat with error handling. Type 'exit' to go back to the menu.")
    print("Tip: turn off Wi-Fi mid-chat to see the connection error + retries.\n")
    messages = []
    while True:
        question = input("You: ").strip()
        if not question:
            continue
        if question.lower() == "exit":
            return
        messages.append({"role": "user", "content": question})
        answer, error = safe_ask(messages)
        if error:
            # Remove the question, or the next call would send two "user"
            # messages in a row with no answer between them.
            messages.pop()
            print(f"❌ {error}\n")
            continue
        messages.append({"role": "assistant", "content": answer})
        print(f"Claude: {answer}\n")


# ---------------------------------------------------------------------------
# STEP D: Menu.
# ---------------------------------------------------------------------------
logging.basicConfig(stream=sys.stdout, format="    [sdk log] %(message)s")  # shows the SDK's retry messages

DEMOS = {
    "1": demo_bad_key,
    "2": demo_bad_model,
    "3": demo_bad_request,
    "4": demo_retries,
    "5": demo_timeout,
    "6": demo_success,
    "7": chat,
}

MENU = """
Pick a demo:
  1  Wrong API key        (401)
  2  Model name typo      (404)
  3  Bad request          (400)
  4  Automatic retries    (connection error)
  5  Timeout
  6  A call that works    (small cost)
  7  Chat that never crashes (normal cost)
  a  Run demos 1-6
  q  Quit"""

while True:
    print(MENU)
    choice = input("Choice: ").strip().lower()
    if choice == "q":
        break
    if choice == "a":
        for key in "123456":
            DEMOS[key]()
    elif choice in DEMOS:
        DEMOS[choice]()
    else:
        print("Unknown choice.")
