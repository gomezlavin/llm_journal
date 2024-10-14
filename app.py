import chainlit as cl
import openai
import datetime
import asyncio
from dotenv import load_dotenv
from prompts import SYSTEM_PROMPT, JOURNAL_PROMPT
from custom_calendar_reader import GoogleCalendarReader
from langsmith.wrappers import wrap_openai
from llama_index.core import VectorStoreIndex, Document
from typing import Dict, List, Tuple
import os
import json
from google.auth.exceptions import RefreshError
import re

# Load environment variables
load_dotenv()

from langfuse.decorators import observe
from langfuse.openai import AsyncOpenAI
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

from journal_functions import get_top_news, journal_search, calendar_search

function_names = ["get_top_news", "journal_search", "calendar_search"]

# Configuration
openai_config = {
    "endpoint_url": os.getenv("OPENAI_ENDPOINT"),
    "api_key": os.getenv("OPENAI_API_KEY"),
    "model": "gpt-4o",
}

ollama_config = {
    "endpoint_url": os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1"),
    "api_key": "ollama",  # Ollama doesn't require an API key, but we need to provide something
    "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
}

# Choose AI provider (set this to 'ollama' or 'openai')
ai_provider = "ollama" if os.getenv("OLLAMA") == "1" else "openai"

# You can also add a print statement for debugging:
print(f"AI Provider: {ai_provider}")

# Initialize services
if ai_provider == "openai":
    config = openai_config
else:
    config = ollama_config

client = wrap_openai(
    openai.AsyncClient(api_key=config["api_key"], base_url=config["endpoint_url"])
)
calendar_reader = GoogleCalendarReader()


async def create_calendar_index():
    try:
        all_events, todays_events = await fetch_and_filter_calendar_events()
        documents = [
            Document(text=event, metadata={"source": "calendar"})
            for event in all_events
        ]
        index = VectorStoreIndex.from_documents(documents)
        return index, todays_events
    except RefreshError as e:
        print(f"Error refreshing Google Calendar token: {e}")
        return None, []


# Helper functions
async def fetch_and_filter_calendar_events() -> Tuple[List[str], List[str]]:
    today = datetime.date.today()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    try:
        calendar_documents = calendar_reader.load_data(
            number_of_results=100,
            start_date=start_of_week,
            local_data_filename=os.getenv("GCAL_TEST_DATAFILE"),
        )
        all_events = [event.text for event in calendar_documents]
        todays_events = []
        for event in calendar_documents:
            start_time_match = re.search(r"Start time: (\S+)", event.text)
            if start_time_match:
                start_time_str = start_time_match.group(1).rstrip(",")
                try:
                    start_time = datetime.datetime.fromisoformat(start_time_str)
                    if start_time.date() == today:
                        todays_events.append(event.text)
                except ValueError as e:
                    print(f"Error parsing date for event: {event.text}. Error: {e}")
        return all_events, todays_events[:10]
    except RefreshError as e:
        print(f"Error refreshing Google Calendar token: {e}")
        raise
    except Exception as e:
        print(f"Error fetching calendar events: {e}")
        return [], []


@observe
async def generate_response(message_history):
    gen_kwargs = {
        "model": config["model"],
        "temperature": 0.3,
        "max_tokens": 500,
    }

    response = await client.chat.completions.create(
        messages=message_history, **gen_kwargs
    )
    response_text = response.choices[0].message.content

    return response_text


# Add this new function to handle re-authentication
async def handle_reauth():
    token_path = "token.json"
    if os.path.exists(token_path):
        os.remove(token_path)
        print(f"Deleted {token_path}")

    await cl.Message(
        content="The old token has been removed. Please restart the application to re-authenticate."
    ).send()

    # Reinitialize the calendar reader
    global calendar_reader
    calendar_reader = GoogleCalendarReader()

    # Attempt to fetch calendar events to trigger the authentication flow
    try:
        await fetch_and_filter_calendar_events()
        await cl.Message(
            content="Re-authentication successful. You can now use calendar features."
        ).send()
    except Exception as e:
        print(f"Error during re-authentication: {e}")
        await cl.Message(
            content="There was an error during re-authentication. Please check the console and ensure you've granted the necessary permissions."
        ).send()


@cl.on_chat_start
async def on_chat_start():
    welcome_message = "Hi there! I'm here to help you with your journal entries."
    await cl.Message(content=welcome_message).send()

    # Create calendar index and fetch today's events
    calendar_index, todays_events = await create_calendar_index()
    if calendar_index is None:
        await cl.Message(
            content="I'm having trouble accessing your calendar. You may need to re-authenticate."
        ).send()

        # Add a button for re-authentication
        actions = [cl.Action(name="reauth", value="reauth", label="Re-authenticate")]
        await cl.Message(
            content="Click the button below to re-authenticate:", actions=actions
        ).send()
    else:
        # Inform the user about the number of events loaded
        total_events = len(calendar_index.docstore.docs)
        today_event_count = len(todays_events)
        await cl.Message(
            content=f"I've successfully loaded {total_events} events from your calendar. You have {today_event_count} event(s) scheduled for today."
        ).send()

    cl.user_session.set("calendar_index", calendar_index)

    # Initialize message history with system prompt and today's events (without displaying them)
    events_summary = f"Today's events: {len(todays_events)}"
    message_history = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": events_summary},
        {"role": "assistant", "content": welcome_message},
    ]
    cl.user_session.set("message_history", message_history)
    cl.user_session.set("current_entry", None)


def extract_json_from_response(text):
    # Regex pattern to find JSON block enclosed in ```json ... ```
    json_pattern = r"```json(.*?)```"

    # Search for the JSON block in the response
    json_match = re.search(json_pattern, text, re.DOTALL)

    if json_match:
        json_str = json_match.group(1).strip()  # Extract the JSON block
        try:
            parsed_json = json.loads(json_str)  # Parse the JSON block
            return parsed_json
        except json.JSONDecodeError as e:
            return None
    else:
        return None


@observe
async def print_response(response_text):
    if not isinstance(response_text, str):
        response_text = str(response_text)  # Ensure it's a string

    tokens = re.split(r"(\s+)", response_text)  # Splitting while keeping whitespace

    response_message = cl.Message(content="")
    await response_message.send()

    for token in tokens:
        await response_message.stream_token(token)
        await asyncio.sleep(0.02)  # Delay of x seconds between each token

    await response_message.update()

    return response_message


@observe
async def call_function(function_json):
    if function_json["function_name"] == "get_top_news":
        response = await get_top_news()
    elif function_json["function_name"] == "journal_search":
        journal_response = await journal_search(function_json["params"]["query"])
        response = str(journal_response.response)
    elif function_json["function_name"] == "calendar_search":
        calendar_response = await calendar_search(function_json["params"]["query"])
        response = str(calendar_response)
    else:
        response = "Invalid function"

    return response


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
        "model": config["model"],
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
    calendar_index = cl.user_session.get("calendar_index")

    # Check if the message is a system message for loading an entry
    if message.type == "system_message":
        print("1. System message")
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

    response_text = await generate_response(message_history)

    print("Response text")
    print(response_text)
    try:
        parsed_json = extract_json_from_response(response_text)

        if (
            parsed_json
            and "function_name" in parsed_json
            and parsed_json["function_name"] in function_names
        ):
            matched_function = parsed_json["function_name"]
            print(f"Matched function: {matched_function}")

            function_response = await call_function(parsed_json)
            message_history.append({"role": "system", "content": function_response})
            print(f"Function response: {function_response}")
            response_text = await generate_response(message_history)
            print(f"Generate response: {response_text}")

    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")

    response_message = await print_response(response_text)
    message_history.append({"role": "assistant", "content": response_text})
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


@cl.action_callback("reauth")
async def on_action(action):
    await handle_reauth()


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
