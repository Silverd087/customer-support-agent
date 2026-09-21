
from fastapi import FastAPI

from adapters import whatsapp
from api import ingestion

app = FastAPI()
app.include_router(router=whatsapp.router,prefix="/api")
app.include_router(router=ingestion.router,prefix="/api")
@app.get("/healthz")
def health():
    return {
        "status": "healthy"
    }
def main():
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
    print("Hello from customer-support-agent!")

if __name__ == "__main__":
    main()
