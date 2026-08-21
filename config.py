import os
from dotenv import load_dotenv

load_dotenv()  # loads .env for local dev; harmless no-op if no .env file exists (e.g. on Render)

TOKEN = os.getenv("TOKEN")
ERLC_SERVER_KEY = os.getenv("ERLC_SERVER_KEY")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority")

