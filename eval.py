import openai
import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langsmith.evaluation import evaluate, LangChainStringEvaluator
from langsmith.schemas import Run, Example
from openai import OpenAI
from app import configurations, SYSTEM_PROMPT, CONFIG_KEY, GoogleCalendarReader
import json

from dotenv import load_dotenv

from langsmith.wrappers import wrap_openai
from langsmith import traceable

load_dotenv()

# Evaluators
qa_evalulator = [LangChainStringEvaluator("cot_qa")]
dataset_name = "llm_journaling_test-gcal-retrieval"

# Initialize services
config = configurations[CONFIG_KEY]

client = wrap_openai(
    openai.AsyncClient(api_key=config["api_key"], base_url=config["endpoint_url"])
)
calendar_reader = GoogleCalendarReader()

def run_sync(api_call):
    return asyncio.run(api_call)

@traceable
def gcal_retrieval_accuracy_evaluator(run: Run, example: Example) -> dict:
    print(f"example.inputs >>>{example.inputs}<<<")
    print(f"example.outputs >>>{example.outputs}<<<")
    inputs = example.inputs['question']['input']
    outputs = example.outputs['answer']['output']

    # Extract system prompt
    system_prompt = next((msg['data']['content'] for msg in inputs if msg['type'] == 'system'), "")
    #system_prompt = SYSTEM_PROMPT #XXX 

    # Extract message history
    message_history = []
    for msg in inputs:
        if msg['type'] in ['human', 'ai']:
            message_history.append({
                "role": "user" if msg['type'] == 'human' else "assistant",
                "content": msg['data']['content']
            })

    # Extract latest user message and model output
    latest_message = message_history[-1]['content'] if message_history else ""
    model_output = outputs['data']['content']

    evaluation_prompt = f"""
    System Prompt: {system_prompt}

    Message History:
    {json.dumps(message_history, indent=2)}

    Latest User Message: {latest_message}

    Model Output: {model_output}

    Based on the above information, evaluate the model's output for compliance with the system prompt and context of the conversation. 
    Provide a score from 0 to 10, where 0 is completely non-compliant and 10 is perfectly compliant.
    Also provide a brief explanation for your score.

    Respond in the following JSON format:
    {{
        "score": <int>,
        "explanation": "<string>"
    }}
    """

    response = run_sync(client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an AI assistant tasked with evaluating the compliance of model outputs to given prompts and conversation context."},
            {"role": "user", "content": evaluation_prompt}
        ],
        temperature=0.2
    ))

    print(f"response >>>{response}<<<")
    try:
        result = json.loads(response.choices[0].message.content)
        return {
            "key": "gcal_retrieval_accuracy",
            "score": result["score"] / 10,  # Normalize to 0-1 range
            "reason": result["explanation"]
        }
    except json.JSONDecodeError:
        return {
            "key": "gcal_retrieval_accuracy",
            "score": 0,
            "reason": "Failed to parse evaluator response"
        }


# A string to prefix the experiment name with.
experiment_prefix = "Python journaling gcal retrieval accuracy"

# List of evaluators to score the outputs of target task
evaluators = [
    gcal_retrieval_accuracy_evaluator
]

# Evaluate the target task
results = evaluate(
    lambda inputs: inputs,
    data=dataset_name,
    evaluators=evaluators,
    experiment_prefix=experiment_prefix,
)

print(results)
