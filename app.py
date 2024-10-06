import chainlit as cl
import openai
import datetime
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
    calendar_index = cl.user_session.get("calendar_index")

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

    # Query the calendar index for relevant events if available
    if calendar_index:
        try:
            query_engine = calendar_index.as_query_engine()
            query_result = query_engine.query(message.content)

            # Add relevant calendar information to the message history
            if query_result.response:
                message_history.append(
                    {
                        "role": "system",
                        "content": f"Relevant calendar information: {query_result.response}",
                    }
                )
        except Exception as e:
            print(f"Error querying calendar index: {e}")
            message_history.append(
                {
                    "role": "system",
                    "content": "I'm having trouble accessing your calendar information at the moment.",
                }
            )

            # Add a button for re-authentication when there's an error
            actions = [
                cl.Action(name="reauth", value="reauth", label="Re-authenticate")
            ]
            await cl.Message(
                content="There seems to be an issue with your calendar access. Would you like to re-authenticate?",
                actions=actions,
            ).send()
    else:
        message_history.append(
            {
                "role": "system",
                "content": "Calendar information is currently unavailable.",
            }
        )

        # Add a button for re-authentication when calendar index is not available
        actions = [cl.Action(name="reauth", value="reauth", label="Re-authenticate")]
        await cl.Message(
            content="Calendar information is unavailable. Would you like to re-authenticate?",
            actions=actions,
        ).send()

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
