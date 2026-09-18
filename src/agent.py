import asyncio
from uuid import uuid4

from orchestrator import handle_incoming

thread_id = uuid4()
async def main():
    while True:
        message = input("\nwhat is your question? ")
        if message.lower() in ["exit","q"]:
            break
        result = await handle_incoming(message,str(thread_id),"cli")
        print(result)

if __name__ == "__main__":
    asyncio.run(main())
    
