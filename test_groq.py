
import os
from groq import Groq

api_key = "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"
client = Groq(api_key=api_key)

try:
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Hello",
            }
        ],
        model="llama-3.3-70b-versatile",
    )
    print("SUCCESS:", chat_completion.choices[0].message.content)
except Exception as e:
    print("FAILURE:", e)
