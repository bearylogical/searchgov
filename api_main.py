import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from src.api import create_api  # noqa: E402

app = create_api()

if __name__ == "__main__":
    dev = os.getenv("ENV", "production").lower() == "development"
    uvicorn.run("api_main:app", host="0.0.0.0", port=8081, reload=dev)
