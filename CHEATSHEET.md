# Developer Cheat Sheet (Beginner)

Quick notes to copy and paste. Commands run in the **terminal** (Linux / Ubuntu).
Text written like `<this>` is a placeholder: replace it with your own value and remove the `< >`.

**Contents**
1. [Terminal basics](#1-terminal-basics)
2. [Create a GitHub account](#2-create-a-github-account)
3. [Git one-time setup](#3-git-one-time-setup)
4. [First push to GitHub](#4-first-push-to-github)
5. [First pull from GitHub (clone)](#5-first-pull-from-github-clone)
6. [Git daily commands](#6-git-daily-commands)
7. [Virtual environment (venv)](#7-virtual-environment-venv)
8. [pip: install packages](#8-pip-install-packages)
9. [Secrets and the .env file](#9-secrets-and-the-env-file)
10. [Python cheat sheet](#10-python-cheat-sheet)
11. [Streamlit cheat sheet](#11-streamlit-cheat-sheet)
12. [AI agent with Claude](#12-ai-agent-with-claude)
13. [Common errors and fixes](#13-common-errors-and-fixes)
14. [New project checklist](#14-new-project-checklist)

---

## 1. Terminal basics

| Command | What it does |
|---|---|
| `pwd` | Show the folder you are in |
| `ls` / `ls -la` | List files (`-la` also shows hidden files such as `.env`) |
| `cd <folder>` | Go into a folder |
| `cd ..` | Go up one folder |
| `cd ~` | Go to your home folder |
| `mkdir <name>` | Make a new folder |
| `touch <file>` | Make an empty file |
| `cat <file>` | Print a file |
| `cp <from> <to>` | Copy |
| `mv <from> <to>` | Move or rename |
| `rm <file>` | Delete a file (there is **no** recycle bin) |
| `rm -r <folder>` | Delete a folder (be careful) |
| `clear` | Clear the screen |
| `Ctrl + C` | Stop the running program |
| `↑` arrow | Show the previous command |
| `Tab` | Auto-complete file names |
| `code .` | Open this folder in VS Code |

---

## 2. Create a GitHub account

1. Go to https://github.com/signup
2. Enter your email, a password, and a **username**. Write the username down.
3. Verify the email with the code GitHub sends you.
4. Choose the **Free** plan.

### Create a Personal Access Token (you use it instead of a password)
GitHub **does not accept your account password** in the terminal. Use a token instead:

1. Click your profile picture → **Settings** → **Developer settings** (bottom left)
2. **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**
3. Note: `laptop`, Expiration: 90 days, tick **`repo`**
4. Click **Generate token**, then **copy it right away** (it starts with `ghp_` and is shown only once)
5. Keep it somewhere safe. **Never put it in your code or on GitHub.**

---

## 3. Git one-time setup

Do this **once per computer**:
```bash
git --version                                   # check Git is installed
sudo apt install git                            # install it if the line above failed
git config --global user.name  "<Your Name>"
git config --global user.email "<you@example.com>"
git config --global init.defaultBranch main
git config --global credential.helper store     # remember the token after the first push
git config --list                               # check your settings
```

**Two GitHub accounts on one computer?** Inside a project folder, run the same commands **without** `--global`. They then apply to that project only.

---

## 4. First push to GitHub

### A. On github.com
**+** (top right) → **New repository** → enter a name → Public or Private → **don't** tick README, .gitignore, or license → **Create repository**

### B. In the terminal
```bash
cd <your-project-folder>

# 1. Tell Git what to ignore (see the .gitignore section below)
nano .gitignore        # or: code .gitignore

# 2. Start Git
git init
git branch -M main

# 3. Stage the files, then CHECK the list
git add .
git status             # .env and venv/ must NOT appear here!

# 4. Save a snapshot (a commit)
git commit -m "First commit"

# 5. Connect to GitHub (do this once)
git remote add origin https://github.com/<username>/<repo>.git

# 6. Upload
git push -u origin main
```
When Git asks: **Username** = your GitHub username, **Password** = your **token** (nothing appears as you paste it, which is normal).

After that, you only need:
```bash
git add .
git commit -m "What I changed"
git push
```

### A good `.gitignore` for Python
```gitignore
# secrets
.env

# virtual environments
venv/
.venv/

# Python temporary files
__pycache__/
*.pyc

# editor / OS files
.vscode/
.DS_Store
```

---

## 5. First pull from GitHub (clone)

**Get a project onto a new computer (first time):**
```bash
git clone https://github.com/<username>/<repo>.git
cd <repo>
python3 -m venv .venv                  # build a new venv; venvs are never on GitHub
source .venv/bin/activate
pip install -r requirements.txt        # install the same packages
cp .env.example .env                   # if the project has one, then add your own keys
```

**Get the latest changes (project already on your computer):**
```bash
git pull
```

| Word | Meaning |
|---|---|
| `clone` | Download a whole repo **for the first time** |
| `pull` | Download **new changes** into a repo you already have |
| `push` | Upload your commits to GitHub |
| `fetch` | Check GitHub for changes without applying them |

---

## 6. Git daily commands

### The everyday loop
```bash
git pull                     # 1. get the latest changes first
# ... edit your code ...
git status                   # 2. what changed?
git diff                     # 3. show the exact changed lines
git add .                    # 4. stage everything (or: git add file.py)
git commit -m "Add login page"
git push                     # 5. upload
```

### Look around
| Command | What it does |
|---|---|
| `git status` | Changed, staged, and untracked files |
| `git log --oneline` | Short history of commits |
| `git diff` | Changes that aren't staged yet |
| `git diff --staged` | Changes that are staged |
| `git remote -v` | Which GitHub repo this folder is connected to |

### Branches (work on a feature without breaking `main`)
```bash
git branch                   # list branches (* = the current one)
git switch -c new-feature    # create a branch and move to it
git switch main              # go back to main
git merge new-feature        # (while on main) bring the feature's changes in
git push -u origin new-feature   # upload the branch to GitHub
git branch -d new-feature    # delete the branch after merging
```

### Undo things
| Problem | Fix |
|---|---|
| Throw away edits to a file (not yet added) | `git restore <file>` |
| Unstage a file (undo `git add`) | `git restore --staged <file>` |
| Fix the last commit message (not pushed yet) | `git commit --amend -m "New message"` |
| Undo the last commit but keep the changes | `git reset --soft HEAD~1` |
| Committed `.env` by mistake (not pushed) | `git rm --cached .env`, add it to `.gitignore`, then commit |
| **Pushed** a secret key | **Revoke the key right away** (Anthropic console / GitHub settings) and create a new one. Deleting the file isn't enough; it stays in the history. |

---

## 7. Virtual environment (venv)

A **venv** is a private folder of packages for **one project**. Projects then don't break each other.

| Task | Command |
|---|---|
| Create (once per project) | `python3 -m venv .venv` |
| Activate (**every new terminal**) | `source .venv/bin/activate` |
| Check it's active | The prompt starts with `(.venv)`; `which python` shows a path inside `.venv` |
| Deactivate | `deactivate` |
| Delete and rebuild | `rm -rf .venv`, then create it again and run `pip install -r requirements.txt` |

- Windows activate: `.venv\Scripts\activate`
- If `python3 -m venv` fails on Ubuntu, run `sudo apt install python3-venv`.
- **Never** push the venv to GitHub. Share `requirements.txt` instead.
- In VS Code: `Ctrl+Shift+P` → **Python: Select Interpreter** → pick the `.venv` one.

---

## 8. pip: install packages

Activate the venv **first**, so packages go into the venv.

| Task | Command |
|---|---|
| Install a package | `pip install streamlit` |
| Install several | `pip install anthropic python-dotenv streamlit` |
| Install a specific version | `pip install streamlit==1.40.0` |
| Upgrade a package | `pip install --upgrade streamlit` |
| Uninstall | `pip uninstall streamlit` |
| List installed packages | `pip list` |
| Show one package's details | `pip show streamlit` |
| Save the package list to a file | `pip freeze > requirements.txt` |
| Install everything from the file | `pip install -r requirements.txt` |
| Upgrade pip itself | `python -m pip install --upgrade pip` |

**`pip list` vs `pip freeze`**
- `pip list` gives a readable table for **you** to look at.
- `pip freeze` prints `name==version` lines for a **file**, so other people can install exactly the same versions.

---

## 9. Secrets and the .env file

Keep API keys **out of your code**. Put them in `.env`:
```bash
# .env   (this file is in .gitignore, so it is never pushed)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```
Read the key in Python:
```python
import os
from dotenv import load_dotenv      # pip install python-dotenv

load_dotenv()                        # reads .env into environment variables
api_key = os.getenv("ANTHROPIC_API_KEY")
```
Tip: commit a `.env.example` file with **empty** values (`ANTHROPIC_API_KEY=`), so others know which keys they need.

---

## 10. Python cheat sheet

### Run Python
```bash
python3 file.py        # run a file
python3                # interactive mode (type exit() to leave)
```

### Variables and types
```python
name = "Santhosh"      # str   (text)
age = 25               # int   (whole number)
price = 9.99           # float (decimal)
is_ready = True        # bool  (True / False)
nothing = None         # no value

type(age)              # <class 'int'>
int("5"), str(5), float("2.5")    # convert between types
```

### Strings
```python
msg = f"Hi {name}, you are {age}"     # f-string: puts values inside text
msg.upper(), msg.lower(), msg.strip() # UPPER, lower, remove spaces at the ends
msg.split(",")                        # split into a list
"-".join(["a", "b"])                  # "a-b"
msg[0], msg[-1], msg[0:3]             # first char, last char, slice
len(msg)                              # length
"Hi" in msg                           # True
```

### Lists (ordered, can change)
```python
fruits = ["apple", "banana"]
fruits.append("mango")         # add at the end
fruits.remove("apple")         # remove by value
fruits[0]                      # first item
len(fruits)
sorted(fruits)
squares = [n * n for n in range(5)]   # list comprehension → [0, 1, 4, 9, 16]
```

### Dictionaries (key → value)
```python
user = {"name": "Ravi", "age": 30}
user["name"]                   # "Ravi"
user.get("email", "none")      # safe get with a default
user["email"] = "r@x.com"      # add or update
for key, value in user.items():
    print(key, value)
```

### If / else
```python
if age >= 18:
    print("adult")
elif age >= 13:
    print("teen")
else:
    print("child")
# comparisons: ==  !=  >  <  >=  <=     logic: and  or  not
```

### Loops
```python
for fruit in fruits:
    print(fruit)

for i in range(3):             # 0, 1, 2
    print(i)

for i, fruit in enumerate(fruits):   # index + item
    print(i, fruit)

while True:
    text = input("Type (q to quit): ")
    if text == "q":
        break                  # leave the loop
```

### Functions
```python
def greet(name: str, greeting: str = "Hello") -> str:
    """Return a greeting."""   # docstring: describes the function
    return f"{greeting}, {name}!"

greet("Anu")                   # "Hello, Anu!"
greet("Anu", greeting="Hi")    # "Hi, Anu!"
```

### Errors (try / except)
```python
try:
    number = int(input("Number: "))
except ValueError:
    print("That is not a number")
```

### Files and JSON
```python
with open("notes.txt", "w") as f:   # "w" write, "a" append, "r" read
    f.write("hello\n")

with open("notes.txt") as f:
    text = f.read()

import json
data = {"a": 1}
with open("data.json", "w") as f:
    json.dump(data, f, indent=2)
with open("data.json") as f:
    data = json.load(f)
```

### Classes (bundle data and functions)
```python
class Dog:
    def __init__(self, name):
        self.name = name

    def bark(self):
        return f"{self.name} says woof"

Dog("Tommy").bark()
```

### Imports and the main guard
```python
import os
from datetime import datetime

def main():
    print(datetime.now())

if __name__ == "__main__":     # runs only when you run this file directly
    main()
```

---

## 11. Streamlit cheat sheet

Streamlit turns a Python file into a web page. **The whole script re-runs from top to bottom** each time the user clicks or types.

```bash
pip install streamlit
streamlit run app.py        # NOT "python app.py"; opens http://localhost:8501
```
Stop it with `Ctrl + C`.

### Show things
```python
import streamlit as st

st.title("My App")
st.header("Section")
st.write("Anything: text, numbers, lists, tables")
st.markdown("**bold** and *italic*")
st.code("print('hi')", language="python")
st.success("Done!"); st.error("Oops"); st.warning("Careful"); st.info("FYI")
st.image("photo.png")
st.dataframe(my_pandas_df)
```

### Get input
```python
name   = st.text_input("Your name")
age    = st.number_input("Age", min_value=0)
level  = st.slider("Level", 1, 10, 5)
choice = st.selectbox("Pick one", ["A", "B", "C"])
agree  = st.checkbox("I agree")
file   = st.file_uploader("Upload a file")

if st.button("Submit"):
    st.write(f"Hello {name}")
```

### Layout
```python
col1, col2 = st.columns(2)
col1.write("left")
col2.write("right")

with st.sidebar:
    st.write("Sidebar content")

with st.expander("Show details"):
    st.write("Hidden until clicked")

with st.spinner("Thinking..."):
    ...   # slow work goes here
```

### Remember values between re-runs: `st.session_state`
```python
if "count" not in st.session_state:
    st.session_state.count = 0

if st.button("+1"):
    st.session_state.count += 1

st.write(st.session_state.count)
```

### Minimal chat app with Claude (streaming)
```python
import streamlit as st
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY from the environment

st.title("🤖 Chat with Claude")

if "messages" not in st.session_state:
    st.session_state.messages = []      # the chat memory

for m in st.session_state.messages:     # redraw the old messages
    st.chat_message(m["role"]).markdown(m["content"])

if question := st.chat_input("Ask something"):
    st.chat_message("user").markdown(question)
    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("assistant"):
        with client.messages.stream(
            model="claude-opus-5-5",
            max_tokens=16000,
            messages=st.session_state.messages,
        ) as stream:
            answer = st.write_stream(stream.text_stream)   # shows the answer word by word

    st.session_state.messages.append({"role": "assistant", "content": answer})
```

---

## 12. AI agent with Claude

### Setup
```bash
pip install anthropic python-dotenv
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env      # get a key at https://console.anthropic.com
```

### Key ideas
| Idea | Meaning |
|---|---|
| **LLM call** | Send messages → get a reply |
| **Memory** | The API remembers nothing. **You** keep a `messages` list and send all of it every time. |
| **Tool** | A Python function you describe to Claude. Claude *asks* for it; **your code runs it**. |
| **Agent** | A loop: call Claude → if it asks for a tool, run it and send back the result → repeat until it's done |
| **System prompt** | Instructions that set Claude's role and behavior |
| **Tokens** | Pieces of text. You pay per token (input + output). |

### Common `stop_reason` values
| Value | What to do |
|---|---|
| `end_turn` | Finished; show the answer |
| `tool_use` | Run the requested tool(s), send back `tool_result`, call again |
| `max_tokens` | The answer was cut off; raise `max_tokens` |
| `refusal` | Claude declined; tell the user |

### Step 1: One question, one answer
```python
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "What is Python?"}],
)

for block in response.content:
    if block.type == "text":
        print(block.text)
print(response.usage.input_tokens, response.usage.output_tokens)
```

### Step 2: Chat with memory
```python
messages = []
while True:
    question = input("You: ")
    if question == "exit":
        break
    messages.append({"role": "user", "content": question})

    response = client.messages.create(
        model="claude-opus-5-5", max_tokens=16000, messages=messages,
    )
    messages.append({"role": "assistant", "content": response.content})  # keep the full reply

    print("Claude:", "".join(b.text for b in response.content if b.type == "text"))
```

### Step 3: Agent with tools (the manual loop, so you see every step)
```python
def get_weather(city: str) -> str:
    return f"30°C and sunny in {city}"          # a real app would call a weather API

TOOL_FUNCTIONS = {"get_weather": get_weather}

TOOLS = [{
    "name": "get_weather",
    "description": "Get the current weather for a city.",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
    },
}]

messages = [{"role": "user", "content": "What's the weather in Chennai?"}]

for _ in range(10):                              # safety limit on loop turns
    response = client.messages.create(
        model="claude-opus-5-5", max_tokens=16000, tools=TOOLS, messages=messages,
    )
    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":       # no more tools needed: done
        break

    tool_results = []
    for block in response.content:
        if block.type == "tool_use":
            result = TOOL_FUNCTIONS[block.name](**block.input)   # OUR code runs the tool
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,          # links the result to Claude's request
                "content": result,
            })
    messages.append({"role": "user", "content": tool_results})   # ALL results in ONE message

print("".join(b.text for b in response.content if b.type == "text"))
```

### Step 4: The same agent, shorter (the SDK's tool runner writes the loop for you)
```python
from anthropic import beta_tool

@beta_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City name, e.g. Chennai.
    """
    return f"30°C and sunny in {city}"

runner = client.beta.messages.tool_runner(
    model="claude-opus-5-5",
    max_tokens=16000,
    tools=[get_weather],
    messages=[{"role": "user", "content": "What's the weather in Chennai?"}],
)
for message in runner:                           # one message per loop turn
    for block in message.content:
        if block.type == "text":
            print(block.text)
```

### Streaming (show the text as it's written)
```python
with client.messages.stream(
    model="claude-opus-5-5", max_tokens=16000,
    messages=[{"role": "user", "content": "Tell me a short story"}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### Handle errors
```python
try:
    response = client.messages.create(...)
except anthropic.AuthenticationError:
    print("Wrong API key; check .env")
except anthropic.RateLimitError:
    print("Too many requests; wait and try again")
except anthropic.APIConnectionError:
    print("No internet connection")
except anthropic.APIStatusError as e:
    print(f"API error {e.status_code}: {e.message}")
```

### Agent-building tips
- Write **clear tool descriptions**. Claude decides which tool to use from the description.
- Always set a **max-turns limit** on the loop.
- Return errors from tools as text (`"Error: city not found"`) so Claude can react.
- Print each tool call while you learn, so you can see what the agent is doing.

---

## 13. Common errors and fixes

| Error | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'x'` | Activate the venv, then `pip install x` |
| `command not found: python` | Use `python3` (or activate the venv) |
| `externally-managed-environment` (pip) | You forgot to activate the venv |
| `ANTHROPIC_API_KEY not found` | Check that `.env` exists, is spelled right, and that `load_dotenv()` runs |
| `401 authentication_error` | The API key is wrong or was revoked |
| `Address already in use` / port busy | Another app is running; stop it with `Ctrl + C` |
| `git push` → `Authentication failed` | Use a **token**, not your password |
| `git push` → `403 Permission denied` | Git saved the login for a different account; put the username in the URL: `git remote set-url origin https://<user>@github.com/<user>/<repo>.git` |
| `git push` → `rejected (fetch first)` | GitHub has newer commits: `git pull`, then `git push` |
| `remote origin already exists` | `git remote set-url origin <new-url>` |
| `fatal: not a git repository` | You're in the wrong folder, or you haven't run `git init` |
| Merge conflict (`<<<<<<<` in a file) | Edit the file to keep the right lines, delete the markers, then `git add .` and `git commit` |
| `IndentationError` (Python) | Use 4 spaces consistently; don't mix tabs and spaces |

---

## 14. New project checklist

```bash
mkdir my-project && cd my-project
python3 -m venv .venv
source .venv/bin/activate
pip install anthropic python-dotenv streamlit
pip freeze > requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
printf ".env\n.venv/\n__pycache__/\n*.pyc\n" > .gitignore
git init && git branch -M main
git add . && git status          # check that .env is NOT listed
git commit -m "Initial commit"
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```
