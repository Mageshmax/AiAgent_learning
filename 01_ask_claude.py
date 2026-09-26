"""
Lesson 1: Your first LLM call.

You type a question -> we send it to Claude -> Claude's answer is printed.

Setup (one time):
    pip install anthropic python-dotenv
    Put your key in a .env file:  ANTHROPIC_API_KEY=sk-ant-...

Run:
    python 01_ask_claude.py
"""

import os

import anthropic
from dotenv import find_dotenv, load_dotenv

# 1. Load variables from the .env file (searches this folder, then parent folders).
load_dotenv(find_dotenv())

api_key = os.getenv("ANTHROPIC_API_KEY")
print(f'api key is: {api_key[:10]}...' if api_key else 'api key is: (missing)')
print()
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

# 2. Create a client and pass the key to it.
client = anthropic.Anthropic(api_key=api_key)

# 3. Get a question from the user.
question = input("Ask Claude a question: ")

# 4. Send the question to the LLM.
response = client.messages.create(
    model="claude-opus-5-5", # which Claude model to use
    max_tokens=16000,        # upper limit on the length of the answer
    system="You are a helpful assistant. Answer clearly and concisely.",  # sets the model's behavior
    messages=[
        {"role": "user", "content": question},  # the conversation so far (just one message)
    ],
)

# --- Look inside the response ---------------------------------------------
# The response is a Python object (a "Message"). Print every field it has.
# print("\n========== RESPONSE FIELDS ==========")
# for field_name, value in response.to_dict().items():
#     if field_name in ("content", "usage"):
#         continue  # these are nested, printed below
#     print(f"{field_name:15}: {value}")

# # content = list of blocks. Each block has a "type" (text, thinking, tool_use...).
# print("\n---------- content (list of blocks) ----------")
# for i, block in enumerate(response.content):
#     print(f"block[{i}]:")
#     for key, value in block.to_dict().items():
#         print(f"    {key:12}: {value}")

# # usage = token counts for this call (this is what you are billed for).
# print("\n---------- usage (tokens) ----------")
# for key, value in response.usage.to_dict().items():
#     print(f"    {key:30}: {value}")

# The whole response as pretty JSON (same data, raw form).
print("\n---------- full response as JSON ----------")
print(response.to_json())
print("=====================================\n")

# 5. Check why the model stopped, then print the answer.
if response.stop_reason == "refusal":
    print("Claude declined to answer this request.")
else:
    # response.content is a list of blocks (text, thinking, tool calls...).
    # We only want the text blocks.
    for block in response.content:
        if block.type == "text":
            print("\nClaude:", block.text)

# 6. (Optional) See how many tokens you used. You pay per token.
print(f"\n[tokens used: input={response.usage.input_tokens}, output={response.usage.output_tokens}]")
