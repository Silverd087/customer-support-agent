from fastapi import FastAPI
from whatsapp_adapter import router

app = FastAPI()
app.include_router(router=router,prefix="/api")

def main():
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
    print("Hello from customer-support-agent!")

if __name__ == "__main__":
    main()
