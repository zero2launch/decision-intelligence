import pymongo.errors
import pytest
from unittest.mock import MagicMock

from src.schemas.upload import UploadRequest, UploadedFile
from src.services.upload import UploadService
from src.utils.exception import AppException


@pytest.fixture()
def service():
    svc = UploadService.__new__(UploadService)
    svc._repo = MagicMock()
    return svc


def _make_request(filename: str, content_b64: str, size: int = 0) -> UploadRequest:
    return UploadRequest(files=[UploadedFile(filename=filename, content=content_b64, size=size)])


def test_upload_pdf_success(service, minimal_pdf_b64):
    service._repo.insert_document.return_value = "fake_id"
    result = service.process_upload(_make_request("report.pdf", minimal_pdf_b64, 1000), "alice")
    assert result.success is True
    assert result.uploaded == 1
    service._repo.insert_document.assert_called_once()


def test_upload_csv_success(service, minimal_csv_b64):
    service._repo.insert_document.return_value = "fake_id"
    result = service.process_upload(_make_request("data.csv", minimal_csv_b64, 15), "alice")
    assert result.success is True
    assert result.uploaded == 1
    service._repo.insert_document.assert_called_once()


def test_upload_xlsx_success(service, minimal_xlsx_b64):
    service._repo.insert_document.return_value = "fake_id"
    result = service.process_upload(_make_request("data.xlsx", minimal_xlsx_b64, 500), "alice")
    assert result.success is True
    assert result.uploaded == 1
    service._repo.insert_document.assert_called_once()


def test_upload_xls_success(service, minimal_xls_b64):
    service._repo.insert_document.return_value = "fake_id"
    result = service.process_upload(_make_request("data.xls", minimal_xls_b64, 500), "alice")
    assert result.success is True
    assert result.uploaded == 1
    service._repo.insert_document.assert_called_once()


def test_upload_multiple_files_success(service, minimal_pdf_b64, minimal_csv_b64):
    service._repo.insert_document.return_value = "fake_id"
    payload = UploadRequest(files=[
        UploadedFile(filename="report.pdf", content=minimal_pdf_b64, size=1000),
        UploadedFile(filename="data.csv", content=minimal_csv_b64, size=15),
    ])
    result = service.process_upload(payload, "alice")
    assert result.success is True
    assert result.uploaded == 2
    assert service._repo.insert_document.call_count == 2


def test_unsupported_file_type(service, minimal_csv_b64):
    with pytest.raises(AppException) as exc_info:
        service.process_upload(_make_request("doc.txt", minimal_csv_b64), "alice")
    assert exc_info.value.status_code == 400
    assert "Unsupported file type" in exc_info.value.message
    assert "doc.txt" in exc_info.value.message


def test_malformed_base64(service):
    with pytest.raises(AppException) as exc_info:
        service.process_upload(_make_request("data.csv", "not-valid-base64!!!"), "alice")
    assert exc_info.value.status_code == 400
    assert "Invalid Base64 content" in exc_info.value.message


def test_db_error_on_insert(service, minimal_csv_b64):
    service._repo.insert_document.side_effect = pymongo.errors.PyMongoError("connection failed")
    with pytest.raises(AppException) as exc_info:
        service.process_upload(_make_request("data.csv", minimal_csv_b64), "alice")
    assert exc_info.value.status_code == 500
    assert exc_info.value.message == "Internal server error"
