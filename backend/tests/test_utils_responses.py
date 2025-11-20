"""
Tests for HTTP response utilities
"""
import sys
from pathlib import Path
import json
from decimal import Decimal

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.responses import create_response


class TestCreateResponse:
    """Tests for create_response function"""

    def test_create_response_basic(self):
        """Test creating a basic response"""
        response = create_response(200, {"message": "success"})

        assert response["statusCode"] == 200
        assert "headers" in response
        assert "body" in response

        body = json.loads(response["body"])
        assert body["message"] == "success"

    def test_create_response_headers(self):
        """Test default headers are included"""
        response = create_response(200, {})

        headers = response["headers"]
        assert headers["Content-Type"] == "application/json"
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert headers["Access-Control-Allow-Methods"] == "GET, POST, PUT, DELETE, OPTIONS"
        assert headers["Access-Control-Allow-Headers"] == "Content-Type"

    def test_create_response_additional_headers(self):
        """Test adding additional headers"""
        additional = {
            "X-Custom-Header": "custom-value",
            "Cache-Control": "no-cache"
        }

        response = create_response(200, {}, additional_headers=additional)

        headers = response["headers"]
        assert headers["X-Custom-Header"] == "custom-value"
        assert headers["Cache-Control"] == "no-cache"
        # Default headers should still be present
        assert headers["Content-Type"] == "application/json"

    def test_create_response_override_default_header(self):
        """Test overriding a default header"""
        response = create_response(
            200,
            {},
            additional_headers={"Content-Type": "text/plain"}
        )

        headers = response["headers"]
        assert headers["Content-Type"] == "text/plain"

    def test_create_response_status_codes(self):
        """Test different status codes"""
        response_200 = create_response(200, {"status": "ok"})
        assert response_200["statusCode"] == 200

        response_201 = create_response(201, {"status": "created"})
        assert response_201["statusCode"] == 201

        response_400 = create_response(400, {"error": "bad request"})
        assert response_400["statusCode"] == 400

        response_404 = create_response(404, {"error": "not found"})
        assert response_404["statusCode"] == 404

        response_500 = create_response(500, {"error": "server error"})
        assert response_500["statusCode"] == 500

    def test_create_response_with_list_body(self):
        """Test response with list as body"""
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        response = create_response(200, data)

        body = json.loads(response["body"])
        assert isinstance(body, list)
        assert len(body) == 3

    def test_create_response_with_decimal(self):
        """Test response with Decimal values (should be converted to float)"""
        data = {
            "price": Decimal("99.99"),
            "tax": Decimal("8.50")
        }

        response = create_response(200, data)

        body = json.loads(response["body"])
        assert body["price"] == 99.99
        assert body["tax"] == 8.50
        # Should be floats, not strings
        assert isinstance(body["price"], float)

    def test_create_response_nested_decimal(self):
        """Test response with nested Decimal values"""
        data = {
            "items": [
                {"price": Decimal("10.50")},
                {"price": Decimal("20.99")}
            ],
            "total": Decimal("31.49")
        }

        response = create_response(200, data)

        body = json.loads(response["body"])
        assert body["items"][0]["price"] == 10.50
        assert body["items"][1]["price"] == 20.99
        assert body["total"] == 31.49

    def test_create_response_empty_body(self):
        """Test response with empty body"""
        response = create_response(204, {})

        assert response["statusCode"] == 204
        body = json.loads(response["body"])
        assert body == {}

    def test_create_response_complex_body(self):
        """Test response with complex nested structure"""
        data = {
            "meta": {
                "total": 100,
                "page": 1
            },
            "data": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"}
            ]
        }

        response = create_response(200, data)

        body = json.loads(response["body"])
        assert body["meta"]["total"] == 100
        assert len(body["data"]) == 2
