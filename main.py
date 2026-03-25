import json
import os
from ollama import chat

MEMORY_FILE = "memory.json"
HISTORY_FILE = "history.json"
PERSONALITY_FILE = "personality.txt"
MODEL_NAME = "gemma3:4b"
MAX_HISTORY = 10


# -------------------------
# MEMORY FUNCTIONS
# -------------------------

def load_memory():
    default_memory = {"facts": [], "goals": [], "notes": []}

    if not os.path.exists(MEMORY_FILE):
        return default_memory

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        save_memory(default_memory)
        return default_memory


def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)


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


# -------------------------
# HISTORY FUNCTIONS
# -------------------------

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        save_history([])
        return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


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
# MEMORY STORAGE TRIGGERS
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
# COMMAND SYSTEM
# -------------------------

def handle_command(user_input, memory, history):
    command = user_input.lower().strip()

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
"""

    elif command == "/memory":
        return format_memory(memory)

    elif command == "/goals":
        goals = memory.get("goals", [])
        return "\n".join([f"- {g}" for g in goals]) if goals else "No goals saved."

    elif command == "/notes":
        notes = memory.get("notes", [])
        return "\n".join([f"- {n}" for n in notes]) if notes else "No notes saved."

    elif command == "/facts":
        facts = memory.get("facts", [])
        return "\n".join([f"- {f}" for f in facts]) if facts else "No facts saved."

    elif command == "/history":
        if not history:
            return "No recent chat history."
        return "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history])

    elif command == "/clearhistory":
        save_history([])
        return "Recent chat history cleared."

    return None


# -------------------------
# BUILD MESSAGES FOR MODEL
# -------------------------

def build_messages(user_input, personality, memory, history):
    memory_text = format_memory(memory)

    system_prompt = f"""
{personality}

Here is the assistant's current long-term memory:
{memory_text}

Use this memory when relevant, but do not mention it unnecessarily.
"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    return messages


# -------------------------
# MAIN LOOP
# -------------------------

def main():
    print("Kalki v0.2 is running. Type 'exit' to quit.\n")

    personality = load_personality()
    memory = load_memory()
    history = load_history()

    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit"]:
            print("Kalki: See you later.")
            break

        # Handle slash commands
        if user_input.startswith("/"):
            command_response = handle_command(user_input, memory, history)
            if command_response:
                print(f"Kalki: {command_response}")
                if user_input.lower().strip() == "/clearhistory":
                    history = []
                continue

        # Store memory if user uses trigger phrases
        memory_response = maybe_store_memory(user_input, memory)
        if memory_response:
            print(f"Kalki: {memory_response}")
            continue

        messages = build_messages(user_input, personality, memory, history)

        try:
            response = chat(
                model=MODEL_NAME,
                messages=messages
            )
            reply = response["message"]["content"]

            print(f"Kalki: {reply}")

            # Save recent conversation
            history = add_to_history("user", user_input, history)
            history = add_to_history("assistant", reply, history)

        except Exception as e:
            print(f"Kalki: Error talking to model: {e}")


if __name__ == "__main__":
    main()