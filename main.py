import json
import os
import re
import webbrowser
import subprocess
import threading
import time
import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime

import requests
import speech_recognition as sr
from ollama import chat
from dotenv import load_dotenv
import keyboard

from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

# -------------------------
# ENV / CONFIG
# -------------------------

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()

MEMORY_FILE = "memory.json"
HISTORY_FILE = "history.json"
PERSONALITY_FILE = "personality.txt"
TASKS_FILE = "tasks.json"
REMINDERS_FILE = "reminders.json"

MAX_HISTORY = 10

# Local models
PRIMARY_MODEL = "qwen2.5:3b"
FALLBACK_MODEL = "gemma3:4b"
CURRENT_MODEL = PRIMARY_MODEL
AUTO_MODEL_SWITCH = True

MODEL_ALIASES = {
    "qwen": "qwen2.5:3b",
    "gemma": "gemma3:4b",
    "auto": PRIMARY_MODEL
}

# Providers
CURRENT_PROVIDER = "smart"   # cloud / local / smart / local-first / cloud-first
CLOUD_MODEL = "deepseek-chat"

# Voice / Hotkey
VOICE_ENABLED = True
HOTKEY_ENABLED = True
HOTKEY_BIND = "ctrl+shift+k"

# Skills
CURRENT_SKILL = "general"

SKILLS = {
    "general": """You are Kalki, a smart adaptable personal AI assistant.
Be useful, natural, and flexible.
Do not behave like a rigid productivity bot.
Adapt to the user's needs naturally.""",

    "productivity": """You are Kalki in Productivity Skill mode.
Prioritize clarity, action steps, time awareness, planning, organization, tasks, and reminders.
Be concise and practical.""",

    "research": """You are Kalki in Research Skill mode.
Answer with structured thinking, good breakdowns, comparisons, context, and useful detail.
Prefer clarity and insight over short shallow answers.""",

    "coding": """You are Kalki in Coding Skill mode.
Help with debugging, coding, architecture, scripting, setup, and technical explanations.
Be practical and solution-oriented.
Prefer exact fixes and implementation guidance.""",

    "system": """You are Kalki in System Skill mode.
You help with desktop actions, tools, apps, websites, commands, workflows, and assistant control.
Be action-oriented and direct.""",

    "memory": """You are Kalki in Memory Skill mode.
Help the user remember, organize, store, retrieve, and reflect on information.
Prioritize continuity and useful recall."""
}


# -------------------------
# WINDOWS TTS
# -------------------------

def split_text_for_tts(text, max_len=220):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_len:
            current += (" " if current else "") + sentence
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks if chunks else [text]


def speak(text):
    global VOICE_ENABLED
    if not VOICE_ENABLED:
        return

    try:
        chunks = split_text_for_tts(str(text), max_len=220)

        for chunk in chunks:
            safe_text = chunk.replace("'", "''")
            command = (
                "Add-Type -AssemblyName System.Speech; "
                "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$speak.Speak('{safe_text}')"
            )
            subprocess.run(
                ["powershell", "-Command", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    except Exception as e:
        print(f"[Voice Error] {e}")


def speak_async(text):
    threading.Thread(target=speak, args=(text,), daemon=True).start()


# -------------------------
# VOICE INPUT
# -------------------------

def listen():
    recognizer = sr.Recognizer()

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)

        try:
            return recognizer.recognize_google(audio)
        except:
            return None
    except:
        return None


# -------------------------
# FILE HELPERS
# -------------------------

def load_json_file(filename, default):
    if not os.path.exists(filename):
        return default
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
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
# REMINDERS
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
# FOCUS
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


def timer_thread(minutes, ui_callback=None):
    speak_async(f"Timer started for {minutes} minutes.")
    time.sleep(minutes * 60)
    if ui_callback:
        ui_callback(f"⏰ Timer finished: {minutes} minute(s).")
    speak_async(f"Timer finished: {minutes} minutes.")


def start_timer(minutes_text, ui_callback=None):
    if not minutes_text.isdigit():
        return "Usage: /timer 5"

    minutes = int(minutes_text)
    threading.Thread(target=timer_thread, args=(minutes, ui_callback), daemon=True).start()
    return f"Started a {minutes}-minute timer."


# -------------------------
# SMART ROUTING
# -------------------------

def estimate_complexity(user_input):
    text = user_input.lower()

    cloud_keywords = [
        "compare", "explain deeply", "research", "analyze", "architecture",
        "design", "debug", "code", "python", "javascript", "error", "fix",
        "why does", "how does", "best approach", "pros and cons", "plan",
        "strategy", "write", "generate", "detailed", "long answer"
    ]

    for keyword in cloud_keywords:
        if keyword in text:
            return "cloud"

    if len(user_input) > 220:
        return "cloud"

    return "local"


def choose_provider_for_message(user_input):
    global CURRENT_PROVIDER, CURRENT_SKILL

    if CURRENT_PROVIDER == "cloud":
        return "cloud"

    if CURRENT_PROVIDER == "local":
        return "local"

    if CURRENT_PROVIDER == "cloud-first":
        return "cloud-first"

    if CURRENT_PROVIDER == "local-first":
        return "local-first"

    # SMART MODE
    if CURRENT_SKILL in ["coding", "research"]:
        return "cloud-first"

    if CURRENT_SKILL in ["system", "memory"]:
        return "local-first"

    estimated = estimate_complexity(user_input)

    if estimated == "cloud":
        return "cloud-first"
    return "local-first"


# -------------------------
# BUILD MESSAGES
# -------------------------

def build_messages(user_input, personality, memory, history, tasks):
    memory_text = format_memory(memory)
    task_text = format_tasks(tasks)
    skill_prompt = SKILLS.get(CURRENT_SKILL, SKILLS["general"])

    system_prompt = f"""
You are Kalki.

Base personality:
{personality}

Current active skill:
{CURRENT_SKILL}

Skill behavior instructions:
{skill_prompt}

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
# DEEPSEEK CLOUD CHAT
# -------------------------

def chat_with_deepseek(messages):
    if not DEEPSEEK_API_KEY:
        raise Exception("DeepSeek API key not found in .env")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": CLOUD_MODEL,
        "messages": messages,
        "temperature": 0.7
    }

    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )

    if response.status_code != 200:
        raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]


# -------------------------
# LOCAL OLLAMA CHAT
# -------------------------

def chat_with_local(messages):
    global CURRENT_MODEL, AUTO_MODEL_SWITCH

    try:
        response = chat(model=CURRENT_MODEL, messages=messages)
        return response["message"]["content"], CURRENT_MODEL

    except Exception as e:
        error_text = str(e).lower()

        if AUTO_MODEL_SWITCH and CURRENT_MODEL == PRIMARY_MODEL and (
            "system memory" in error_text
            or "status code: 500" in error_text
            or "runner process has terminated" in error_text
            or "cuda error" in error_text
        ):
            CURRENT_MODEL = FALLBACK_MODEL
            response = chat(model=CURRENT_MODEL, messages=messages)
            return response["message"]["content"], CURRENT_MODEL

        raise e


# -------------------------
# HYBRID CHAT ROUTER
# -------------------------

def chat_router(messages, user_input):
    route_mode = choose_provider_for_message(user_input)

    if route_mode == "cloud":
        reply = chat_with_deepseek(messages)
        return reply, f"{CLOUD_MODEL} [cloud]"

    elif route_mode == "local":
        reply, used_model = chat_with_local(messages)
        return reply, f"{used_model} [local]"

    elif route_mode == "cloud-first":
        try:
            reply = chat_with_deepseek(messages)
            return reply, f"{CLOUD_MODEL} [cloud-first]"
        except Exception as cloud_error:
            print(f"[Cloud Fallback] {cloud_error}")
            reply, used_model = chat_with_local(messages)
            return reply, f"{used_model} [local fallback]"

    elif route_mode == "local-first":
        try:
            reply, used_model = chat_with_local(messages)
            return reply, f"{used_model} [local-first]"
        except Exception as local_error:
            print(f"[Local Fallback] {local_error}")
            reply = chat_with_deepseek(messages)
            return reply, f"{CLOUD_MODEL} [cloud fallback]"

    else:
        raise Exception("Invalid routing mode.")


# -------------------------
# COMMAND SYSTEM
# -------------------------

def handle_command(user_input, memory, history, tasks, reminders, ui_callback=None):
    global CURRENT_MODEL, AUTO_MODEL_SWITCH, VOICE_ENABLED, CURRENT_PROVIDER, HOTKEY_ENABLED, CURRENT_SKILL

    parts = user_input.strip().split(" ", 1)
    command = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command == "/help":
        return """
Available commands:

General:
/help
/time
/date
/status

Memory:
/memory
/goals
/notes
/facts
/history
/clearhistory

Tasks:
/task <text>
/tasks
/done <number>

Reminders:
/remind HH:MM text
/reminders

Productivity:
/focus
/timer <minutes>

Actions:
/openapp <app>
/openweb <site>

Voice:
/voice
/silent
/speak

Hotkey:
/hotkey
/hotkeyon
/hotkeyoff

Local Models:
/model
/models
/use <qwen|gemma|auto>

Providers:
/provider
/providers
/useprovider <cloud|local|smart|local-first|cloud-first>

Skills:
/skill
/skills
/useskill <general|productivity|research|coding|system|memory>
"""

    elif command == "/status":
        return f"""Kalki Status:
- Provider mode: {CURRENT_PROVIDER}
- Cloud model: {CLOUD_MODEL}
- Local model: {CURRENT_MODEL}
- Voice: {'ON' if VOICE_ENABLED else 'OFF'}
- Hotkey: {'ON' if HOTKEY_ENABLED else 'OFF'}
- Hotkey bind: {HOTKEY_BIND}
- Current skill: {CURRENT_SKILL}"""

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
        return start_timer(argument, ui_callback)

    elif command == "/time":
        return datetime.now().strftime("Current time: %H:%M:%S")

    elif command == "/date":
        return datetime.now().strftime("Today's date: %Y-%m-%d")

    elif command == "/voice":
        spoken = listen()
        return spoken if spoken else "Sorry, I didn’t catch that."

    elif command == "/silent":
        VOICE_ENABLED = False
        return "Voice output disabled."

    elif command == "/speak":
        VOICE_ENABLED = True
        return "Voice output enabled."

    elif command == "/hotkey":
        return f"Current hotkey: {HOTKEY_BIND} | {'ON' if HOTKEY_ENABLED else 'OFF'}"

    elif command == "/hotkeyon":
        HOTKEY_ENABLED = True
        return f"Global hotkey enabled: {HOTKEY_BIND}"

    elif command == "/hotkeyoff":
        HOTKEY_ENABLED = False
        return "Global hotkey disabled."

    elif command == "/model":
        mode = "AUTO" if AUTO_MODEL_SWITCH else "MANUAL"
        return f"""Current local model info:
- Current: {CURRENT_MODEL}
- Primary: {PRIMARY_MODEL}
- Fallback: {FALLBACK_MODEL}
- Mode: {mode}"""

    elif command == "/models":
        return """Available local models:
- qwen -> qwen2.5:3b
- gemma -> gemma3:4b
- auto -> return to default automatic mode"""

    elif command == "/use":
        choice = argument.lower().strip()

        if choice not in MODEL_ALIASES:
            return "Usage: /use qwen OR /use gemma OR /use auto"

        if choice == "auto":
            CURRENT_MODEL = PRIMARY_MODEL
            AUTO_MODEL_SWITCH = True
            return f"Switched local model mode to AUTO. Current model reset to {CURRENT_MODEL}"

        CURRENT_MODEL = MODEL_ALIASES[choice]
        AUTO_MODEL_SWITCH = False
        return f"Switched local model manually to {CURRENT_MODEL}"

    elif command == "/provider":
        return f"""Current provider info:
- Provider mode: {CURRENT_PROVIDER}
- Cloud model: {CLOUD_MODEL}
- Local model: {CURRENT_MODEL}"""

    elif command == "/providers":
        return """Available providers:
- cloud -> always DeepSeek
- local -> always Ollama
- smart -> choose based on skill + message type
- local-first -> prefer local, fallback cloud
- cloud-first -> prefer cloud, fallback local"""

    elif command == "/useprovider":
        choice = argument.lower().strip()

        if choice not in ["cloud", "local", "smart", "local-first", "cloud-first"]:
            return "Usage: /useprovider cloud OR /useprovider local OR /useprovider smart OR /useprovider local-first OR /useprovider cloud-first"

        CURRENT_PROVIDER = choice
        return f"Switched provider mode to: {CURRENT_PROVIDER}"

    elif command == "/skill":
        return f"Current skill: {CURRENT_SKILL}"

    elif command == "/skills":
        return """Available skills:
- general
- productivity
- research
- coding
- system
- memory"""

    elif command == "/useskill":
        choice = argument.lower().strip()

        if choice not in SKILLS:
            return "Usage: /useskill general OR /useskill productivity OR /useskill research OR /useskill coding OR /useskill system OR /useskill memory"

        CURRENT_SKILL = choice
        return f"Switched active skill to: {CURRENT_SKILL}"

    return None


# -------------------------
# NATURAL LANGUAGE ROUTER
# -------------------------

def natural_language_to_command(user_input):
    text = user_input.lower().strip()

    for site in ["youtube", "google", "chatgpt", "gmail", "github"]:
        if text in [f"open {site}", f"launch {site}", f"go to {site}"]:
            return f"/openweb {site}"

    for app in ["notepad", "calculator", "explorer", "vscode", "code", "browser", "edge"]:
        if text in [f"open {app}", f"launch {app}", f"start {app}"]:
            return f"/openapp {app}"

    if text in ["what are my tasks", "show my tasks", "list my tasks"]:
        return "/tasks"

    if text in ["what are my goals", "show my goals", "list my goals"]:
        return "/goals"

    if text in ["what do you remember", "show my memory", "what do you know about me"]:
        return "/memory"

    if text in ["motivate me", "focus me", "give me a focus prompt", "push me to work"]:
        return "/focus"

    if text in ["listen to me", "use voice", "voice mode"]:
        return "/voice"

    if text in ["what model are you using", "show current model"]:
        return "/model"

    if text in ["what provider are you using", "show provider"]:
        return "/provider"

    if text in ["show status", "kalki status"]:
        return "/status"

    if text in ["what skill are you using", "show current skill"]:
        return "/skill"

    match = re.match(r"add (.+) to (my )?tasks?", text)
    if match:
        return f"/task {match.group(1).strip()}"

    match = re.match(r"(start|set) a (\d+) minute timer", text)
    if match:
        return f"/timer {match.group(2)}"

    match = re.match(r"remind me at (\d{1,2}:\d{2}) to (.+)", text)
    if match:
        return f"/remind {match.group(1)} {match.group(2).strip()}"

    return None


# -------------------------
# TRAY ICON
# -------------------------

def create_image():
    image = Image.new('RGB', (64, 64), color=(20, 20, 20))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 12, 52, 52), fill=(0, 200, 255))
    draw.text((24, 20), "K", fill=(0, 0, 0))
    return image


# -------------------------
# GUI APP
# -------------------------

class KalkiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kalki v1.3")
        self.root.geometry("950x680")
        self.root.configure(bg="#111111")

        self.personality = load_personality()
        self.memory = load_memory()
        self.history = load_history()
        self.tasks = load_tasks()
        self.reminders = load_reminders()

        self.chat_area = scrolledtext.ScrolledText(
            root,
            wrap=tk.WORD,
            font=("Consolas", 11),
            bg="#1a1a1a",
            fg="#f0f0f0",
            insertbackground="white"
        )
        self.chat_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.chat_area.config(state=tk.DISABLED)

        bottom_frame = tk.Frame(root, bg="#111111")
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)

        self.entry = tk.Entry(
            bottom_frame,
            font=("Consolas", 12),
            bg="#222222",
            fg="white",
            insertbackground="white"
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.entry.bind("<Return>", lambda event: self.send_message())

        tk.Button(bottom_frame, text="Send", command=self.send_message, width=10).pack(side=tk.LEFT, padx=3)
        tk.Button(bottom_frame, text="Voice", command=self.voice_input, width=10).pack(side=tk.LEFT, padx=3)
        tk.Button(bottom_frame, text="Speak On/Off", command=self.toggle_voice, width=12).pack(side=tk.LEFT, padx=3)
        tk.Button(bottom_frame, text="Clear Chat", command=self.clear_chat, width=10).pack(side=tk.LEFT, padx=3)

        self.add_message("Kalki", "Kalki v1.3 is online.")
        self.add_message("System", f"Global hotkey ready: {HOTKEY_BIND}")
        self.add_message("System", f"Active skill: {CURRENT_SKILL}")
        self.add_message("System", f"Provider mode: {CURRENT_PROVIDER}")
        speak_async("Kalki version one point three is now online.")

        self.start_background_reminders()
        self.setup_tray()
        self.setup_hotkey()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

    def add_message(self, sender, message):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"{sender}: {message}\n\n")
        self.chat_area.config(state=tk.DISABLED)
        self.chat_area.see(tk.END)

    def clear_chat(self):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.delete("1.0", tk.END)
        self.chat_area.config(state=tk.DISABLED)

    def toggle_voice(self):
        global VOICE_ENABLED
        VOICE_ENABLED = not VOICE_ENABLED
        self.add_message("System", f"Voice {'enabled' if VOICE_ENABLED else 'disabled'}.")

    def voice_input(self):
        self.add_message("System", "Listening...")
        threading.Thread(target=self._voice_capture_worker, daemon=True).start()

    def _voice_capture_worker(self):
        spoken = listen()
        if spoken:
            self.root.after(0, lambda: self.entry.delete(0, tk.END))
            self.root.after(0, lambda: self.entry.insert(0, spoken))
            self.root.after(0, self.send_message)
        else:
            self.root.after(0, lambda: self.add_message("System", "Sorry, I didn’t catch that."))

    def send_message(self):
        user_input = self.entry.get().strip()
        if not user_input:
            return

        self.entry.delete(0, tk.END)
        self.add_message("You", user_input)

        threading.Thread(target=self.process_message, args=(user_input,), daemon=True).start()

    def process_message(self, user_input):
        converted_command = natural_language_to_command(user_input)
        if converted_command:
            self.root.after(0, lambda: self.add_message("Kalki", f"Interpreted as -> {converted_command}"))
            user_input = converted_command

        if user_input.startswith("/"):
            command_response = handle_command(
                user_input,
                self.memory,
                self.history,
                self.tasks,
                self.reminders,
                ui_callback=lambda msg: self.root.after(0, lambda: self.add_message("Kalki", msg))
            )

            if command_response:
                if user_input == "/voice" and command_response not in ["Sorry, I didn’t catch that."]:
                    self.root.after(0, lambda: self.entry.insert(0, command_response))
                    return
                else:
                    self.root.after(0, lambda: self.add_message("Kalki", command_response))
                    speak_async(command_response)
                    return

        memory_response = maybe_store_memory(user_input, self.memory)
        if memory_response:
            self.root.after(0, lambda: self.add_message("Kalki", memory_response))
            speak_async(memory_response)
            return

        messages = build_messages(user_input, self.personality, self.memory, self.history, self.tasks)

        try:
            reply, used_backend = chat_router(messages, user_input)
            self.history = add_to_history("user", user_input, self.history)
            self.history = add_to_history("assistant", reply, self.history)

            self.root.after(0, lambda: self.add_message(f"Kalki [{CURRENT_SKILL}] ({used_backend})", reply))
            speak_async(reply)

        except Exception as e:
            self.root.after(0, lambda: self.add_message("Kalki", f"Error talking to model/provider: {e}"))

    def start_background_reminders(self):
        def reminder_loop_gui():
            while True:
                self.reminders = load_reminders()
                due = check_due_reminders(self.reminders)

                for reminder in due:
                    msg = f"⏰ Reminder: {reminder['text']} ({reminder['time']})"
                    self.root.after(0, lambda m=msg: self.add_message("Kalki", m))
                    speak_async(msg)

                time.sleep(30)

        threading.Thread(target=reminder_loop_gui, daemon=True).start()

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)
        self.root.after(0, self.entry.focus_set)

    def quit_app(self, icon=None, item=None):
        self.icon.stop()
        self.root.destroy()

    def setup_tray(self):
        image = create_image()
        menu = (
            item("Show Kalki", self.show_window),
            item("Hide Kalki", lambda icon, item: self.hide_window()),
            item("Exit Kalki", self.quit_app)
        )

        self.icon = pystray.Icon("Kalki", image, "Kalki Assistant", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def hotkey_trigger(self):
        global HOTKEY_ENABLED
        if not HOTKEY_ENABLED:
            return

        self.root.after(0, self.show_window)
        self.root.after(0, lambda: self.add_message("System", "🎤 Push-to-talk activated..."))
        threading.Thread(target=self._voice_capture_worker, daemon=True).start()

    def setup_hotkey(self):
        def hotkey_worker():
            try:
                keyboard.add_hotkey(HOTKEY_BIND, self.hotkey_trigger)
                keyboard.wait()
            except Exception as e:
                print(f"[Hotkey Error] {e}")

        threading.Thread(target=hotkey_worker, daemon=True).start()


# -------------------------
# RUN APP
# -------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = KalkiApp(root)
    root.mainloop()