from langchain_classic.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_anthropic import ChatAnthropic
from config import settings
from pydantic import BaseModel, Field
from typing import Literal
from langchain_core.prompts import ChatPromptTemplate

llm = ChatAnthropic(api_key=settings.anthropic_api_key,model="claude-haiku-4-5-20251001")
prompt = ChatPromptTemplate.from_messages([
    ("system", "Analyze the text snippet and classify it into one of these exact categories: technical, billing, account, other."),
    ("user", "Text: {text}")
])
class ChunkCategory(BaseModel):
    category: Literal["technical","billing","account","other"] = Field(
        description="Categorize the content into technical, billing, account, or other."
    )


embedding_model = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    encode_kwargs={"normalize_embeddings": True}
)
loader = DirectoryLoader(
    path="knowledge_base",
    glob="**/*.md",
    loader_cls=TextLoader
)

documents = loader.load()
splitter = RecursiveCharacterTextSplitter(
    chunk_size = 1000,
    chunk_overlap = 200
)
chunks = splitter.split_documents(documents=documents)
structured_llm = llm.with_structured_output(ChunkCategory)
category_chain = prompt | structured_llm
for chunk in chunks:
    result = category_chain.invoke({"text":chunk.page_content})
    chunk.metadata["category"] = result.category

vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embedding_model,
    collection_name="organization_policies",
    persist_directory="./chroma_langchain_db")
