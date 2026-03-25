import json
import os
import re
import webbrowser
import subprocess
import time
from datetime import datetime
from ollama import chat

MEMORY_FILE = "memory.json"
HISTORY_FILE = "history.json"
PERSONALITY_FILE = "personality.txt"
TASKS_FILE = "tasks.json"
REMINDERS_FILE = "reminders.json"

MODEL_NAME = "gemma3:4b"
MAX_HISTORY = 10


# -------------------------
# FILE HELPERS
# -------------------------

def load_json_file(filename, default):
    if not os.path.exists(filename):
        return default
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        save_json_file(filename, default)
        return default


def save_json_file(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# -------------------------
# LOADERS / SAVERS
# -------------------------

def load_memory():
    return load_json_file(MEMORY_FILE, {"facts": [], "goals": [], "notes": []})


def save_memory(memory):
    save_json_file(MEMORY_FILE, memory)


def load_history():
    return load_json_file(HISTORY_FILE, [])


def save_history(history):
    save_json_file(HISTORY_FILE, history)


def load_tasks():
    return load_json_file(TASKS_FILE, [])


def save_tasks(tasks):
    save_json_file(TASKS_FILE, tasks)


def load_reminders():
    return load_json_file(REMINDERS_FILE, [])


def save_reminders(reminders):
    save_json_file(REMINDERS_FILE, reminders)


# -------------------------
# FORMATTERS
# -------------------------

def format_memory(memory):
    lines = []
    if memory.get("facts"):
        lines.append("Facts:")
        for item in memory["facts"]:
            lines.append(f"- {item}")
    if memory.get("goals"):
        lines.append("Goals:")
        for item in memory["goals"]:
            lines.append(f"- {item}")
    if memory.get("notes"):
        lines.append("Notes:")
        for item in memory["notes"]:
            lines.append(f"- {item}")
    return "\n".join(lines) if lines else "No memory stored yet."


def format_tasks(tasks):
    if not tasks:
        return "No tasks saved."
    lines = []
    for i, task in enumerate(tasks, 1):
        status = "✅" if task["done"] else "❌"
        lines.append(f"{i}. {status} {task['text']}")
    return "\n".join(lines)


def format_reminders(reminders):
    if not reminders:
        return "No reminders saved."
    lines = []
    for i, reminder in enumerate(reminders, 1):
        status = "✅" if reminder.get("done") else "⏰"
        lines.append(f"{i}. {status} {reminder['time']} - {reminder['text']}")
    return "\n".join(lines)


# -------------------------
# HISTORY
# -------------------------

def add_to_history(role, content, history):
    history.append({"role": role, "content": content})
    history = history[-MAX_HISTORY:]
    save_history(history)
    return history


# -------------------------
# PERSONALITY
# -------------------------

def load_personality():
    if not os.path.exists(PERSONALITY_FILE):
        return "You are a helpful AI assistant."
    with open(PERSONALITY_FILE, "r", encoding="utf-8") as f:
        return f.read()


# -------------------------
# MEMORY STORAGE
# -------------------------

def maybe_store_memory(user_input, memory):
    lowered = user_input.lower()

    if lowered.startswith("remember that "):
        fact = user_input[14:].strip()
        if fact:
            memory["facts"].append(fact)
            save_memory(memory)
            return f"Got it. I’ll remember: {fact}"

    if lowered.startswith("my goal is "):
        goal = user_input[11:].strip()
        if goal:
            memory["goals"].append(goal)
            save_memory(memory)
            return f"Saved your goal: {goal}"

    if lowered.startswith("note that "):
        note = user_input[10:].strip()
        if note:
            memory["notes"].append(note)
            save_memory(memory)
            return f"Saved note: {note}"

    return None


# -------------------------
# REMINDER CHECKER
# -------------------------

def check_due_reminders(reminders):
    now = datetime.now().strftime("%H:%M")
    due = []

    for reminder in reminders:
        if reminder["time"] == now and not reminder.get("done", False):
            due.append(reminder)
            reminder["done"] = True

    if due:
        save_reminders(reminders)

    return due


# -------------------------
# PROACTIVE FOCUS PROMPT
# -------------------------

def generate_focus_prompt(tasks, memory):
    undone_tasks = [task["text"] for task in tasks if not task["done"]]
    goals = memory.get("goals", [])

    if undone_tasks:
        return f"You still have unfinished tasks. Start with this: {undone_tasks[0]}"
    elif goals:
        return f"You have goals saved. Pick one and work on it for 15 minutes: {goals[0]}"
    else:
        return "You have no tasks or goals saved. Set one small target right now."


# -------------------------
# SAFE ACTIONS
# -------------------------

def open_app(app_name):
    app_name = app_name.lower().strip()

    app_map = {
        "notepad": "notepad",
        "calculator": "calc",
        "explorer": "explorer",
        "vscode": "code",
        "code": "code",
        "browser": "start microsoft-edge:",
        "edge": "start microsoft-edge:"
    }

    if app_name not in app_map:
        return f"Unsupported app: {app_name}"

    try:
        if app_name in ["browser", "edge"]:
            os.system(app_map[app_name])
        else:
            subprocess.Popen(app_map[app_name], shell=True)
        return f"Opened {app_name}."
    except Exception as e:
        return f"Failed to open {app_name}: {e}"


def open_website(site_name):
    site_name = site_name.lower().strip()

    site_map = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "chatgpt": "https://chat.openai.com",
        "gmail": "https://mail.google.com",
        "github": "https://github.com"
    }

    if site_name not in site_map:
        return f"Unsupported website: {site_name}"

    try:
        webbrowser.open(site_map[site_name])
        return f"Opened {site_name}."
    except Exception as e:
        return f"Failed to open {site_name}: {e}"


def start_timer(minutes_text):
    if not minutes_text.isdigit():
        return "Usage: /timer 5"

    minutes = int(minutes_text)
    seconds = minutes * 60

    print(f"Kalki: Timer started for {minutes} minute(s).")
    time.sleep(seconds)
    return f"⏰ Timer finished: {minutes} minute(s)."


# -------------------------
# COMMAND SYSTEM
# -------------------------

def handle_command(user_input, memory, history, tasks, reminders):
    parts = user_input.strip().split(" ", 1)
    command = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command == "/help":
        return """
Available commands:
/help - Show this help menu
/memory - Show all stored memory
/goals - Show saved goals
/notes - Show saved notes
/facts - Show saved facts
/history - Show recent chat history
/clearhistory - Clear recent conversation history

/task <text> - Add a new task
/tasks - Show all tasks
/done <number> - Mark a task as done

/remind HH:MM your reminder text - Add a reminder
/reminders - Show all reminders

/focus - Get a productivity nudge

/openapp <app> - Open a safe app
/openweb <site> - Open a safe website
/timer <minutes> - Start a timer
/time - Show current time
/date - Show current date
"""

    elif command == "/memory":
        return format_memory(memory)

    elif command == "/goals":
        return "\n".join([f"- {g}" for g in memory.get("goals", [])]) or "No goals saved."

    elif command == "/notes":
        return "\n".join([f"- {n}" for n in memory.get("notes", [])]) or "No notes saved."

    elif command == "/facts":
        return "\n".join([f"- {f}" for f in memory.get("facts", [])]) or "No facts saved."

    elif command == "/history":
        return "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history]) or "No recent chat history."

    elif command == "/clearhistory":
        save_history([])
        return "Recent chat history cleared."

    elif command == "/task":
        if not argument:
            return "Usage: /task Finish assignment"
        tasks.append({"text": argument, "done": False})
        save_tasks(tasks)
        return f"Task added: {argument}"

    elif command == "/tasks":
        return format_tasks(tasks)

    elif command == "/done":
        if not argument.isdigit():
            return "Usage: /done 1"
        index = int(argument) - 1
        if 0 <= index < len(tasks):
            tasks[index]["done"] = True
            save_tasks(tasks)
            return f"Marked task {index + 1} as done."
        return "Invalid task number."

    elif command == "/remind":
        if not argument or len(argument.split(" ", 1)) < 2:
            return "Usage: /remind 21:30 Drink water"
        time_part, text_part = argument.split(" ", 1)
        reminders.append({"time": time_part, "text": text_part, "done": False})
        save_reminders(reminders)
        return f"Reminder set for {time_part}: {text_part}"

    elif command == "/reminders":
        return format_reminders(reminders)

    elif command == "/focus":
        return generate_focus_prompt(tasks, memory)

    elif command == "/openapp":
        return open_app(argument)

    elif command == "/openweb":
        return open_website(argument)

    elif command == "/timer":
        return start_timer(argument)

    elif command == "/time":
        return datetime.now().strftime("Current time: %H:%M:%S")

    elif command == "/date":
        return datetime.now().strftime("Today's date: %Y-%m-%d")

    return None


# -------------------------
# NATURAL LANGUAGE ROUTER
# -------------------------

def natural_language_to_command(user_input):
    text = user_input.lower().strip()

    # Open websites
    for site in ["youtube", "google", "chatgpt", "gmail", "github"]:
        if text in [f"open {site}", f"launch {site}", f"go to {site}"]:
            return f"/openweb {site}"

    # Open apps
    for app in ["notepad", "calculator", "explorer", "vscode", "code", "browser", "edge"]:
        if text in [f"open {app}", f"launch {app}", f"start {app}"]:
            return f"/openapp {app}"

    # Show tasks
    if text in ["what are my tasks", "show my tasks", "list my tasks"]:
        return "/tasks"

    # Show goals
    if text in ["what are my goals", "show my goals", "list my goals"]:
        return "/goals"

    # Show memory
    if text in ["what do you remember", "show my memory", "what do you know about me"]:
        return "/memory"

    # Focus prompt
    if text in ["motivate me", "focus me", "give me a focus prompt", "push me to work"]:
        return "/focus"

    # Add task
    match = re.match(r"add (.+) to (my )?tasks?", text)
    if match:
        task_text = match.group(1).strip()
        return f"/task {task_text}"

    # Start timer
    match = re.match(r"(start|set) a (\d+) minute timer", text)
    if match:
        minutes = match.group(2)
        return f"/timer {minutes}"

    # Reminder
    match = re.match(r"remind me at (\d{1,2}:\d{2}) to (.+)", text)
    if match:
        time_part = match.group(1)
        reminder_text = match.group(2).strip()
        return f"/remind {time_part} {reminder_text}"

    return None


# -------------------------
# BUILD MESSAGES
# -------------------------

def build_messages(user_input, personality, memory, history, tasks):
    memory_text = format_memory(memory)
    task_text = format_tasks(tasks)

    system_prompt = f"""
{personality}

Here is the assistant's current long-term memory:
{memory_text}

Current tasks:
{task_text}

Use this information when relevant, but do not mention it unnecessarily.
"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    return messages


# -------------------------
# MAIN LOOP
# -------------------------

def main():
    print("Kalki v0.5 is running. Type 'exit' to quit.\n")

    personality = load_personality()
    memory = load_memory()
    history = load_history()
    tasks = load_tasks()
    reminders = load_reminders()

    while True:
        due_reminders = check_due_reminders(reminders)
        for reminder in due_reminders:
            print(f"\n⏰ Kalki Reminder: {reminder['text']} ({reminder['time']})\n")

        user_input = input("You: ").strip()

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit"]:
            print("Kalki: See you later.")
            break

        # Convert natural language to safe commands
        converted_command = natural_language_to_command(user_input)
        if converted_command:
            print(f"Kalki: Interpreted as -> {converted_command}")
            user_input = converted_command

        if user_input.startswith("/"):
            command_response = handle_command(user_input, memory, history, tasks, reminders)
            if command_response:
                print(f"Kalki: {command_response}")
                if user_input.lower().strip() == "/clearhistory":
                    history = []
                continue

        memory_response = maybe_store_memory(user_input, memory)
        if memory_response:
            print(f"Kalki: {memory_response}")
            continue

        messages = build_messages(user_input, personality, memory, history, tasks)

        try:
            response = chat(
                model=MODEL_NAME,
                messages=messages
            )
            reply = response["message"]["content"]

            print(f"Kalki: {reply}")

            history = add_to_history("user", user_input, history)
            history = add_to_history("assistant", reply, history)

        except Exception as e:
            print(f"Kalki: Error talking to model: {e}")


if __name__ == "__main__":
    main()