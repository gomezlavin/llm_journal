import asyncio
from custom_calendar_reader import GoogleCalendarReader
import datetime
import re
import os
from google.auth.exceptions import RefreshError
from llama_index.core import VectorStoreIndex, Document

calendar_reader = GoogleCalendarReader()


def fetch_and_filter_calendar_events():
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


# Add any other calendar-related functions as needed
