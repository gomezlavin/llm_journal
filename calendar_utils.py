import asyncio
from custom_calendar_reader import GoogleCalendarReader
import datetime
import re
import json
from google.auth.exceptions import RefreshError
from llama_index.core import VectorStoreIndex, Document, Settings
import os
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding  # Add this import

# Define and export CACHE_FILE
CACHE_FILE = os.path.join("data", "calendar_cache.json")

# Add this line near the top of the file, after imports
calendar_reader = GoogleCalendarReader()

# Choose AI provider
USE_OLLAMA = os.getenv("OLLAMA") == "1"

# Ollama embedding configuration
OLLAMA_EMBEDDING_CONFIG = {
    "model_name": os.getenv("OLLAMA_MODEL", "llama3.2"),
    "base_url": os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434"),
    "ollama_additional_kwargs": {"mirostat": 0},
}

# OpenAI embedding configuration
OPENAI_EMBEDDING_CONFIG = {
    "model": "text-embedding-ada-002",  # or whichever model you prefer
    "api_key": os.getenv("OPENAI_API_KEY"),
}


def load_cache():
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        return cache["events"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


def fetch_and_filter_calendar_events(target_date=None, force_refresh=False):
    if target_date:
        target_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        target_date = datetime.date.today()

    start_date = target_date - datetime.timedelta(days=7)
    end_date = target_date + datetime.timedelta(days=7)

    try:
        if not force_refresh:
            cached_events = load_cache()
            if cached_events:
                return cached_events["all_events"], []

        calendar_documents = calendar_reader.load_data(
            number_of_results=100,
            start_date=start_date,
        )

        all_events = [event.text for event in calendar_documents]
        filtered_events = [
            event
            for event in all_events
            if start_date
            <= datetime.datetime.fromisoformat(
                re.search(r"Start time: (\S+)", event).group(1).rstrip(",")
            ).date()
            <= end_date
        ]

        save_cache(
            {
                "all_events": filtered_events,
                "last_updated": datetime.datetime.now().isoformat(),
            }
        )
        return filtered_events, []
    except RefreshError as e:
        print(f"Error refreshing Google Calendar token: {e}")
        raise
    except Exception as e:
        print(f"Error fetching calendar events: {e}")
        return [], []


async def create_calendar_index():
    try:
        all_events, todays_events = fetch_and_filter_calendar_events()
        documents = [
            Document(text=event, metadata={"source": "calendar"})
            for event in all_events
        ]

        if USE_OLLAMA:
            ollama_embedding = OllamaEmbedding(**OLLAMA_EMBEDDING_CONFIG)
            Settings.embed_model = ollama_embedding
        else:
            openai_embedding = OpenAIEmbedding(**OPENAI_EMBEDDING_CONFIG)
            Settings.embed_model = openai_embedding

        # Create the index with the appropriate embedding
        index = VectorStoreIndex.from_documents(documents)
        return index, todays_events
    except RefreshError as e:
        print(f"Error refreshing Google Calendar token: {e}")
        return None, []


# Add any other calendar-related functions as needed
