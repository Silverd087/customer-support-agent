from src.config import settings


class TestIngestion:
    def test_rejects_non_md_file(self,test_client):
        headers = {"X-API-Key": settings.ingestion_api_key}
        file = {"file": ("test.txt", b"test file", "text/plain")}        
        response = test_client.post("/api/documents/ingestion",headers=headers,files=file)
        assert response.status_code == 400
        assert response.json()["detail"] == "Bad file extension"

    def test_rejects_empty_file(self,test_client):
        headers = {"X-API-Key": settings.ingestion_api_key}
        file = {"file": ("test.md", b"", "text/plain")}        
        response = test_client.post("/api/documents/ingestion",headers=headers,files=file)
        assert response.status_code == 400
        assert response.json()["detail"] == "Cannot upload empty file"

    def test_rejects_missing_api_key(self,test_client):
        file = {"file": ("test.md", b"test file", "text/plain")}        
        response = test_client.post("/api/documents/ingestion",files=file)
        assert response.status_code == 401

    def test_enqueues_task_and_returns_task_id(self,mocker,test_client):
        headers = {"X-API-Key": settings.ingestion_api_key}
        file = {"file": ("test.md", b"test file", "text/plain")}

        mock_task = mocker.Mock()
        mock_task.id = "task123"

        mock_delay = mocker.patch("api.ingestion.ingest_documents.delay")
        mock_delay.return_value = mock_task

        response = test_client.post("/api/documents/ingestion",headers=headers,files=file)
        data = response.json()
        assert response.status_code == 200
        assert "task_id" in data
        assert data["task_id"] == "task123"