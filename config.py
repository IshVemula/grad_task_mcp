from pathlib import Path
from dotenv import dotenv_values


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

config = dotenv_values(ENV_FILE)

APP_NAME = config.get(
    "APP_NAME",
    "Grad Student Task Manager",
)