import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Set your API key here or via environment variable GOOGLE_API_KEY
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "Missing GOOGLE_API_KEY. Set it in the environment or assign API_KEY in this script."
    )

client = genai.Client(api_key=API_KEY)

model_entries = []
for m in client.models.list():
    name = m.name
    if name.startswith("models/"):
        name = "google/" + name[len("models/") :]
    model_entries.append(name)

print('  "models": {')
for i, name in enumerate(model_entries):
    comma = "," if i < len(model_entries) - 1 else ""
    print(f'    "{name}": {{}}{comma}')
print("  },")