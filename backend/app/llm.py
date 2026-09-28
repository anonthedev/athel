from langchain_openrouter import ChatOpenRouter
import os
from dotenv import load_dotenv

load_dotenv()

writer_llm = ChatOpenRouter(model="anthropic/claude-sonnet-5", api_key=os.getenv("OPENROUTER_API_KEY"))
planner_llm = ChatOpenRouter(model="openai/gpt-5-mini", api_key=os.getenv("OPENROUTER_API_KEY"))
extractor_llm = ChatOpenRouter(model="google/gemini-3.1-flash-lite", api_key=os.getenv("OPENROUTER_API_KEY"))