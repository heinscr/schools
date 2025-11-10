"""
Contract PDF Ingestion Module
Extracts text and tables from teacher contract PDFs
"""
import io
import logging
from typing import Dict, List, Optional
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

logger = logging.getLogger(__name__)


class ContractIngestion:
    """
    Extract text and metadata from teacher contract PDFs
    """

    def __init__(self):
        if pdfplumber is None:
            raise ImportError(
                "pdfplumber is required. Install with: pip install pdfplumber"
            )

    def extract_from_file(self, file_path: str) -> Dict:
        """
        Extract text content and metadata from PDF file

        Args:
            file_path: Path to PDF file

        Returns:
            Dictionary with extracted data:
            {
                'filename': str,
                'district_name': str,
                'total_pages': int,
                'pages': List[Dict]
            }
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        logger.info(f"Processing PDF: {file_path}")

        with pdfplumber.open(file_path) as pdf:
            pages = []

            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text
                text = page.extract_text() or ""

                # Extract tables
                tables = page.extract_tables()

                pages.append({
                    'page_number': page_num,
                    'text': text,
                    'tables': tables or [],
                    'width': page.width,
                    'height': page.height
                })

                logger.debug(
                    f"Page {page_num}: {len(text)} chars, {len(tables or [])} tables"
                )

            # Extract district from filename
            district_name = self._extract_district_name(file_path.name)

            result = {
                'filename': file_path.name,
                'district_name': district_name,
                'total_pages': len(pages),
                'pages': pages
            }

            logger.info(
                f"Extracted {len(pages)} pages from {district_name}"
            )

            return result

    def extract_from_bytes(self, pdf_bytes: bytes, filename: str) -> Dict:
        """
        Extract text content and metadata from PDF bytes
        Useful for S3 or uploaded files

        Args:
            pdf_bytes: PDF file content as bytes
            filename: Original filename for district extraction

        Returns:
            Dictionary with extracted data
        """
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []

            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                tables = page.extract_tables()

                pages.append({
                    'page_number': page_num,
                    'text': text,
                    'tables': tables or [],
                    'width': page.width,
                    'height': page.height
                })

            district_name = self._extract_district_name(filename)

            return {
                'filename': filename,
                'district_name': district_name,
                'total_pages': len(pages),
                'pages': pages
            }

    def _extract_district_name(self, filename: str) -> str:
        """
        Extract district name from filename

        Examples:
            "Bedford_contract_1_conf85.pdf" → "Bedford"
            "Agawam_contract_2_conf85.pdf" → "Agawam"
            "Arlington_contract_1_conf85.pdf" → "Arlington"
        """
        # Remove .pdf extension
        name = filename.replace('.pdf', '').replace('.PDF', '')

        # Split on underscore and take first part
        parts = name.split('_')

        # Capitalize properly
        district = parts[0].title()

        return district
