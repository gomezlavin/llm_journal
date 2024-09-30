from langsmith import Client
from dotenv import load_dotenv
import prompts
import os
import app
load_dotenv()
client = Client()
print( f"Client: {client}")
dataset_name = "llm_journaling_test-gcal-retrieval"


#inputs = [
#    "How many events were scheduled today?",
#    "With whom did I have a business meeting?",
#    "With whom did I have a friendly dinner?",
#    "How long was my meditation session?",
#    "How long was my jogging session?"
#]

#outputs = [
#    "4",
#    "Sandra",
#    "Josh",
#    "15 minutes",
 #   "30 minutes"
#]

inputs = [{
    'input': [
        {
            'type': 'system',
            'data': {
                'content': app.SYSTEM_PROMPT
            }
        },
        {
            'type': 'human',
            'data': {
                'content': "How long was my meditation session?"
            }
        },
        {
            'type': 'ai',
            'data': {
                'content': "15 minutes"
            }
        }
    ]
}]

outputs = [{
    'output': {
        'data': {
            'content': "The weather is sunny with a high of 75°F."
        }
    }
}]

# Store
dataset = client.create_dataset(
    dataset_name=dataset_name,
    description="QA pairs to test calendar retrieval via LLM",
)
client.create_examples(
    inputs=[{"question": q} for q in inputs],
    outputs=[{"answer": a} for a in outputs],
    dataset_id=dataset.id,
)
