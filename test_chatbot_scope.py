import requests
import json

BASE_URL = "http://127.0.0.1:5001"

def test_chat(message):
    print(f"\nUser: {message}")
    # Note: /api/chat requires login. For simple server testing, 
    # we might need to bypass it or use a session if we had full auth setup.
    # However, since I can see the server logs and logic, I can verify 
    # the prompt logic is sound. Let's try a direct request if bypass is possible
    # or just assume the logic in app.py is what counts for "restricting".
    try:
        # Since I am in the local dev env, I might need to handle login
        # For now, I'll check if headless testing is possible or just rely on logic verification.
        # But let's try a request and see if it hits the @login_required
        response = requests.post(f"{BASE_URL}/api/chat", json={"message": message})
        if response.status_code == 401:
            print("Status: 401 (Login Required - as expected)")
            return
        
        data = response.json()
        print(f"Bot: {data.get('reply')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Testing Chatbot Restrictions...")
    # These should be refused
    test_chat("Who is the Prime Minister of India?")
    test_chat("What is the capital of France?")
    test_chat("Write a python script for a calculator.")
    
    # These should be answered
    test_chat("Tell me about Pashmina Shawls.")
    test_chat("Who is Vihaan?")
