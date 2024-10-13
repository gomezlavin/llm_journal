import os
import requests
from serpapi import GoogleSearch
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

def get_top_news():
    # Set up parameters for the API call
    params = {
        "api_key": os.getenv('SERP_API_KEY'),
        "engine": "google",
        "q": "top stories",
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

def journal_search(query):
    documents = SimpleDirectoryReader("data").load_data()

    # Create an index from the documents
    index = VectorStoreIndex.from_documents(documents)

    # Create a query engine
    query_engine = index.as_query_engine()

    # Example query
    response = query_engine.query(query)
    print(response)

    return response