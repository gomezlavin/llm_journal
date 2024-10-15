import os
import requests
import chainlit as cl
import asyncio
from serpapi import GoogleSearch
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding


async def get_top_news():
    # Set up parameters for the API call
    params = {
        "api_key": os.getenv("SERP_API_KEY"),
        "engine": "google",
        "q": "top news articles",
        "google_domain": "google.com",
        "gl": "us",
        "hl": "en",
        "tbm": "nws",
    }

    # Perform the API search
    search = GoogleSearch(params)
    results = search.get_dict()

    # Check if 'news_results' are present in the API response
    if "news_results" not in results:
        return "No top news found."

    # Initialize a string to format the output
    formatted_news = "Top News Headlines:\n\n"

    # Iterate through each news result and format the response
    for news in results["news_results"]:
        title = news.get("title", "No Title")
        source = news.get("source", "Unknown Source")
        date = news.get("date", "Unknown Date")
        link = news.get("link", "#")
        snippet = news.get("snippet", "No description available.")

        # Append formatted news item to the output string
        formatted_news += f"**{title}**\n"
        formatted_news += f"Source: {source} | Date: {date}\n"
        formatted_news += f"Snippet: {snippet}\n"
        formatted_news += f"[Read more]({link})\n\n"

    # Return the formatted news headlines
    return formatted_news


async def journal_search(query):
    documents = SimpleDirectoryReader("data").load_data()

    if USE_OLLAMA:
        ollama_embedding = OllamaEmbedding(**OLLAMA_EMBEDDING_CONFIG)
        Settings.embed_model = ollama_embedding
    else:
        openai_embedding = OpenAIEmbedding(**OPENAI_EMBEDDING_CONFIG)
        Settings.embed_model = openai_embedding

    # Create an index from the documents
    index = VectorStoreIndex.from_documents(documents)

    # Create a query engine
    query_engine = index.as_query_engine()

    # Example query
    response = query_engine.query(query)
    print(response)

    return response


async def calendar_search(query):
    calendar_index = cl.user_session.get("calendar_index")

    if calendar_index:
        try:
            query_engine = calendar_index.as_query_engine()

            # Add debugging information
            print(f"Query engine type: {type(query_engine)}")
            print(f"Query: {query}")

            query_result = query_engine.query(query)

            response = str(query_result)
            print("Response from calendar_search:")
            print(response)
            return response
        except Exception as e:
            print(f"Error querying calendar index: {e}")
            print(f"Error type: {type(e).__name__}")
            print(f"Error details: {str(e)}")

            error_message = (
                "I'm having trouble accessing your calendar information at the moment. "
                "There might be an issue with the calendar data or the query processing."
            )

            # Add a button for re-authentication when there's an error
            actions = [
                cl.Action(name="reauth", value="reauth", label="Re-authenticate")
            ]
            await cl.Message(
                content=f"{error_message} Would you like to re-authenticate?",
                actions=actions,
            ).send()
            return error_message
    else:
        print("Calendar index not available")
        error_message = "Calendar information is unavailable."

        # Add a button for re-authentication when calendar index is not available
        actions = [cl.Action(name="reauth", value="reauth", label="Re-authenticate")]
        await cl.Message(
            content=f"{error_message} Would you like to re-authenticate?",
            actions=actions,
        ).send()
        return error_message


# Add these configurations at the top of the file
USE_OLLAMA = os.getenv("OLLAMA") == "1"

OLLAMA_EMBEDDING_CONFIG = {
    "model_name": os.getenv("OLLAMA_MODEL", "llama3.2"),
    "base_url": os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434"),
    "ollama_additional_kwargs": {"mirostat": 0},
}

OPENAI_EMBEDDING_CONFIG = {
    "model": "text-embedding-ada-002",
    "api_key": os.getenv("OPENAI_API_KEY"),
}
