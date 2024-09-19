# LLM Journaling Assistant

## Overview

The **LLM Journaling Assistant** is a conversational AI application designed to help you maintain a detailed and polished personal journal. By integrating with your Google Calendar, the app prompts you throughout the day to reflect on your meetings and events, making journaling easier and more intuitive.

## Key Features

- **Google Calendar Integration**: The app connects to your Google Calendar to identify meetings and events, allowing it to send timely prompts to help you reflect and journal about each event.
  
- **Smart Prompts**: After each meeting, the chatbot asks relevant questions, such as how the meeting went, how you felt, and other important details. These questions help you capture key information for your journal.

- **Meeting Context**: The app automatically pulls in relevant details from the meeting invite, including the attendees, meeting agenda, and other notes. This information is used to enhance your journal entries, saving you the time and effort of filling in these details manually.

- **Event Reminders**: The assistant will remind you throughout the day to journal about your meetings and events. You can snooze or decline reminders based on your schedule and preferences.

- **Polished Journal Entries**: The app gathers your responses and creates well-written journal entries that are ready to read or share. Whether you choose to keep your entries private or share them, they’ll always be polished and easy to review.

- **Yearly Reviews**: The app can generate summaries of your year, highlighting key events and insights. These summaries are designed to help you reflect on your progress and accomplishments.

- **"One Year Ago" Feature**: Want to know how you felt a year ago? The assistant can pull up summaries of your journal entries from exactly one year ago, providing insights into how you were feeling and what you were experiencing.

- **Global News Context**: Using Retrieval-Augmented Generation (RAG), the app pulls the most relevant global and local news from that day and creates a short paragraph summarizing it. This section, titled "What Was Happening in the World," helps give context to your journal entries by including external events that may have influenced your mood or thoughts.

## Installation

To install and run the LLM Journaling Assistant locally:

1. Clone the repository:
    ```bash
   git clone https://github.com/yourusername/llm-journaling-assistant.git
   ```

2.	Navigate to the project directory:
    ```bash
    cd llm-journaling-assistant
    ```

3.	Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4.	Set up your Google Calendar API credentials and add them to the project’s .env file.

5.	Run the application:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Once the app is running, it will begin by connecting to your Google Calendar and scanning for upcoming events. The LLM chatbot will engage with you via a chat interface, prompting you with questions after each meeting or event.

You can interact with the chatbot by responding to prompts or managing reminders. At the end of each day, the assistant will compile your responses into a polished journal entry.

## Future Enhancements

- **Advanced Search**: Allow users to search their journal entries by date, keyword, or mood.
- **Mood Tracking**: Provide analytics on the user’s mood over time based on journal entries.
- **Integration with Other Apps**: Integrate with other platforms like Slack or Zoom to offer even more context for journal entries.

## Contributing

We welcome contributions to improve the LLM Journaling Assistant. Please open an issue or submit a pull request with detailed information on any proposed changes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Authors

- Santiago Gomez ([github.com/gomezlavin](https://github.com/gomezlavin))
- Isaac Ho ([github.com/isaacyho](https://github.com/isaacyho))
- Harley Trung ([github.com/harley](https://github.com/harley))
