import asyncio
from uuid import uuid4

from orchestrator import handle_incoming

thread_id = uuid4()

if __name__ == "__main__":
    while True:
        message = input("\nwhat is your question? ")
        if message.lower() in ["exit","q"]:
            break
        result = asyncio.run(handle_incoming(message,str(thread_id),"cli"))
        reply = result["messages"][-1].text
        print(reply)
    
