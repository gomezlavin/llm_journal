import os
import requests
import chainlit as cl
import asyncio
from serpapi import GoogleSearch
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

async def get_top_news():
    # Set up parameters for the API call
    params = {
        "api_key": os.getenv('SERP_API_KEY'),
        "engine": "google",
        "q": "top news articles",
        "google_domain": "google.com",
        "gl": "us",
        "hl": "en",
        "tbm": "nws"
    }

    # Perform the API search
    search = GoogleSearch(params)
    results = search.get_dict()
    
    # Check if 'news_results' are present in the API response
    if 'news_results' not in results:
        return "No top news found."

    # Initialize a string to format the output
    formatted_news = "Top News Headlines:\n\n"

    # Iterate through each news result and format the response
    for news in results['news_results']:
        title = news.get('title', 'No Title')
        source = news.get('source', 'Unknown Source')
        date = news.get('date', 'Unknown Date')
        link = news.get('link', '#')
        snippet = news.get('snippet', 'No description available.')

        # Append formatted news item to the output string
        formatted_news += f"**{title}**\n"
        formatted_news += f"Source: {source} | Date: {date}\n"
        formatted_news += f"Snippet: {snippet}\n"
        formatted_news += f"[Read more]({link})\n\n"

    # Return the formatted news headlines
    return formatted_news

async def journal_search(query):
    documents = SimpleDirectoryReader("data").load_data()

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
    response = "Calendar information is currently unavailable."

    if calendar_index:
        print("2a. Calendar index")
        try:
            query_engine = calendar_index.as_query_engine()
            query_result = query_engine.query(query)

            response = query_result
            print("respnse from calendar_search")
            print(response)
            if query_result.response:
                response = f"Relevant calendar information: {query_result.response}"
        except Exception as e:
            print(f"Error querying calendar index: {e}")
            response = "I'm having trouble accessing your calendar information at the moment."

            # Add a button for re-authentication when there's an error
            actions = [
                cl.Action(name="reauth", value="reauth", label="Re-authenticate")
            ]
            await cl.Message(
                content="There seems to be an issue with your calendar access. Would you like to re-authenticate?",
                actions=actions,
            ).send()
    else:
        print("2b. Not calendar index")

    # Add a button for re-authentication when calendar index is not available
    actions = [cl.Action(name="reauth", value="reauth", label="Re-authenticate")]
    await cl.Message(
        content="Calendar information is unavailable. Would you like to re-authenticate?",
        actions=actions,
    ).send()

    return response