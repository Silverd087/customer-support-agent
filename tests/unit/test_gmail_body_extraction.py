import base64

from adapters.utils import extract_email_body


class TestExtractEmail:
    def test_extract_body_plain_text(self):
        body = "random text"
        encoded_body = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8")
        payload = {
            "mimeType":"text/plain",
            "body": {
                "data":encoded_body
            }
        }
        print(payload.get("body",{}))
        assert extract_email_body(payload) == body

    def test_extract_body_recurses_multipart_to_find_plain_text(self):
        body = "random text"
        encoded_body = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8")
        payload = {
            "mimeType": "multipart/alternative",
            "body": {
                "size": 0
            },
            "parts": [
                {
                    "partId": "0",
                    "mimeType": "text/plain",
                    "filename": "",
                    "headers": [],
                    "body": {
                        "size": len(body),
                        "data": encoded_body
                    }
                },
                {
                    "partId": "1",
                    "mimeType": "text/html",
                    "filename": "",
                    "headers": [],
                    "body": {
                        "size": len(f"<p>{body}</p>"),
                        "data": base64.urlsafe_b64encode(f"<p>{body}</p>".encode()).decode("utf-8")
                    }
                }
            ]
        }
        assert extract_email_body(payload) == body

    def test_extract_body_falls_back_to_html_when_no_plain_text(self):
        body = "random html content"
        html = f"<html><body><p>{body}</p></body></html>"
        encoded_body = base64.urlsafe_b64encode(html.encode("utf-8")).decode("utf-8")
        payload = {
            "mimeType":"text/html",
            "body": {
                "data":encoded_body
            }
        }
        print(payload.get("body",{}))
        assert extract_email_body(payload) == body

    def test_extract_body_returns_none_when_nothing_found(self):
        body = ""
        encoded_body = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8")
        payload = {
            "mimeType":"text/plain",
            "body": {
                "data":encoded_body
            }
        }
        print(payload.get("body",{}))
        assert extract_email_body(payload) is None