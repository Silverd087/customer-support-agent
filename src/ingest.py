from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field, SecretStr

from src.celery_main import app
from src.config import settings
from src.rag_config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CLAUDE_CATEGORIZATION_MODEL,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
)

llm = ChatAnthropic(api_key=SecretStr(settings.anthropic_api_key),model=CLAUDE_CATEGORIZATION_MODEL)
prompt = ChatPromptTemplate.from_messages([
    ("system", "Analyze the text snippet and classify it into one of these exact categories: technical, billing, account, other."),
    ("user", "Text: {text}")
])
class ChunkCategory(BaseModel):
    category: Literal["technical","billing","account","other"] = Field(
        description="Categorize the content into technical, billing, account, or other."
    )


embedding_model = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL,
    encode_kwargs={"normalize_embeddings": True}
)


@app.task
def ingest_documents(content:str,filename):
    doc = Document(page_content=content, metadata={"source": filename})    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size = CHUNK_SIZE,
        chunk_overlap = CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(documents=[doc])
    structured_llm = llm.with_structured_output(ChunkCategory)
    category_chain = prompt | structured_llm
    for chunk in chunks:
        result = category_chain.invoke({"text":chunk.page_content})
        if isinstance(result,ChunkCategory):
            chunk.metadata["category"] = result.category

    Chroma.from_documents(
        documents=chunks,
        embedding=embedding_model,
        collection_name=COLLECTION_NAME,
        persist_directory="./chroma_langchain_db")
