"""
Source code in llama-index-integrations/readers/llama-index-readers-google/llama_index/readers/google/calendar/base.py
"""

import os
import datetime
import json
from typing import Any, List, Optional, Union

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class GoogleCalendarReader(BaseReader):
    """Google Calendar reader.

    Reads events from Google Calendar

    """

    def load_data(
        self,
        number_of_results: Optional[int] = 100,
        start_date: Optional[Union[str, datetime.date]] = None,
        local_data_filename: Optional[str] = None,
    ) -> List[Document]:
        """Load data from user's calendar.

        Args:
            number_of_results (Optional[int]): the number of events to return. Defaults to 100.
            start_date (Optional[Union[str, datetime.date]]): the start date to return events from. Defaults to today.
        """
        from googleapiclient.discovery import build

        events_result = None
        if local_data_filename is None:
            credentials = self._get_credentials()
            service = build("calendar", "v3", credentials=credentials)

            if start_date is None:
                start_date = datetime.date.today()
            elif isinstance(start_date, str):
                start_date = datetime.date.fromisoformat(start_date)

            start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
            start_datetime_utc = start_datetime.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_datetime_utc,
                    maxResults=number_of_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        else:
            with open(local_data_filename, "r") as file:
                events_result = json.load(file)

        events = events_result.get("items", [])

        if not events:
            return []

        results = []
        for event in events:
            if "dateTime" in event["start"]:
                start_time = event["start"]["dateTime"]
            else:
                start_time = event["start"]["date"]

            if "dateTime" in event["end"]:
                end_time = event["end"]["dateTime"]
            else:
                end_time = event["end"]["date"]

            event_string = f"Status: {event['status']}, "
            event_string += f"Summary: {event['summary']}, "
            event_string += f"Start time: {start_time}, "
            event_string += f"End time: {end_time}, "

            organizer = event.get("organizer", {})
            display_name = organizer.get("displayName", "N/A")
            email = organizer.get("email", "N/A")
            if display_name != "N/A":
                event_string += f"Organizer: {display_name} ({email})"
            else:
                event_string += f"Organizer: {email}"

            results.append(Document(text=event_string))

        return results

    def _get_credentials(self) -> Any:
        """Get valid user credentials from storage.

        The file token.json stores the user's access and refresh tokens, and is
        created automatically when the authorization flow completes for the first
        time.

        Returns:
            Credentials, the obtained credential.
        """
        from google_auth_oauthlib.flow import InstalledAppFlow

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        return creds
