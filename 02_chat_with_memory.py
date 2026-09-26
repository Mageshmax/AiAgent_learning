"""
Lesson 2: Chat loop with memory.

KEY IDEA: The LLM has NO memory. Every API call starts fresh.
"Memory" = our code keeps a `messages` list and sends the WHOLE list every time.

Commands while chatting:
    history  -> show what we are sending to the LLM
    exit     -> quit

Experiment:
    1. Say "My name is Santhosh", then ask "What is my name?"
    2. Set REMEMBER = False below and try again -> Claude forgets.
    3. Watch input_tokens grow every turn (the whole history is re-sent).

Run:
    python 02_chat_with_memory.py
"""

import os

import anthropic
from dotenv import find_dotenv, load_dotenv

REMEMBER = True  # set to False to see what happens without memory

load_dotenv(find_dotenv())
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise SystemExit("ANTHROPIC_API_KEY not found. Add it to your .env file.")

client = anthropic.Anthropic(api_key=api_key)

# This list IS the memory. It holds every user and assistant turn.
messages = []

print("Chat with Claude (type 'history' to see memory, 'exit' to quit)\n")

while True:
    question = input("You: ").strip()
    if not question:
        continue
    if question.lower() == "exit":
        break
    if question.lower() == "history":
        print("\n--- messages list (sent to the LLM on every call) ---")
        for i, msg in enumerate(messages):
            text = msg["content"]
            if not isinstance(text, str):  # assistant turns hold content blocks
                text = " ".join(b.text for b in text if b.type == "text")
            print(f"[{i}] {msg['role']:9}: {text}")
        print("-----------------------------------------------------\n")
        continue

    if not REMEMBER:
        messages = []  # forget everything before this question

    # 1. Add the user's question to memory.
    messages.append({"role": "user", "content": question})

    # 2. Send the FULL conversation to Claude.
    response = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=16000,
        system="You are a helpful assistant. Answer clearly and concisely.",
        messages=messages,
    )

    # 3. Add Claude's reply to memory, so the next call includes it.
    #    We store response.content (all blocks), not just the text, so nothing is lost.
    messages.append({"role": "assistant", "content": response.content})

    # 4. Show the answer.
    answer = "".join(b.text for b in response.content if b.type == "text")
    print(f"\nClaude: {answer}")
    print(
        f"[turns in memory: {len(messages)} | "
        f"input_tokens: {response.usage.input_tokens} | "
        f"output_tokens: {response.usage.output_tokens}]\n"
    )
