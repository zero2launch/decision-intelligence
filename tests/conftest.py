import base64
import io

import pytest


@pytest.fixture
def minimal_pdf_b64():
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello PDF")
    pdf_bytes = doc.tobytes()
    return base64.b64encode(pdf_bytes).decode()


@pytest.fixture
def minimal_csv_b64():
    content = b"col1,col2\na,b\n"
    return base64.b64encode(content).decode()


@pytest.fixture
def minimal_xlsx_b64():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["col1", "col2"])
    ws.append(["a", "b"])
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def minimal_xls_b64():
    import xlwt
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    ws.write(0, 0, "col1")
    ws.write(0, 1, "col2")
    ws.write(1, 0, "a")
    ws.write(1, 1, "b")
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()
