import chainlit as cl
import openai
import datetime
import asyncio
from dotenv import load_dotenv
from prompts import SYSTEM_PROMPT, JOURNAL_PROMPT
from langsmith.wrappers import wrap_openai
from llama_index.core import VectorStoreIndex, Document, Settings
from typing import Dict, List, Tuple
import os
import json
from google.auth.exceptions import RefreshError
import re
from calendar_utils import (
    CACHE_FILE,
    create_calendar_index,
    fetch_and_filter_calendar_events,
)
from llama_index.embeddings.ollama import OllamaEmbedding
from langfuse.decorators import observe
from langfuse.openai import AsyncOpenAI
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

from journal_functions import get_top_news, journal_search, calendar_search

# Load environment variables
load_dotenv()

function_names = ["get_top_news", "journal_search", "calendar_search"]

# Configuration
USE_OLLAMA = os.getenv("OLLAMA") == "1"

if USE_OLLAMA:
    config = {
        "endpoint_url": os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1"),
        "api_key": "ollama",  # Ollama doesn't require an API key, but we need to provide something
        "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
    }
else:
    config = {
        "endpoint_url": os.getenv("OPENAI_ENDPOINT"),
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-4",
    }

print(f"AI Provider: {'Ollama' if USE_OLLAMA else 'OpenAI'}")

# Initialize services
client = wrap_openai(
    openai.AsyncClient(api_key=config["api_key"], base_url=config["endpoint_url"])
)


# Helper functions
async def load_cache():
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        return cache["events"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


# Add this new function to handle re-authentication
async def handle_reauth():
    token_path = "token.json"
    if os.path.exists(token_path):
        os.remove(token_path)
        print(f"Deleted {token_path}")

    await cl.Message(
        content="The old token has been removed. Please restart the application to re-authenticate."
    ).send()

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

        actions = [cl.Action(name="reauth", value="reauth", label="Re-authenticate")]
        await cl.Message(
            content="Click the button below to re-authenticate:", actions=actions
        ).send()
    else:
        total_events = len(calendar_index.docstore.docs)
        today_event_count = len(todays_events)
        await cl.Message(
            content=f"I've successfully loaded {total_events} events from your calendar. You have {today_event_count} event(s) scheduled for today."
        ).send()

    cl.user_session.set("calendar_index", calendar_index)

    events_summary = f"Today's events: {len(todays_events)}"
    message_history = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": events_summary},
        {"role": "assistant", "content": welcome_message},
    ]
    cl.user_session.set("message_history", message_history)
    cl.user_session.set("current_entry", None)


def extract_json_from_response(text):
    # First, try to find JSON block enclosed in ```json ... ```
    json_pattern = r"```(json)?(.*?)```"
    json_match = re.search(json_pattern, text, re.DOTALL)

    if json_match:
        json_str = json_match.group(2).strip()
    else:
        # If no code block is found, treat the entire text as potential JSON
        json_str = text.strip()

    try:
        parsed_json = json.loads(json_str)
        return parsed_json
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
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


async def update_journal_file(filename: str, new_content: str):
    file_path = os.path.join("data", filename)

    # Read existing content
    with open(file_path, "r") as f:
        existing_content = f.read().strip()

    # Prepare the prompt for the LLM
    prompt = (
        JOURNAL_PROMPT
        + "\n\nExisting entry:\n"
        + existing_content
        + "\n\nNew input:\n"
        + new_content  # Use the new_content directly
    )

    # Generate journal entry using LLM
    updated_entry = await generate_journal_entry(prompt)

    # Write the updated entry to the file
    with open(file_path, "w") as f:
        f.write(updated_entry.strip())

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


@cl.on_message
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])
    current_entry = cl.user_session.get("current_entry")
    calendar_index = cl.user_session.get("calendar_index")

    # Check if the message is a system message for loading or reloading an entry
    if message.type == "system_message":
        print("1. System message")
        try:
            data = json.loads(message.content)
            if data.get("action") in ["load_entry", "reload_entry"]:
                filename = data.get("filename")
                if filename:
                    # Load the journal entry
                    with open(os.path.join("data", filename), "r") as f:
                        entry_content = f.read()

                    # Update the current entry
                    cl.user_session.set("current_entry", filename)

                    # Inform the user that the entry has been loaded or reloaded
                    action_verb = (
                        "reloaded" if data.get("action") == "reload_entry" else "loaded"
                    )
                    await cl.Message(
                        content=f"Journal entry '{filename}' has been {action_verb}. How can I assist you with this entry?"
                    ).send()

                    # Update the message history with the loaded entry
                    message_history.append(
                        {
                            "role": "system",
                            "content": f"{action_verb.capitalize()} journal entry: {filename}\n\n{entry_content}",
                        }
                    )
                    cl.user_session.set("message_history", message_history)
                    return
        except json.JSONDecodeError:
            pass  # If it's not a valid JSON, treat it as a regular message

    # Add user message to history
    message_history.append({"role": "user", "content": message.content})

    response_text = await generate_response(message_history)

    print("Response:")
    print(response_text)
    try:
        parsed_json = extract_json_from_response(response_text)
        print(f"Parsed JSON: {parsed_json}")

        if (
            parsed_json
            and "function_name" in parsed_json
            and parsed_json["function_name"] in function_names
        ):
            matched_function = parsed_json["function_name"]
            print(f"Matched function: {matched_function}")
            print(f"Function parameters: {parsed_json.get('params', {})}")

            function_response = await call_function(parsed_json)
            message_history.append(
                {
                    "role": "assistant",
                    "content": f"Respond using the following function call result: {function_response}",
                }
            )
            print(f"Function response: {function_response}")

            # Only generate a new response if the function_response is not an error message
            if not function_response.startswith(
                "Calendar information is unavailable"
            ) and not function_response.startswith(
                "I'm having trouble accessing your calendar"
            ):
                response_text = await generate_response(message_history)
                print(f"Generate response: {response_text}")
            else:
                response_text = function_response
        else:
            print("No valid function call found in the response")

    except Exception as e:
        print(f"Error in JSON processing: {e}")

    response_message = await print_response(response_text)
    message_history.append({"role": "assistant", "content": response_text})
    cl.user_session.set("message_history", message_history)

    # Only update the current journal entry if one is loaded
    if current_entry:
        updated_filename = await update_journal_file(current_entry, message.content)
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
async def update_journal_file(filename: str, new_content: str):
    file_path = os.path.join("data", filename)

    # Read existing content
    with open(file_path, "r") as f:
        existing_content = f.read().strip()

    # Prepare the prompt for the LLM
    prompt = (
        JOURNAL_PROMPT
        + "\n\nExisting entry:\n"
        + existing_content
        + "\n\nNew input:\n"
        + new_content  # Use the new_content directly
    )

    # Generate journal entry using LLM
    updated_entry = await generate_journal_entry(prompt)

    # Write the updated entry to the file
    with open(file_path, "w") as f:
        f.write(updated_entry.strip())

    return filename
