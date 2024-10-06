import chainlit as cl
import openai
import datetime
from dotenv import load_dotenv
from prompts import SYSTEM_PROMPT, JOURNAL_PROMPT
from custom_calendar_reader import GoogleCalendarReader
from langsmith.wrappers import wrap_openai
from llama_index.core import VectorStoreIndex, Document
from typing import Dict, List
import os
import json

# Load environment variables
load_dotenv()

# Configuration
openai_config = {
    "endpoint_url": os.getenv("OPENAI_ENDPOINT"),
    "api_key": os.getenv("OPENAI_API_KEY"),
    "model": "gpt-4o-mini",
}

# Initialize services
client = wrap_openai(
    openai.AsyncClient(
        api_key=openai_config["api_key"], base_url=openai_config["endpoint_url"]
    )
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
    gen_kwargs = {
        "model": openai_config["model"],
        "temperature": 0.3,
        "max_tokens": 500,
    }

    stream = await client.chat.completions.create(
        messages=message_history, stream=True, **gen_kwargs
    )

    response_content = ""
    async for part in stream:
        token = part.choices[0].delta.content
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


def generate_unique_filename():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.datetime.now().strftime("%H%M%S")
    return f"{today}-{timestamp}-entry.md"


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
    gen_kwargs = {
        "model": openai_config["model"],
        "temperature": 0.7,
        "max_tokens": 1000,
    }

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
