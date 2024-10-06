import chainlit as cl
import openai
import datetime
from dotenv import load_dotenv
from prompts import SYSTEM_PROMPT, JOURNAL_PROMPT
from custom_calendar_reader import GoogleCalendarReader
from langsmith.wrappers import wrap_openai
from llama_index.core import VectorStoreIndex, Document
from llama_index.core.retrievers import VectorIndexRetriever
from typing import Dict, List
import os
import json
from datetime import date
from flask import Flask, jsonify, send_file
import markdown
import re

# Load environment variables
load_dotenv()

# Configuration
configurations = {
    "mistral_7B_instruct": {
        "endpoint_url": os.getenv("MISTRAL_7B_INSTRUCT_ENDPOINT"),
        "api_key": os.getenv("RUNPOD_API_KEY"),
        "model": "mistralai/Mistral-7B-Instruct-v0.2",
    },
    "mistral_7B": {
        "endpoint_url": os.getenv("MISTRAL_7B_ENDPOINT"),
        "api_key": os.getenv("RUNPOD_API_KEY"),
        "model": "mistralai/Mistral-7B-v0.1",
    },
    "openai_gpt-4": {
        "endpoint_url": os.getenv("OPENAI_ENDPOINT"),
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-4o-mini",
    },
}

CONFIG_KEY = "openai_gpt-4"
ENABLE_SYSTEM_PROMPT = True

# Initialize services
config = configurations[CONFIG_KEY]
client = wrap_openai(
    openai.AsyncClient(api_key=config["api_key"], base_url=config["endpoint_url"])
)
calendar_reader = GoogleCalendarReader()


async def create_calendar_index():
    calendar_events = await fetch_calendar_events()
    documents = [
        Document(text=event, metadata={"source": "calendar"})
        for event in calendar_events
    ]
    index = VectorStoreIndex.from_documents(documents)
    return index


# Helper functions
async def fetch_calendar_events() -> List[str]:
    today = datetime.date.today()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    calendar_documents = calendar_reader.load_data(
        number_of_results=100,
        start_date=start_of_week,
        local_data_filename=os.getenv("GCAL_TEST_DATAFILE"),
    )
    return [event.text for event in calendar_documents]


async def generate_response(message_history: List[Dict[str, str]]) -> str:
    gen_kwargs = {"model": config["model"], "temperature": 0.3, "max_tokens": 500}

    if CONFIG_KEY == "mistral_7B":
        stream = await client.completions.create(
            prompt=message_history[-1]["content"], stream=True, **gen_kwargs
        )
    else:
        stream = await client.chat.completions.create(
            messages=message_history, stream=True, **gen_kwargs
        )

    response_content = ""
    async for part in stream:
        token = (
            part.choices[0].text
            if CONFIG_KEY == "mistral_7B"
            else part.choices[0].delta.content
        )
        if token:
            response_content += token
            yield token


async def fetch_todays_events() -> List[str]:
    today = datetime.date.today()
    calendar_documents = calendar_reader.load_data(
        number_of_results=10, start_date=today, end_date=today
    )
    return [event.text for event in calendar_documents]


@cl.on_chat_start
async def on_chat_start():
    today = datetime.date.today()
    welcome_message = "Hi there! I'm here to help you with your journal entries."
    await cl.Message(content=welcome_message).send()

    # Initialize message history
    message_history = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "assistant", "content": welcome_message},
    ]
    cl.user_session.set("message_history", message_history)
    cl.user_session.set("current_entry", None)

    # Create calendar index to load events
    await create_calendar_index()  # Call to fetch and index calendar events


def format_event(event):
    import re
    from datetime import datetime

    print(f"format event: {event}")
    summary_match = re.search(r"Summary: (.+?),", event)
    print(f"summary match: {summary_match}")

    start_time_match = re.search(r"Start time: (.+?)[,+]", event)
    print(f"start time match: {start_time_match}")
    end_time_match = re.search(r"End time: (.+?)[,+]", event)
    print(f"end time match: {start_time_match}")

    if summary_match and start_time_match and end_time_match:
        summary = summary_match.group(1)
        start_time = datetime.fromisoformat(start_time_match.group(1))
        end_time = datetime.fromisoformat(end_time_match.group(1))

        formatted_time = (
            f"{start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
        )
        return f"- {summary} ({formatted_time})"
    else:
        return "- Unable to parse event details"


def generate_unique_filename():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.datetime.now().strftime("%H%M%S")
    return f"{today}-{timestamp}-entry.md"


# Update this function to handle journal updates
async def update_journal_file(message_history: List[Dict[str, str]]):
    filename = generate_unique_filename()
    file_path = os.path.join("data", filename)

    # Prepare the prompt for the LLM
    prompt = (
        JOURNAL_PROMPT
        + "\n\nConversation:\n"
        + "\n".join([f"{msg['role']}: {msg['content']}" for msg in message_history])
    )

    # Generate journal entry using LLM
    journal_entry = await generate_journal_entry(prompt)

    # Write the generated entry to the file
    with open(file_path, "w") as f:
        f.write(journal_entry.strip())

    return filename


async def generate_journal_entry(prompt: str) -> str:
    gen_kwargs = {"model": config["model"], "temperature": 0.7, "max_tokens": 1000}

    if CONFIG_KEY == "mistral_7B":
        response = await client.completions.create(prompt=prompt, **gen_kwargs)
        journal_entry = response.choices[0].text
    else:
        response = await client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}], **gen_kwargs
        )
        journal_entry = response.choices[0].message.content

    return journal_entry


@cl.on_message
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    current_entry = cl.user_session.get("current_entry")

    # Check if the message is a system message for loading an entry
    if message.type == "system_message":
        try:
            data = json.loads(message.content)
            if data.get("action") == "load_entry":
                filename = data.get("filename")
                if filename:
                    # Load the journal entry
                    with open(os.path.join("data", filename), "r") as f:
                        entry_content = f.read()

                    # Update the current entry
                    cl.user_session.set("current_entry", filename)

                    # Inform the user that the entry has been loaded
                    await cl.Message(
                        content=f"Journal entry '{filename}' has been loaded. How can I assist you with this entry?"
                    ).send()

                    # Update the message history with the loaded entry
                    message_history.append(
                        {
                            "role": "system",
                            "content": f"Loaded journal entry: {filename}\n\n{entry_content}",
                        }
                    )
                    cl.user_session.set("message_history", message_history)
                    return
        except json.JSONDecodeError:
            pass  # If it's not a valid JSON, treat it as a regular message

    # Add user message to history
    message_history.append({"role": "user", "content": message.content})

    response_message = cl.Message(content="")

    full_response = ""
    async for token in generate_response(message_history):
        full_response += token
        await response_message.stream_token(token)

    await response_message.update()

    message_history.append({"role": "assistant", "content": full_response})
    cl.user_session.set("message_history", message_history)

    # Only update the current journal entry if one is loaded
    if current_entry:
        updated_filename = await update_journal_file(current_entry, message_history)

        # Use CopilotFunction to notify the frontend
        if cl.context.session.client_type == "copilot":
            fn = cl.CopilotFunction(
                name="update_journal", args={"filename": updated_filename}
            )
            await fn.acall()


# Update this function to handle journal updates for a specific entry
async def update_journal_file(filename: str, message_history: List[Dict[str, str]]):
    file_path = os.path.join("data", filename)

    # Prepare the prompt for the LLM
    prompt = (
        JOURNAL_PROMPT
        + "\n\nConversation:\n"
        + "\n".join([f"{msg['role']}: {msg['content']}" for msg in message_history])
    )

    # Generate journal entry using LLM
    journal_entry = await generate_journal_entry(prompt)

    # Write the generated entry to the file
    with open(file_path, "w") as f:
        f.write(journal_entry.strip())

    return filename


app = Flask(__name__, static_folder="static")


@app.route("/api/journal-entries")
def get_journal_entries():
    entries = []
    for filename in os.listdir("data"):
        if filename.endswith(".md"):
            file_path = os.path.join("data", filename)
            with open(file_path, "r") as f:
                content = f.read().split("\n")
                title = content[0].strip("# ")  # Remove Markdown heading syntax
                body = content[1] if len(content) > 1 else ""
                date_str = filename.split("-")[:3]
                date = "-".join(date_str[:3])  # Keep as YYYY-MM-DD
                preview = body[:100] + "..." if len(body) > 100 else body
                entries.append(
                    {
                        "date": date,
                        "title": title,
                        "preview": preview,
                        "filename": filename,
                    }
                )
    return jsonify(sorted(entries, key=lambda x: x["filename"], reverse=True))


@app.route("/api/journal-entry/<filename>")
def get_journal_entry(filename):
    file_path = os.path.join("data", filename)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            content = f.read()
            html_content = markdown.markdown(content)
            return html_content
    return "Entry not found", 404


@app.route("/api/new-entry", methods=["POST"])
def create_new_entry():
    filename = generate_unique_filename()
    title = f"Today, ..."
    file_path = os.path.join("data", filename)

    # Create a new entry file
    with open(file_path, "w") as f:
        f.write(f"# {title}\n\n")

    return jsonify(
        {
            "filename": filename,
            "title": title,
            "date": filename.split("-")[0],
            "preview": "",
        }
    )


@app.route("/")
def serve_journal():
    return send_file("journal.html")


@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)


if __name__ == "__main__":
    app.run(debug=True)
