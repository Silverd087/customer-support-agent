from fastapi import APIRouter, HTTPException, UploadFile, status

from ingest import ingest_documents

router = APIRouter()

@router.post("/documents/ingestion")
async def ingest(file:UploadFile):
    if file.filename and not file.filename.endswith(".md"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Bad file extension")
    if file.size is not None and file.size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Cannot upload empty file")

    content = (await file.read()).decode("utf-8")
    filename = file.filename
    task = ingest_documents.delay(content,filename)

    return {"task_id":task.id}
