from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass(frozen=True)
class Settings:
    aoai_endpoint: str = os.environ["AZURE_OPENAI_ENDPOINT"]
    aoai_key: str = os.environ["AZURE_OPENAI_KEY"]
    aoai_api_version: str = os.environ["AZURE_OPENAI_API_VERSION"]
    chat_deployment: str = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]
    embed_deployment: str = os.environ["AZURE_OPENAI_EMBED_DEPLOYMENT"]
    search_endpoint: str = os.environ["AZURE_SEARCH_ENDPOINT"]
    search_key: str = os.environ["AZURE_SEARCH_KEY"]
    search_index: str = os.environ["AZURE_SEARCH_INDEX"] 

settings = Settings()
