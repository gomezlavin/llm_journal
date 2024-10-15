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

    # Append new content to existing content
    updated_entry = f"{existing_content}\n\n{new_content}"

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
        print("Received system message:", message.content)
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
                        content=f"Journal entry '{filename}' has been {action_verb}."
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

    # Determine the type of user input
    user_input = message.content.strip()
    if user_input.lower().startswith("q:"):
        # Question mode: Use SYSTEM_PROMPT
        system_prompt = SYSTEM_PROMPT
        user_content = user_input[2:].strip()
        message_type = "question"

        # Include the current journal entry context if available
        if current_entry:
            with open(os.path.join("data", current_entry), "r") as f:
                entry_content = f.read()
            user_content = f"Current journal entry:\n\n{entry_content}\n\nUser question: {user_content}"
    elif user_input.lower().startswith("j:"):
        # Journal mode: Use JOURNAL_PROMPT
        system_prompt = JOURNAL_PROMPT
        user_content = user_input[2:].strip()
        message_type = "journal"
    else:
        # Inform the user about using prefixes
        await cl.Message(
            content=(
                "To help me understand your intent better, please use these prefixes:\n"
                "- Start with 'j:' to update your journal entry\n"
                "- Start with 'q:' to ask a general question\n"
                "For now, I'll treat your input as a journal entry."
            )
        ).send()
        system_prompt = JOURNAL_PROMPT
        user_content = user_input
        message_type = "journal"

    # Update message history with the appropriate system prompt
    message_history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    response_text = ""  # Initialize response_text

    # Generate response based on the message type
    if message_type == "question":
        response_text = await generate_response(message_history)

        # Handle function calls for questions
        try:
            parsed_json = extract_json_from_response(response_text)
            if (
                parsed_json
                and "function_name" in parsed_json
                and parsed_json["function_name"] in function_names
            ):
                function_response = await call_function(parsed_json)
                message_history.append(
                    {
                        "role": "assistant",
                        "content": f"Function call result: {function_response}",
                    }
                )
                response_text = await generate_response(message_history)
        except Exception as e:
            print(f"Error in JSON processing: {e}")

        await print_response(response_text)
    elif message_type == "journal" and current_entry:
        updated_filename = await update_journal_file(current_entry, user_content)
        response_text = f"Journal entry '{updated_filename}' has been updated."
        await cl.Message(content=response_text).send()

        # Notify the frontend about the update
        if cl.context.session.client_type == "copilot":
            fn = cl.CopilotFunction(
                name="update_journal", args={"filename": updated_filename}
            )
            await fn.acall()
    else:
        response_text = (
            "No current journal entry is loaded. Please load an entry before updating."
        )
        await cl.Message(content=response_text).send()

    # Update the message history
    message_history.append({"role": "assistant", "content": response_text})
    cl.user_session.set("message_history", message_history)


@cl.action_callback("reauth")
async def on_action(action):
    await handle_reauth()


# Update this function to handle journal updates for a specific entry
async def update_journal_file(filename: str, new_content: str):
    file_path = os.path.join("data", filename)

    # Read existing content
    with open(file_path, "r") as f:
        existing_content = f.read().strip()

    # Append new content to existing content
    updated_entry = f"{existing_content}\n\n{new_content}"

    # Write the updated entry to the file
    with open(file_path, "w") as f:
        f.write(updated_entry.strip())

    return filename
