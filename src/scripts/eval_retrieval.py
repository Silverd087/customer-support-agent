import os

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from rich.console import Console
from rich.table import Table

from src.rag_config import COLLECTION_NAME, EMBEDDING_MODEL, RETRIEVAL_K

EVAL_CASES = [
    {
        "question": "What Wi-Fi frequency do Lumen devices need?",
        "expected_sources": {"faq.md", "troubleshooting_guide.md"},
    },
    {
        "question": "How long is the return window, and does the item need original packaging?",
        "expected_sources": {"shipping_and_returns.md"},
    },
    {
        "question": "If I cancel Lumen+, when do I stop being charged, and what happens to my recordings?",
        "expected_sources": {"billing_and_subscriptions.md", "faq.md"},
    },
    {
        "question": "My thermostat's temperature reading looks wrong — what should I check first?",
        "expected_sources": {"troubleshooting_guide.md"},
    },
    {
        "question": "How does 2-factor authentication recovery work if I lose my phone?",
        "expected_sources": {"account_and_security.md"},
    },
    {
        "question": "Can I get a partial refund for the unused part of a billing cycle if I cancel mid-month?",
        "expected_sources": {"billing_and_subscriptions.md"},
    },
    {
        "question": "Is water damage covered under warranty?",
        "expected_sources": {"troubleshooting_guide.md", "shipping_and_returns.md"},
    },
]

embedding_model = HuggingFaceEmbeddings(
    model_name=EMBEDDING_MODEL,
    encode_kwargs={"normalize_embeddings": True}
)
vectorstore = Chroma(
    collection_name=COLLECTION_NAME,
    persist_directory="./chroma_langchain_db",
    embedding_function=embedding_model)

def eval():
    console = Console()
    table = Table(title="RAG Retrieval Evaluation", show_lines=True)

    table.add_column("#", justify="center", width=3)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Question", width=42)
    table.add_column("Retrieved", width=30)
    table.add_column("Expected", width=30)

    success = 0
    for i, case in enumerate(EVAL_CASES, start=1):
        results = vectorstore.similarity_search_with_score(
            case["question"], k=RETRIEVAL_K
        )
        sources = {os.path.basename(doc.metadata["source"]) for doc, _ in results}
        expected = set(case["expected_sources"])
        passed = bool(expected & set(sources))

        if passed:
            success += 1

        status_text = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"

        retrieved_cell = "\n".join(f"• {s}" for s in sources)
        expected_cell = "\n".join(f"• {s}" for s in expected)

        table.add_row(
            str(i), status_text, case["question"], retrieved_cell, expected_cell
        )

    console.print(table)
    console.print(
        f"\n[bold]Final Score:[/bold] {success}/{len(EVAL_CASES)} passed ({(success/len(EVAL_CASES)):.0%})\n"
    )


if __name__ == "__main__":
    eval()