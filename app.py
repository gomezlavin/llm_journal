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
        number_of_results=100, start_date=start_of_week, local_data_filename=os.getenv("GCAL_TEST_DATAFILE")
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
    welcome_message = f"Hi there! I'm here to help you update your journal for today, {today.strftime('%B %d, %Y')}. Let's take a look at your recent events to get started."
    await cl.Message(content=welcome_message).send()

    index = await create_calendar_index()
    retriever = VectorIndexRetriever(index=index, similarity_top_k=3)
    query_engine = index.as_query_engine()

    today_query = f"What events are relevant for journaling about today, {today.strftime('%Y-%m-%d')}?"
    response = query_engine.query(today_query)

    if response.source_nodes:
        events = [node.text for node in response.source_nodes]
        event_summary = "\n".join(format_event(event) for event in events)
        follow_up = f"I found some events that might be interesting to journal about:\n\n{event_summary}\n\nWhich one would you like to start with?"
    else:
        follow_up = "I don't see any specific events for today. Is there anything particular you'd like to reflect on in your journal?"

    await cl.Message(content=follow_up).send()

    # Initialize message history with system prompt and initial messages
    message_history = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "assistant", "content": welcome_message},
        {"role": "assistant", "content": follow_up},
    ]
    cl.user_session.set("message_history", message_history)


def format_event(event):
    import re
    from datetime import datetime

    print(f"format event: {event}")
    summary_match = re.search(r"Summary: (.+?),", event)
    print(f"summary match: {summary_match}")

    start_time_match = re.search(r"Start time: (.+?)[,+]", event)
    print(f"start time match: {start_time_match}")
    end_time_match = re.search(r"End time: (.+?)[,+]", event)
    print(f"end time match: {end_time_match}")

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


# Add this function to handle journal updates
async def update_journal_file(message_history: List[Dict[str, str]]):
    today = date.today()
    filename = f"data/{today.strftime('%Y-%m-%d')}-entry.md"

    # Prepare the prompt for the LLM
    prompt = JOURNAL_PROMPT + "\n\nConversation:\n" + "\n".join([f"{msg['role']}: {msg['content']}" for msg in message_history])

    # Generate journal entry using LLM
    journal_entry = await generate_journal_entry(prompt)

    # Write the generated entry to the file
    with open(filename, "w") as f:
        f.write(f"# Journal Entry for {today.strftime('%B %d, %Y')}\n\n")
        f.write(journal_entry)


async def generate_journal_entry(prompt: str) -> str:
    gen_kwargs = {"model": config["model"], "temperature": 0.7, "max_tokens": 1000}

    if CONFIG_KEY == "mistral_7B":
        response = await client.completions.create(prompt=prompt, **gen_kwargs)
        journal_entry = response.choices[0].text
    else:
        response = await client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            **gen_kwargs
        )
        journal_entry = response.choices[0].message.content

    return journal_entry


@cl.on_message
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history", [])

    # Add user message to history
    message_history.append({"role": "user", "content": message.content})

    # Change this part
    actions = [
        cl.Action(
            name="Show Entry",
            value="show_entry",
            description="Show the journal entry for today",
        )
    ]

    response_message = cl.Message(content="", actions=actions)

    full_response = ""
    async for token in generate_response(message_history):
        full_response += token
        await response_message.stream_token(token)

    await response_message.update()

    message_history.append({"role": "assistant", "content": full_response})
    cl.user_session.set("message_history", message_history)

    # Update the journal file with the LLM-generated entry
    await update_journal_file(message_history)

# Update the show_journal action to read from the file
@cl.action_callback("Show Entry")
async def show_entry(action):
    today = date.today()
    filename = f"data/{today.strftime('%Y-%m-%d')}-entry.md"

    if os.path.exists(filename):
        with open(filename, "r") as f:
            journal_content = f.read()
        await cl.Message(
            f"Here's your journal for today:\n\n```markdown\n{journal_content}\n```"
        ).send()
    else:
        await cl.Message("No journal entry found for today.").send()

