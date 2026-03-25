import json
import os
from ollama import chat

MEMORY_FILE = "memory.json"
PERSONALITY_FILE = "personality.txt"
MODEL_NAME = "gemma3:4b"


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


def load_personality():
    if not os.path.exists(PERSONALITY_FILE):
        return "You are a helpful AI assistant."
    with open(PERSONALITY_FILE, "r", encoding="utf-8") as f:
        return f.read()


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


def build_messages(user_input, personality, memory):
    memory_text = format_memory(memory)

    system_prompt = f"""
{personality}

Here is the assistant's current long-term memory:
{memory_text}

Use this memory when relevant, but do not mention it unnecessarily.
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]


def main():
    print("Kalki v0.1 is running. Type 'exit' to quit.\n")

    personality = load_personality()
    memory = load_memory()

    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit"]:
            print("Kalki: See you later.")
            break

        memory_response = maybe_store_memory(user_input, memory)
        if memory_response:
            print(f"Kalki: {memory_response}")
            continue

        messages = build_messages(user_input, personality, memory)

        try:
            response = chat(
                model=MODEL_NAME,
                messages=messages
            )
            reply = response["message"]["content"]
            print(f"Kalki: {reply}")
        except Exception as e:
            print(f"Kalki: Error talking to model: {e}")


if __name__ == "__main__":
    main()