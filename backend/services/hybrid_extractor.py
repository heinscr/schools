"""
Hybrid PDF Contract Extraction with S3 Integration
Extraction order:
1. pdfplumber (fast, works for most PDFs)
2. PyMuPDF (better text extraction, handles column-oriented layouts)
3. AWS Textract (for image-based/scanned PDFs)
"""
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from decimal import Decimal, InvalidOperation

import boto3
import pdfplumber

fitz = None  # type: ignore
pdfium = None  # type: ignore

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF not installed - fallback to PyMuPDF disabled")

try:
    import pypdfium2 as pdfium  # type: ignore
    PYPDFIUM_AVAILABLE = True
except ImportError:
    PYPDFIUM_AVAILABLE = False
    logging.warning("pypdfium2 not installed - PDFium path disabled")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


ROMAN_NUMERAL_VALUES = {
    'I': 1,
    'V': 5,
    'X': 10,
    'L': 50,
    'C': 100,
    'D': 500,
    'M': 1000,
}


def roman_to_int(value: str) -> Optional[int]:
    value = value.upper()
    total = 0
    prev = 0
    for ch in reversed(value):
        if ch not in ROMAN_NUMERAL_VALUES:
            return None
        current = ROMAN_NUMERAL_VALUES[ch]
        if current < prev:
            total -= current
        else:
            total += current
            prev = current
    return total if total > 0 else None


EDU_MAP_RAW: Dict[str, Tuple[str, int]] = {
    'BA': ('B', 0),
    'B': ('B', 0),
    'BA0': ('B', 0),
    'BA+0': ('B', 0),
    'BACHELOR': ('B', 0),
    'BA+10': ('B', 10),
    'B+10': ('B', 10),
    'BA+15': ('B', 15),
    'B+15': ('B', 15),
    '15': ('B', 15),
    'BA+20': ('B', 20),
    'B+20': ('B', 20),
    'BA+30': ('B', 30),
    'B+30': ('B', 30),
    'B30': ('B', 30),
    'B30/MA': ('M', 0),
    'BA+45': ('B', 45),
    'B+45': ('B', 45),
    'BA+60': ('B', 60),
    'MA': ('M', 0),
    'M': ('M', 0),
    'MA0': ('M', 0),
    'MA+0': ('M', 0),
    'MASTERS': ('M', 0),
    'MA+10': ('M', 10),
    'M+10': ('M', 10),
    'MA+15': ('M', 15),
    'M+15': ('M', 15),
    'MA+20': ('M', 20),
    'M+20': ('M', 20),
    'MA+30': ('M', 30),
    'M+30': ('M', 30),
    'MA+45': ('M', 45),
    'M+45': ('M', 45),
    'MA+45/CAGS': ('M', 45),
    'M+45/CAGS': ('M', 45),
    'MA+45CAGS': ('M', 45),
    'MA+40': ('M', 40),
    'M+40': ('M', 40),
    'MA+60': ('M', 60),
    'M+60': ('M', 60),
    'MA+60/CAGS': ('M', 60),
    'M+60/CAGS': ('M', 60),
    'MA+60CAGS': ('M', 60),
    'CAGS': ('M', 60),
    'CAGS/DOC': ('D', 0),
    'CAGS DOC': ('D', 0),
    'DOC': ('D', 0),
    'DOCTORATE': ('D', 0),
    'PHD': ('D', 0),
    'EDD': ('D', 0),
    'PROV': ('D', 0),
    'AS': ('B', 0),
    'LANE1': ('B', 0),
    'LANE2': ('B', 15),
    'LANE3': ('B', 30),
    'LANE4': ('M', 0),
    'LANE5': ('M', 15),
    'LANE6': ('M', 30),
    'LANE7': ('M', 45),
    'LANE8': ('M', 60),
    'PAYSCALE1': ('B', 0),
    'PAYSCALE2': ('B', 15),
    'PAYSCALE3': ('B', 30),
    'PAYSCALE4': ('M', 0),
    'PAYSCALE5': ('M', 15),
    'PAYSCALE6': ('M', 30),
    # Roman numeral variants (for tables using I, II, III, IV notation)
    'I': ('B', 0),
    'II': ('B', 15),
    'III': ('B', 30),
    'IV': ('M', 0),
    'V': ('M', 15),
    'VI': ('M', 30),
    'VII': ('M', 45),
    'VIII': ('M', 60),
    '(I)': ('B', 0),
    '(II)': ('B', 15),
    '(III)': ('B', 30),
    '(IV)': ('M', 0),
    '(V)': ('M', 15),
    '(VI)': ('M', 30),
    '(VII)': ('M', 45),
    '(VIII)': ('M', 60),
}


def normalize_lane_key(text: Any) -> str:
    """
    Normalize lane/education column keys to standard format.
    Enhanced to handle Roman numerals and parentheses (e.g., "B.A. (I)", "MA + (15) II").
    """
    if text is None:
        return 'NONE'

    raw = str(text).upper().strip()

    # Normalize common variations
    raw = raw.replace('B.A.', 'BA').replace('M.A.', 'MA')
    replacements = {
        'BACHELOR': 'BA',
        'BACCALAUREATE': 'BA',
        'MASTER': 'MA',
        'MASTERS': 'MA',
        'MASTEROFARTS': 'MA',
        'DOCTORATE': 'DOC',
        'DOCTORAL': 'DOC',
        'DOCTOROFEDUCATION': 'DOC',
    }
    for needle, repl in replacements.items():
        raw = raw.replace(needle, repl)

    # Handle parenthetical Roman numerals: "BA (I)" or "MA+15 (II)"
    paren_match = re.search(r'\(([IVX]+)\)', raw)
    if paren_match:
        roman_num = paren_match.group(1)
        # Check if this is a standalone Roman numeral with minimal other content
        cleaned = re.sub(r'\([IVX]+\)', '', raw).strip()
        cleaned = re.sub(r'[^A-Z0-9+]', '', cleaned)
        if not cleaned or cleaned in ['BA', 'MA', 'B', 'M']:
            # Use Roman numeral for mapping
            return f'({roman_num})'

    # Handle "BA + (10)" -> "BA+10"
    raw = re.sub(r'\+\s*\((\d+)\)', r'+\1', raw)

    # Normalize dashes/colons to plus
    raw = raw.replace('–', '+').replace('—', '+').replace('-', '+').replace(':', '+')

    # Normalize plus signs
    raw = re.sub(r'\s*\+\s*', '+', raw)

    # Normalize BA15 to BA+15, M30 to M+30
    raw = re.sub(r'\b(BA|MA|B|M)(\d{1,2})\b', r'\1+\2', raw)
    raw = re.sub(r'\+L(\d)', r'+1\1', raw)  # Handle "+L5" -> "+15"
    raw = re.sub(r'\+I(\d)', r'+1\1', raw)  # Handle "+I5" -> "+15"

    # Try tokenizing to extract education label
    tokens = tokenize_lane_labels(raw)
    if tokens:
        return tokens[0]

    # Clean up for mapping
    simplified = re.sub(r'[^A-Z0-9+()]', '', raw)

    # Handle explicit lane references
    lane_match = re.match(r'LANE(\d+)', simplified)
    if lane_match:
        return f"LANE{lane_match.group(1)}"

    pay_scale_match = re.match(r'PAYSCALE(\d+)', simplified)
    if pay_scale_match:
        return f"PAYSCALE{pay_scale_match.group(1)}"

    level_match = re.match(r'LEVEL(\d+)', simplified)
    if level_match:
        return f"LEVEL{level_match.group(1)}"

    # Check for standalone Roman numerals with optional parentheses
    roman_pattern = r'\(?([IVX]+)\)?'
    roman_match = re.fullmatch(roman_pattern, simplified)
    if roman_match:
        return simplified  # Keep parentheses if present

    return simplified if simplified else 'NONE'


def tokenize_lane_labels(text: str) -> List[str]:
    """
    Tokenize lane labels from text.
    Enhanced to handle Roman numerals and parenthetical notation.
    """
    if not text:
        return []

    normalized = text.upper().strip()

    # Normalize common patterns
    normalized = normalized.replace('B.A.', 'BA').replace('M.A.', 'MA')
    normalized = normalized.replace('BACCALAUREATE', 'BA').replace('BACHELOR', 'BA')
    normalized = normalized.replace('MASTERS', 'MA').replace('MASTER', 'MA')

    # Handle "BA + (10)" -> "BA+10"
    normalized = re.sub(r'\+\s*\((\d+)\)', r'+\1', normalized)

    # Normalize separators
    normalized = normalized.replace('-', '+').replace('/', ' ')

    # Remove other punctuation except +, spaces, and parentheses (for Roman numerals)
    normalized = re.sub(r'[^A-Z0-9+ ()]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    # Normalize BA15 to BA+15
    normalized = re.sub(r'\b(BA|MA|B|M)(\d{1,2})\b', r'\1+\2', normalized)

    # Enhanced pattern to match education tokens including Roman numerals
    token_pattern = re.compile(
        r'(?:BA|MA|B|M)(?:\+\d+)?|'  # BA, MA, B+15, M+30, etc.
        r'CAGS|DOC|DR|EDD|PHD|'  # Doctorate variants
        r'\([IVX]+\)|'  # Parenthetical Roman numerals like (I), (II)
        r'[IVX]+',  # Standalone Roman numerals
        re.I
    )

    tokens = token_pattern.findall(normalized)
    return [token.upper().strip() for token in tokens if token.strip()]


def extract_lane_labels(lines: List[str], header_idx: int, expected_pairs: int) -> List[str]:
    labels: List[str] = []
    if header_idx <= 0 or expected_pairs <= 0:
        return labels
    start = max(0, header_idx - 12)
    for line in lines[start:header_idx]:
        candidate = line.strip()
        if not candidate:
            continue
        label_tokens = tokenize_lane_labels(candidate)
        labels.extend(label_tokens)

    deduped: List[str] = []
    seen: set[str] = set()
    for label in labels:
        if label not in seen:
            seen.add(label)
            deduped.append(label)

    return deduped[-expected_pairs:] if expected_pairs else deduped


EDU_MAP: Dict[str, Tuple[str, int]] = {
    normalize_lane_key(key): value for key, value in EDU_MAP_RAW.items()
}


def collapse_multiplier_salary_columns(
    table: Optional[Sequence[Sequence[Any]]],
    lane_labels: Optional[List[str]] = None,
) -> Optional[List[List[str]]]:
    if not table:
        return None

    table_list = [list(row) for row in table]
    header = table_list[0]
    if not header or len(header) < 3:
        return table_list

    normalized = [normalize_lane_key(cell) for cell in header]
    pattern = normalized[1:]
    if not pattern or len(pattern) % 2 != 0:
        return table_list

    for idx, cell in enumerate(pattern):
        expected = 'MULTIPLIER' if idx % 2 == 0 else 'SALARY'
        if cell != expected:
            return table_list

    pair_count = len(pattern) // 2
    labels: List[str] = []
    if lane_labels:
        labels = lane_labels[:pair_count]
    if len(labels) < pair_count:
        labels.extend([f'Lane {i + 1}' for i in range(len(labels), pair_count)])

    new_table: List[List[str]] = [['Step'] + labels]
    for row in table_list[1:]:
        if len(row) < 1 + pair_count * 2:
            continue
        new_row = [row[0]]
        for pair_idx in range(pair_count):
            salary_idx = 1 + pair_idx * 2 + 1
            salary_val = row[salary_idx] if salary_idx < len(row) else ''
            new_row.append(salary_val)
        new_table.append(new_row)

    return new_table if len(new_table) > 1 else None


def normalize_table_data(table: Optional[Sequence[Sequence[Any]]]) -> List[List[str]]:
    normalized: List[List[str]] = []
    if not table:
        return normalized

    for row in table:
        if row is None:
            continue
        normalized.append([
            str(cell).strip() if cell is not None else ''
            for cell in row
        ])
    return normalized


def split_table_on_step_columns(table: List[List[str]]) -> List[List[List[str]]]:
    if not table or not table[0]:
        return []

    header = table[0]
    step_indices = [idx for idx, cell in enumerate(header)
                    if str(cell).strip().upper() == 'STEP']

    if not step_indices or (len(step_indices) == 1 and step_indices[0] == 0):
        return [table]

    sub_tables: List[List[List[str]]] = []
    for pos, start in enumerate(step_indices):
        end = step_indices[pos + 1] if pos + 1 < len(step_indices) else len(header)
        slice_cols = list(range(start, end))
        new_table: List[List[str]] = []
        for row in table:
            new_row = []
            for col in slice_cols:
                if col < len(row):
                    new_row.append(row[col])
                else:
                    new_row.append('')
            new_table.append(new_row)
        if new_table and str(new_table[0][0]).strip().upper() == 'STEP':
            sub_tables.append(new_table)

    return sub_tables or [table]


def split_row_tokens(line: str) -> List[str]:
    if not line:
        return []
    normalized = line.replace('\t', '    ')
    tokens = [tok.strip() for tok in re.split(r'\s{2,}', normalized) if tok.strip()]
    if len(tokens) > 1:
        return tokens
    return [tok.strip() for tok in normalized.split() if tok.strip()]


STEP_HEADER_NORMALIZED = {
    'STEP', 'STEPS', 'ACADEMIC', 'ACADEMICS', 'ACADEMICTRACK', 'ACADEMICTRAINING',
    'EXPERIENCE', 'YEARS', 'YEAR', 'LEVEL', 'LEVELS', 'CLASS', 'CLASSES',
    'CVTE', 'VOC', 'VOCATIONAL', 'TECH', 'TECHNICAL'
}

LANE_HEADER_TOKEN_PATTERN = re.compile(r'^(?=.*[A-Z])[A-Z0-9+/.-]+$', re.I)


def looks_like_step_header(text: str) -> bool:
    if not text:
        return False
    normalized = text.strip().upper()
    if not normalized:
        return False
    if normalized.startswith('STEP'):
        return True
    simplified = re.sub(r'[^A-Z]', '', normalized)
    return simplified in STEP_HEADER_NORMALIZED


STEP_MARKER_PATTERN = re.compile(r'^\d{1,2}(?:[-/]\d{1,2})?$')


def is_column_step_marker(text: str) -> bool:
    if not text:
        return False
    token = text.strip().replace('–', '-').replace('—', '-')
    return bool(STEP_MARKER_PATTERN.match(token))


def is_column_salary_value(text: str) -> bool:
    if not text:
        return False
    token = text.strip()
    token = token.replace('$', '').replace(',', '').replace(' ', '')
    token = token.replace('.', '')
    return token.isdigit()


def looks_like_lane_header_token(token: str) -> bool:
    if not token:
        return False
    normalized = token.strip()
    if not normalized:
        return False
    normalized = normalized.replace('–', '-').replace('—', '-')
    return bool(LANE_HEADER_TOKEN_PATTERN.match(normalized))


TRIGGER_PATTERN = re.compile(r'(SALARY|COMPENSATION|TEACHERS?|SCHEDULE|STEP)', re.I)


def text_has_salary_signal(text: str) -> bool:
    if not text:
        return False
    if TRIGGER_PATTERN.search(text):
        return True
    upper = text.upper()
    return any(token in upper for token in STEP_HEADER_NORMALIZED)


def collect_lane_aliases(text: str) -> Dict[str, str]:
    alias_map: Dict[str, str] = {}
    if not text:
        return alias_map

    lines = [line.strip() for line in text.split('\n') if line.strip()]

    def register_alias(alias: str, descriptor: str) -> None:
        alias_key = normalize_lane_key(alias)
        if alias_key == 'NONE':
            return
        tokens = tokenize_lane_labels(descriptor) or [descriptor]
        for token in tokens:
            target_key = normalize_lane_key(token)
            if target_key in EDU_MAP:
                alias_map.setdefault(alias_key, target_key)
                break

    simple_pattern = re.compile(r'^(?P<alias>[A-Z]{1,4}(?:\+\d+)?)\s*(?:=|:|-|–|—)\s*(?P<desc>.+)$')
    lane_pattern = re.compile(r'^(?P<label>(?:Lane|Pay\s*Scale|Level)\s*[A-Z0-9]+)\s*(?:=|:|-|–|—)\s*(?P<desc>.+)$', re.I)

    for line in lines:
        match = lane_pattern.match(line)
        if match:
            register_alias(match.group('label'), match.group('desc'))
            continue
        match = simple_pattern.match(line)
        if match:
            register_alias(match.group('alias'), match.group('desc'))

    token_lines = [split_row_tokens(line) for line in lines]
    for tokens in token_lines:
        if not tokens:
            continue
        head = tokens[0].strip().upper()
        if head != 'STEP' or len(tokens) <= 2:
            continue
        sequence = []
        for token in tokens[1:]:
            key = normalize_lane_key(token)
            if key not in ('NONE', 'STEP') and key in EDU_MAP:
                sequence.append(key)
        if not sequence:
            continue
        for idx, canonical in enumerate(sequence, start=1):
            alias_map.setdefault(f'LANE{idx}', canonical)
            alias_map.setdefault(f'PAYSCALE{idx}', canonical)
            alias_map.setdefault(str(idx), canonical)

    return alias_map


def extract_step_value(tokens: List[str]) -> Tuple[Optional[str], List[str]]:
    for idx, token in enumerate(tokens):
        candidate = token.replace('–', '-').replace('—', '-')
        match = re.match(r'^(?:STEP)?\s*(\d{1,2})(?:[-/]\d+)?$', candidate, re.I)
        if match:
            step_value = match.group(1)
            remaining = tokens[:idx] + tokens[idx + 1:]
            return step_value, remaining
    return None, tokens


def parse_row_oriented_table(lines: List[str]) -> Optional[List[List[str]]]:
    for idx, line in enumerate(lines):
        tokens = split_row_tokens(line)
        if not tokens:
            continue
        step_idx = next((i for i, tok in enumerate(tokens) if tok.lower().startswith('step')), None)
        if step_idx is None:
            continue
        header_tokens = tokens[step_idx:]
        if len(header_tokens) < 3:
            continue

        header_tokens[0] = 'Step'
        expected_pairs = max(0, (len(header_tokens) - 1) // 2)
        lane_labels = extract_lane_labels(lines, idx, expected_pairs)
        header = header_tokens
        table: List[List[str]] = [header]
        expected_cols = len(header)

        for row_line in lines[idx + 1:]:
            if not row_line.strip():
                break
            row_tokens = split_row_tokens(row_line)
            if not row_tokens:
                break
            if any(tok.lower().startswith('step') for tok in row_tokens):
                break

            step_value, remaining_tokens = extract_step_value(row_tokens)
            if not step_value:
                break

            row = [step_value] + remaining_tokens
            row = row[:expected_cols]
            if len(row) < expected_cols:
                row += [''] * (expected_cols - len(row))
            table.append(row)

        if len(table) > 1:
            collapsed = collapse_multiplier_salary_columns(table, lane_labels)
            return collapsed or table
        return None

    return None


def _parse_column_oriented_table_block(
    lines: List[str],
    start_idx: int = 0
) -> Tuple[Optional[List[List[str]]], int]:
    line_count = len(lines)
    header_idx: Optional[int] = None
    for idx in range(start_idx, line_count):
        if looks_like_step_header(lines[idx]):
            header_idx = idx
            break

    if header_idx is None:
        return None, line_count

    logger.debug("Found 'Step' header at line %s", header_idx)

    header: List[str] = ['Step']
    i = header_idx + 1
    while i < line_count:
        edu = lines[i].strip()
        if not edu:
            i += 1
            continue

        tokens = split_row_tokens(edu)
        if not tokens:
            i += 1
            continue

        first_token = tokens[0]
        if is_column_step_marker(first_token):
            logger.debug("Line %s: '%s' looks like first step marker", i, first_token)
            break

        if len(tokens) == 1:
            token = tokens[0]
            if looks_like_lane_header_token(token):
                logger.debug("Line %s: '%s' is education level", i, token)
                header.append(token)
                i += 1
                continue
            if re.match(r'^\d{1,2}$', token) and not re.search(r'[A-Z]', token, re.I):
                logger.debug("Line %s: '%s' could be education level", i, token)
                header.append(token)
                i += 1
                continue

        if len(tokens) > 1 and all(looks_like_lane_header_token(tok) for tok in tokens):
            logger.debug(
                "Line %s: parsed %s lane header token(s) from '%s'",
                i,
                len(tokens),
                edu,
            )
            header.extend(tokens)
            i += 1
            continue

        logger.debug("Line %s: '%s' - stopping header collection", i, edu)
        break

    if len(header) < 2:
        logger.debug("ERROR: Only found %s columns", len(header))
        return None, line_count

    num_cols = len(header)
    logger.debug("Detected column-oriented table with %s columns: %s", num_cols, header)

    table_data: List[List[str]] = [header]
    token_stream: List[Tuple[str, int]] = []
    for line_idx in range(i, line_count):
        tokens = split_row_tokens(lines[line_idx])
        if not tokens:
            continue
        for tok in tokens:
            token_stream.append((tok, line_idx))

    current_row: List[str] = []
    data_rows = 0

    def finalize_row() -> None:
        nonlocal current_row
        nonlocal data_rows
        if not current_row or len(current_row) <= 1:
            return
        padded = current_row + [''] * (num_cols - len(current_row))
        table_data.append(padded[:num_cols])
        data_rows += 1
        current_row = []

    next_start_line = line_count
    idx = 0
    while idx < len(token_stream):
        token, token_line = token_stream[idx]
        token = token.strip()
        if not token:
            idx += 1
            continue

        if is_column_step_marker(token):
            finalize_row()
            current_row = [token]
            idx += 1
            continue

        if is_column_salary_value(token):
            if current_row:
                current_row.append(token)
                if len(current_row) == num_cols:
                    finalize_row()
            idx += 1
            continue

        if re.search(r'[A-Z]', token, re.I):
            if not current_row and data_rows == 0:
                # Skip leading textual tokens (e.g., 'Prov') before the first step row
                idx += 1
                continue

            logger.debug(
                "Encountered new section token '%s' at stream index %s; stopping table parse",
                token,
                idx,
            )
            restart_line = max(start_idx + 1, token_line)
            next_start_line = min(next_start_line, restart_line)
            break

        idx += 1

    finalize_row()

    if len(table_data) <= 1:
        return None, next_start_line

    expected_pairs = max(0, (len(table_data[0]) - 1) // 2)
    lane_labels = extract_lane_labels(lines, header_idx, expected_pairs)
    collapsed = collapse_multiplier_salary_columns(table_data, lane_labels)
    return (collapsed or table_data), next_start_line


def parse_column_oriented_tables_from_lines(lines: List[str]) -> List[List[List[str]]]:
    tables: List[List[List[str]]] = []
    start_idx = 0
    while start_idx < len(lines):
        table, next_idx = _parse_column_oriented_table_block(lines, start_idx)
        if table:
            tables.append(table)
        if next_idx <= start_idx:
            start_idx += 1
        else:
            start_idx = next_idx
        if not table and start_idx >= len(lines):
            break
    return tables


def parse_column_oriented_table_from_lines(lines: List[str]) -> Optional[List[List[str]]]:
    tables = parse_column_oriented_tables_from_lines(lines)
    return tables[0] if tables else None


class HybridContractExtractor:
    """
    Hybrid extraction: pdfplumber for text PDFs, AWS Textract for image PDFs
    """

    def __init__(self):
        """Initialize extractor with AWS clients"""
        self.s3 = boto3.client('s3')
        self.textract = boto3.client('textract')

    def is_text_based_pdf(self, pdf_bytes: bytes) -> bool:
        """
        Determine if PDF is text-based or image-based

        Args:
            pdf_bytes: PDF file content

        Returns:
            True if text-based, False if image-based
        """
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                # Check first few pages
                for page in pdf.pages[:3]:
                    text = page.extract_text() or ""
                    # If we find substantial text, it's text-based
                    if len(text.strip()) > 100:
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking PDF type: {e}")
            return False

    def extract_year_from_text(self, text: str) -> str:
        """
        Extract year from text using multiple strategies

        Returns school year in "YYYY-YYYY" format

        Examples:
            "2024-2025" → "2024-2025" (keep as is)
            "2023" → "2023-2024" (convert to range)
            "Effective July 1, 2027" → "2027-2028" (convert to range)
            "July 2024" → "2024-2025" (convert to range)
            "27" → "2027-2028" (expand and convert to range)
        """
        import re

        if not text:
            return "unknown"

        # Strategy 1: Look for YYYY-YYYY pattern (e.g., "2024-2025" or "July 1, 2024 - June 30, 2025")
        # Keep as is
        # Look for two 4-digit years with a dash/hyphen between them (may have text before/after)
        match = re.search(r'(20\d{2})\s*,?\s*[-–—]\s*.{0,15}?(20\d{2})', text)
        if match:
            year1 = match.group(1)
            year2 = match.group(2)
            # Only return if they're consecutive school years (year2 = year1 + 1)
            if int(year2) == int(year1) + 1:
                return f"{year1}-{year2}"

        # Strategy 2: Look for "Effective [Month] [Day,] YYYY" pattern
        # Matches: "Effective July 1, 2027" → "2027-2028"
        match = re.search(
            r'Effective\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})',
            text, re.IGNORECASE
        )
        if match:
            year = int(match.group(1))
            return f"{year}-{year + 1}"

        # Strategy 3: Look for month name followed by year
        # Matches: "July 2024" → "2024-2025"
        match = re.search(
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            text, re.IGNORECASE
        )
        if match:
            year = int(match.group(1))
            return f"{year}-{year + 1}"

        # Strategy 4: Look for "FY YYYY" or "FY YY" pattern
        # Matches: "FY26" → "2025-2026", "FY 2026" → "2025-2026"
        match = re.search(r'FY\s*(\d{2,4})', text, re.IGNORECASE)
        if match:
            year_str = match.group(1)
            if len(year_str) == 2:
                # FY26 -> 2025-2026
                year = 2000 + int(year_str)
                return f"{year - 1}-{year}"
            else:
                # FY 2022 -> 2021-2022
                year = int(year_str)
                return f"{year - 1}-{year}"

        # Strategy 5: Look for any standalone 4-digit year (2000-2099)
        # Matches: "2023" → "2023-2024"
        years = re.findall(r'\b(20\d{2})\b', text)
        if years:
            # Take the most recent year found
            year = int(max(years))
            return f"{year}-{year + 1}"

        # Strategy 6: Look for 2-digit year (e.g., "27" → "2027-2028")
        match = re.search(r'\b(\d{2})\b', text)
        if match:
            year_2digit = int(match.group(1))
            # Assume 20xx for years 00-99
            year = 2000 + year_2digit
            return f"{year}-{year + 1}"

        return "unknown"

    @staticmethod
    def is_valid_step_number(step: int) -> bool:
        """
        Check if a step number is valid (not garbage from bad text extraction).
        Valid step numbers are typically 0-35 (some districts go higher but rarely above 35).
        """
        return 0 <= step <= 35

    @staticmethod
    def deduplicate_records(records: List[Dict]) -> List[Dict]:
        """
        Deduplicate salary records based on their DynamoDB primary key.

        The primary key is: (district_id, school_year, period, education, credits, step)

        When duplicates are found (same table extracted via multiple methods),
        keeps the first occurrence.

        Args:
            records: List of salary records

        Returns:
            Deduplicated list of salary records
        """
        if not records:
            return records

        seen_keys = set()
        unique_records = []
        duplicates_removed = 0

        for record in records:
            # Create a key tuple matching DynamoDB primary key
            key = (
                record.get('district_id'),
                record.get('school_year'),
                record.get('period'),
                record.get('education'),
                record.get('credits'),
                record.get('step'),
            )

            if key not in seen_keys:
                seen_keys.add(key)
                unique_records.append(record)
            else:
                duplicates_removed += 1

        if duplicates_removed > 0:
            logger.debug(
                "Removed %d duplicate records (original: %d, unique: %d)",
                duplicates_removed,
                len(records),
                len(unique_records)
            )

        return unique_records

    def parse_salary_table(
        self,
        table: Sequence[Sequence[Any]],
        district: str,
        year: str,
        alias_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict]:
        """
        Parse salary table into structured records with alias-aware lane mapping.
        Enhanced with step number validation and better education column detection.
        """
        if not table:
            return []

        normalized_table = normalize_table_data(table)
        if not normalized_table:
            return []

        alias_map = alias_map or {}
        records: List[Dict] = []
        invalid_steps = 0

        for sub_table in split_table_on_step_columns(normalized_table):
            if len(sub_table) < 2:
                continue

            header_row_idx = 0
            for idx, row in enumerate(sub_table):
                if row and str(row[0]).strip().upper() == 'STEP':
                    header_row_idx = idx
                    break

            if header_row_idx > 0:
                logger.debug("Skipping %d non-header row(s) at top of table", header_row_idx)

            raw_header = sub_table[header_row_idx]
            normalized_header = [normalize_lane_key(h) for h in raw_header]

            edu_columns: List[Tuple[int, str, Tuple[str, int]]] = []
            for col_idx, (raw_cell, normalized_cell) in enumerate(zip(raw_header, normalized_header)):
                if col_idx == 0:
                    continue

                display_label = str(raw_cell).strip() or normalized_cell
                normalized_label = normalize_lane_key(display_label)

                if normalized_cell in EDU_MAP:
                    edu_columns.append((col_idx, display_label, EDU_MAP[normalized_cell]))
                    continue

                mapped_key = alias_map.get(normalized_label) or alias_map.get(normalized_cell)
                if mapped_key and mapped_key in EDU_MAP:
                    edu_columns.append((col_idx, display_label, EDU_MAP[mapped_key]))
                else:
                    # Skip warning for known metadata columns
                    if normalized_cell.upper() not in ['MULTIPLIER', 'SALARY', 'EMPTY', 'NONE', '']:
                        logger.warning(
                            "Unknown education level '%s' (normalized: '%s') in column %s",
                            display_label,
                            normalized_cell,
                            col_idx,
                        )

            if not edu_columns:
                logger.debug("No valid education columns found in table")
                continue

            logger.debug(
                "Mapped %d columns: %s",
                len(edu_columns),
                [(header, edu, cr) for _, header, (edu, cr) in edu_columns],
            )

            for row_idx, row in enumerate(sub_table[header_row_idx + 1:], header_row_idx + 2):
                if not row or len(row) < 2:
                    continue

                step_str = str(row[0]).strip()
                step_match = re.search(r'(\d+)', step_str)
                if not step_match:
                    continue
                step = int(step_match.group(1))

                # Validate step number to filter garbage from bad text extraction
                if not self.is_valid_step_number(step):
                    invalid_steps += 1
                    continue

                for col_idx, _, (education, credits) in edu_columns:
                    if col_idx >= len(row):
                        continue

                    salary_str = str(row[col_idx]).strip()
                    if not salary_str:
                        continue

                    salary_cleaned = re.sub(r'[$,\s]', '', salary_str).replace('.', '')
                    try:
                        salary = float(Decimal(salary_cleaned))
                    except (ValueError, InvalidOperation):
                        logger.debug(
                            "Could not parse salary '%s' at row %s, col %s",
                            salary_str,
                            row_idx,
                            col_idx,
                        )
                        continue

                    # Validate salary range
                    if not (20000 <= salary <= 200000):
                        logger.debug("Salary %s out of valid range at row %s, col %s", salary, row_idx, col_idx)
                        continue

                    records.append({
                        'district_id': district.lower().replace(' ', '-'),
                        'district_name': district,
                        'school_year': year,
                        'period': 'full-year',
                        'education': education,
                        'credits': credits,
                        'step': step,
                        'salary': salary,
                    })

            if invalid_steps > 0:
                logger.debug("Filtered out %d rows with invalid step numbers (> 35)", invalid_steps)

        return records

    def is_salary_table(self, table: Sequence[Sequence[Any]]) -> bool:
        """
        Check if a table looks like a salary table based on structure

        Returns True if table has:
        - A 'Step' column
        - At least one education level column (B, M, MA, etc.)
        """
        if not table or len(table) < 2:
            return False

        # Education patterns to look for
        edu_patterns = ['B', 'M', 'BA', 'MA', 'B+', 'M+', 'CAGS', 'DOC']

        # Check all rows for potential headers
        for row in table[:5]:  # Check first 5 rows
            if not row:
                continue
            normalized_row = [str(h).strip().upper().replace(' ', '') for h in row]

            # Check if this row has Step and education columns
            has_step = any('STEP' in col for col in normalized_row)
            has_education = any(
                any(edu in col for edu in edu_patterns)
                for col in normalized_row
            )

            if has_step and has_education:
                return True

        return False

    def extract_with_pdfplumber(self, pdf_bytes: bytes, filename: str, district_name: str) -> Optional[List[Dict]]:
        """
        Extract salary data using pdfplumber + regex

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records

        Returns:
            List of salary records or None if extraction fails
        """
        try:
            logger.info(f"Extracting with pdfplumber: {filename}")

            # Use provided district name
            district = district_name

            # Extract tables
            all_records = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    alias_map = collect_lane_aliases(text)
                    tables = page.extract_tables()

                    # Check if this is a salary table page (by keyword OR by table structure)
                    has_keyword = text_has_salary_signal(text)

                    if has_keyword:
                        year = self.extract_year_from_text(text)

                        for table in tables:
                            if table and len(table) > 1:
                                # Try to extract year from table itself (first row might have FY26, etc.)
                                table_year = year  # Default to page-level year
                                if table[0] and table[0][0]:
                                    first_cell = str(table[0][0]).strip()
                                    extracted = self.extract_year_from_text(first_cell)
                                    if extracted != "unknown":
                                        table_year = extracted

                                records = self.parse_salary_table(table, district, table_year, alias_map)
                                all_records.extend(records)
                                logger.debug(f"Page {page_num}: extracted {len(records)} records (keyword match)")
                    else:
                        # No keyword, but check if tables look like salary tables
                        year = self.extract_year_from_text(text)

                        for table in tables:
                            if table and len(table) > 1 and self.is_salary_table(table):
                                # Try to extract year from table itself (first row might have FY26, etc.)
                                table_year = year  # Default to page-level year
                                if table[0] and table[0][0]:
                                    first_cell = str(table[0][0]).strip()
                                    extracted = self.extract_year_from_text(first_cell)
                                    if extracted != "unknown":
                                        table_year = extracted

                                records = self.parse_salary_table(table, district, table_year, alias_map)
                                if records:  # Only extend if we got records
                                    all_records.extend(records)
                                    logger.debug(f"Page {page_num}: extracted {len(records)} records (structure match)")

            return all_records if all_records else None

        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            return None

    def extract_with_pypdfium(self, pdf_bytes: bytes, filename: str, district_name: str) -> Optional[List[Dict]]:
        """Extract salary data using pypdfium2 for robust text layout parsing."""
        if not PYPDFIUM_AVAILABLE or pdfium is None:  # type: ignore[truthy-bool]
            logger.warning("pypdfium2 not available, skipping PDFium extraction")
            return None

        try:
            logger.info(f"Extracting with pypdfium2: {filename}")

            district = district_name
            all_records: List[Dict] = []

            pdf = pdfium.PdfDocument(pdf_bytes)  # type: ignore[call-arg]
            for page_index in range(len(pdf)):
                page_num = page_index + 1
                page = pdf[page_index]
                textpage = page.get_textpage()
                text = textpage.get_text_range() or ''
                textpage.close()

                if not text_has_salary_signal(text):
                    continue

                year = self.extract_year_from_text(text)
                alias_map = collect_lane_aliases(text)
                lines = text.split('\n')

                column_tables = self.parse_column_oriented_tables(lines)
                for block_idx, table_data in enumerate(column_tables, start=1):
                    logger.debug(
                        "PDFium page %s: parsed column block %s (%s rows x %s cols)",
                        page_num,
                        block_idx,
                        len(table_data),
                        len(table_data[0]) if table_data else 0,
                    )
                    records = self.parse_salary_table(table_data, district, year, alias_map)
                    all_records.extend(records)

                row_table = parse_row_oriented_table(lines)
                if row_table:
                    logger.debug(
                        "PDFium page %s: parsed row-oriented fallback (%s rows x %s cols)",
                        page_num,
                        len(row_table),
                        len(row_table[0]) if row_table else 0,
                    )
                    records = self.parse_salary_table(row_table, district, year, alias_map)
                    all_records.extend(records)

                page.close()

            pdf.close()

            # Deduplicate records (same table might be extracted via column + row parsers)
            if all_records:
                all_records = self.deduplicate_records(all_records)

            return all_records if all_records else None

        except Exception as e:  # pragma: no cover - debugging helper
            logger.error(f"pypdfium2 extraction failed: {e}", exc_info=True)
            return None

    def parse_column_oriented_tables(self, lines: List[str]) -> List[List[List[str]]]:
        """Parse all column-oriented tables found within the provided text lines."""
        return parse_column_oriented_tables_from_lines(lines)

    def parse_column_oriented_table(self, lines: List[str]) -> Optional[List[List[str]]]:
        """Parse the first column-oriented table from the provided text lines."""
        return parse_column_oriented_table_from_lines(lines)

    def extract_with_pymupdf(self, pdf_bytes: bytes, filename: str, district_name: str) -> Optional[List[Dict]]:
        """
        Extract salary data using PyMuPDF

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records

        Returns:
            List of salary records or None if extraction fails
        """
        if not PYMUPDF_AVAILABLE or fitz is None:  # type: ignore[truthy-bool]
            logger.warning("PyMuPDF not available, skipping")
            return None

        try:
            logger.info(f"Extracting with PyMuPDF: {filename}")

            district = district_name
            all_records = []

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            for page_index in range(len(doc)):
                page_num = page_index + 1
                page = doc[page_index]
                text = str(page.get_text() or '')

                # Check if this looks like a salary table page
                if not text_has_salary_signal(text):
                    continue

                year = self.extract_year_from_text(text)
                alias_map = collect_lane_aliases(text)

                # Try built-in table detection first
                table_finder = getattr(page, 'find_tables', None)
                tables = table_finder() if callable(table_finder) else None
                table_objects = getattr(tables, 'tables', None) if tables is not None else None
                if table_objects:
                    logger.debug(f"Page {page_num}: PyMuPDF found {len(table_objects)} tables with built-in detection")
                    for table_obj in table_objects:
                        table_data = table_obj.extract()
                        if table_data and len(table_data) > 1:
                            # Try to extract year from table itself (first row might have FY26, etc.)
                            table_year = year  # Default to page-level year
                            if table_data[0] and table_data[0][0]:
                                first_cell = str(table_data[0][0]).strip()
                                extracted = self.extract_year_from_text(first_cell)
                                if extracted != "unknown":
                                    table_year = extracted

                            records = self.parse_salary_table(table_data, district, table_year, alias_map)
                            all_records.extend(records)

                lines = text.split('\n')
                column_tables = self.parse_column_oriented_tables(lines)
                for block_idx, table_data in enumerate(column_tables, start=1):
                    logger.debug(
                        "Page %s: parsed column-oriented block %s (%s rows x %s cols)",
                        page_num,
                        block_idx,
                        len(table_data),
                        len(table_data[0]) if table_data else 0,
                    )
                    records = self.parse_salary_table(table_data, district, year, alias_map)
                    all_records.extend(records)

                row_table = parse_row_oriented_table(lines)
                if row_table:
                    logger.debug(
                        "Page %s: parsed row-oriented fallback (%s rows x %s cols)",
                        page_num,
                        len(row_table),
                        len(row_table[0]) if row_table else 0,
                    )
                    records = self.parse_salary_table(row_table, district, year, alias_map)
                    all_records.extend(records)

            doc.close()

            # Deduplicate records (same table might be extracted via built-in + column + row parsers)
            if all_records:
                all_records = self.deduplicate_records(all_records)

            return all_records if all_records else None

        except Exception as e:
            logger.error(f"PyMuPDF extraction failed: {e}", exc_info=True)
            return None

    def extract_with_textract(self, pdf_bytes: bytes, filename: str, district_name: str, s3_bucket: str, s3_key: str) -> Optional[List[Dict]]:
        """
        Extract salary data using AWS Textract

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records
            s3_bucket: S3 bucket where PDF is stored
            s3_key: S3 key of the PDF

        Returns:
            List of salary records or None if extraction fails
        """
        try:
            logger.info(f"Extracting with AWS Textract: {filename}")

            # Use provided district name
            district = district_name

            # Start Textract job for table extraction
            response = self.textract.start_document_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': s3_bucket,
                        'Name': s3_key
                    }
                },
                FeatureTypes=['TABLES']
            )

            job_id = response['JobId']
            logger.info(f"Started Textract job: {job_id}")

            # Wait for job completion
            while True:
                result = self.textract.get_document_analysis(JobId=job_id)
                status = result['JobStatus']

                if status == 'SUCCEEDED':
                    break
                elif status == 'FAILED':
                    logger.error(f"Textract job failed: {result.get('StatusMessage')}")
                    return None

                logger.info(f"Textract job status: {status}, waiting...")
                time.sleep(2)

            # Extract all pages
            blocks = result['Blocks']

            # Get additional pages if multipage
            next_token = result.get('NextToken')
            while next_token:
                result = self.textract.get_document_analysis(
                    JobId=job_id,
                    NextToken=next_token
                )
                blocks.extend(result['Blocks'])
                next_token = result.get('NextToken')

            logger.info(f"Retrieved {len(blocks)} blocks from Textract")

            # Extract text for year detection
            full_text = ' '.join([
                block.get('Text', '') for block in blocks
                if block['BlockType'] == 'LINE'
            ])

            # Parse tables from Textract response
            all_records = []
            tables = self._parse_textract_tables(blocks)

            logger.info(f"Found {len(tables)} tables in Textract response")

            for table_data in tables:
                year = self.extract_year_from_text(full_text)
                records = self.parse_salary_table(table_data, district, year)
                all_records.extend(records)

            return all_records if all_records else None

        except Exception as e:
            logger.error(f"Textract extraction failed: {e}", exc_info=True)
            return None

    def _parse_textract_tables(self, blocks: List[Dict]) -> List[List[List[str]]]:
        """
        Parse tables from Textract blocks

        Args:
            blocks: Textract response blocks

        Returns:
            List of tables (each table is a 2D array of strings)
        """
        # Build block map
        block_map = {block['Id']: block for block in blocks}

        # Find all table blocks
        table_blocks = [block for block in blocks if block['BlockType'] == 'TABLE']

        tables = []

        for table_block in table_blocks:
            # Skip small tables (likely not salary tables)
            row_count = sum(1 for rel in table_block.get('Relationships', [{}])[0].get('Ids', [])
                          if block_map.get(rel, {}).get('BlockType') == 'CELL')
            if row_count < 10:  # Need at least header + several data rows
                continue

            # Extract cells
            cells = {}
            if 'Relationships' in table_block:
                for relationship in table_block['Relationships']:
                    if relationship['Type'] == 'CHILD':
                        for cell_id in relationship['Ids']:
                            cell_block = block_map.get(cell_id)
                            if cell_block and cell_block['BlockType'] == 'CELL':
                                row_index = cell_block.get('RowIndex', 0)
                                col_index = cell_block.get('ColumnIndex', 0)

                                # Get cell text
                                cell_text = self._get_cell_text(cell_block, block_map)
                                cells[(row_index, col_index)] = cell_text

            # Convert to 2D array
            if cells:
                max_row = max(row for row, col in cells.keys())
                max_col = max(col for row, col in cells.keys())

                table_data = []
                for row in range(1, max_row + 1):
                    row_data = []
                    for col in range(1, max_col + 1):
                        cell_text = cells.get((row, col), '')
                        row_data.append(cell_text)
                    table_data.append(row_data)

                # Check if this looks like a salary table
                if self._is_salary_table(table_data):
                    tables.append(table_data)

        return tables

    def _get_cell_text(self, cell_block: Dict, block_map: Dict) -> str:
        """Extract text from a Textract cell block"""
        text = ''
        if 'Relationships' in cell_block:
            for relationship in cell_block['Relationships']:
                if relationship['Type'] == 'CHILD':
                    for word_id in relationship['Ids']:
                        word_block = block_map.get(word_id)
                        if word_block and word_block['BlockType'] == 'WORD':
                            text += word_block.get('Text', '') + ' '
        return text.strip()

    def _is_salary_table(self, table: List[List[str]]) -> bool:
        """Check if a table looks like a salary schedule"""
        if not table or len(table) < 2:
            return False

        # Check header for education columns
        header_text = ' '.join(table[0]).upper()
        has_edu_cols = any(kw in header_text for kw in ['BA', 'MA', 'DOC', 'STEP'])

        # Check first column for step numbers
        first_col = ' '.join([row[0] for row in table[:5] if row]).upper()
        has_steps = 'STEP' in first_col or any(str(i) in first_col for i in range(1, 6))

        return has_edu_cols and has_steps

    def filter_records_by_year_and_period(self, records: List[Dict]) -> List[Dict]:
        """
        Filter records to include only relevant years and periods.

        Rules:
        1. Only include past years if there are no current or future years
        2. If including past year, only include one year (most recent)
        3. Include all current and future years
        4. For each year, only include the period that sorts last alphabetically

        Args:
            records: List of salary records

        Returns:
            Filtered list of salary records
        """
        if not records:
            return records

        from datetime import datetime

        # Determine current school year
        # School year spans July-June, so if we're in July-Dec, it's year to year+1
        # If we're in Jan-June, it's year-1 to year
        today = datetime.now()
        if today.month >= 7:  # July or later
            current_year_start = today.year
        else:  # January-June
            current_year_start = today.year - 1
        current_school_year = f"{current_year_start}-{current_year_start + 1}"

        logger.info(f"Current school year: {current_school_year}")

        # Group records by year
        years_data = {}
        for record in records:
            year = record.get('school_year', 'unknown')
            if year not in years_data:
                years_data[year] = []
            years_data[year].append(record)

        # Categorize years as past, current, or future
        past_years = []
        current_future_years = []

        for year in years_data.keys():
            if year == 'unknown':
                continue

            # Parse year (format: "YYYY-YYYY")
            try:
                year_start = int(year.split('-')[0])
                if year_start < current_year_start:
                    past_years.append(year)
                else:
                    current_future_years.append(year)
            except:
                logger.warning(f"Could not parse year: {year}")
                continue

        # Determine which years to include
        if current_future_years:
            # Have current or future years - use only those
            years_to_include = sorted(current_future_years)
            logger.info(f"Including current/future years: {years_to_include}")
        elif past_years:
            # Only have past years - use most recent one
            most_recent_past = max(past_years)
            years_to_include = [most_recent_past]
            logger.info(f"Including most recent past year: {years_to_include}")
        else:
            # No valid years found
            logger.warning("No valid years found in records")
            return records

        # For each year to include, filter to only the period that sorts last
        filtered_records = []
        for year in years_to_include:
            year_records = years_data[year]

            # Group by period
            periods = {}
            for record in year_records:
                period = record.get('period', 'full-year')
                if period not in periods:
                    periods[period] = []
                periods[period].append(record)

            # Select period that sorts last alphabetically
            selected_period = max(periods.keys())
            logger.info(f"Year {year}: selected period '{selected_period}' from {list(periods.keys())}")

            # Add all records for this year+period
            filtered_records.extend(periods[selected_period])

        logger.info(f"Filtered from {len(records)} to {len(filtered_records)} records")
        return filtered_records

    def extract_from_pdf(self, pdf_bytes: bytes, filename: str, district_name: str, s3_bucket: str, s3_key: str) -> Tuple[List[Dict], str]:
        """
        Extract salary data using hybrid approach

        Extraction order:
        1. pdfplumber (fast, works for most text PDFs)
        2. pypdfium2 (better for column-oriented layouts)
        3. PyMuPDF (better text extraction, handles encoding issues and column-oriented layouts)
        4. AWS Textract (for image-based/scanned PDFs)

        Falls back to next method if records found < 200

        Args:
            pdf_bytes: PDF file content
            filename: Original filename
            district_name: District name to use in records
            s3_bucket: S3 bucket where PDF is stored
            s3_key: S3 key of the PDF

        Returns:
            Tuple of (records, method_used)
        """
        MIN_RECORDS_THRESHOLD = 200

        # Try pdfplumber first for text-based PDFs
        if self.is_text_based_pdf(pdf_bytes):
            logger.info(f"✓ Text-based PDF detected: {filename}")
            records = self.extract_with_pdfplumber(pdf_bytes, filename, district_name)
            if records:
                # Filter records by year and period
                records = self.filter_records_by_year_and_period(records)
                if len(records) >= MIN_RECORDS_THRESHOLD:
                    logger.info(f"pdfplumber extracted {len(records)} records (>= {MIN_RECORDS_THRESHOLD})")
                    return records, "pdfplumber"
                else:
                    logger.warning(f"pdfplumber extracted only {len(records)} records (< {MIN_RECORDS_THRESHOLD}), trying next method")
            else:
                logger.warning("pdfplumber extraction returned no records")

            if PYPDFIUM_AVAILABLE and pdfium is not None:  # type: ignore[truthy-bool]
                logger.info(f"Trying pypdfium2 fallback: {filename}")
                records = self.extract_with_pypdfium(pdf_bytes, filename, district_name)
                if records:
                    records = self.filter_records_by_year_and_period(records)
                    if len(records) >= MIN_RECORDS_THRESHOLD:
                        logger.info(f"pypdfium2 extracted {len(records)} records (>= {MIN_RECORDS_THRESHOLD})")
                        return records, "pypdfium"
                    else:
                        logger.warning(f"pypdfium2 extracted only {len(records)} records (< {MIN_RECORDS_THRESHOLD}), trying next method")
                else:
                    logger.warning("pypdfium2 extraction returned no records, falling back to PyMuPDF")
            else:
                logger.info("pypdfium2 not available, skipping PDFium fallback")

            # Try PyMuPDF as fallback before Textract
            if PYMUPDF_AVAILABLE and fitz is not None:
                logger.info(f"Trying PyMuPDF fallback: {filename}")
                records = self.extract_with_pymupdf(pdf_bytes, filename, district_name)
                if records:
                    # Filter records by year and period
                    records = self.filter_records_by_year_and_period(records)
                    if len(records) >= MIN_RECORDS_THRESHOLD:
                        logger.info(f"PyMuPDF extracted {len(records)} records (>= {MIN_RECORDS_THRESHOLD})")
                        return records, "pymupdf"
                    else:
                        logger.warning(f"PyMuPDF extracted only {len(records)} records (< {MIN_RECORDS_THRESHOLD}), falling back to Textract")
                else:
                    logger.warning("PyMuPDF extraction returned no records, falling back to Textract")
            else:
                logger.warning("PyMuPDF not available, falling back to Textract")
        else:
            logger.info(f"⚠ Image-based PDF detected: {filename}")

        # Fall back to Textract for image-based PDFs or when other methods fail
        logger.info(f"Using AWS Textract for: {filename}")
        records = self.extract_with_textract(pdf_bytes, filename, district_name, s3_bucket, s3_key)
        if records:
            # Filter records by year and period
            records = self.filter_records_by_year_and_period(records)
            logger.info(f"Textract extracted {len(records)} records")
            return records, "textract"

        return [], "failed"

    def process_s3_bucket(
        self,
        input_bucket: str,
        input_prefix: str,
        output_bucket: str,
        output_prefix: str
    ) -> Dict:
        """
        Process all PDFs in an S3 bucket

        Args:
            input_bucket: S3 bucket with PDFs
            input_prefix: Prefix/folder in input bucket
            output_bucket: S3 bucket for JSON output
            output_prefix: Prefix/folder in output bucket

        Returns:
            Summary statistics
        """
        logger.info(f"Processing PDFs from s3://{input_bucket}/{input_prefix}")

        # List PDFs in input bucket
        response = self.s3.list_objects_v2(
            Bucket=input_bucket,
            Prefix=input_prefix
        )

        pdf_files = [
            obj['Key'] for obj in response.get('Contents', [])
            if obj['Key'].lower().endswith('.pdf')
        ]

        logger.info(f"Found {len(pdf_files)} PDF files")

        results = {
            'total_files': len(pdf_files),
            'successful': 0,
            'failed': 0,
            'pdfplumber_count': 0,
            'pymupdf_count': 0,
            'textract_count': 0,
            'files': []
        }

        for pdf_key in pdf_files:
            filename = Path(pdf_key).name
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing: {filename}")
            logger.info(f"{'='*60}")

            try:
                # Download PDF from S3
                pdf_obj = self.s3.get_object(Bucket=input_bucket, Key=pdf_key)
                pdf_bytes = pdf_obj['Body'].read()

                # Extract district name from filename
                district_name = Path(filename).stem.split('_')[0].title()

                # Extract data
                records, method = self.extract_from_pdf(pdf_bytes, filename, district_name, input_bucket, pdf_key)

                if records:
                    # Upload JSON to output bucket
                    output_key = f"{output_prefix}{Path(filename).stem}.json"

                    json_data = {
                        'metadata': {
                            'source_file': filename,
                            'extraction_method': method,
                            'total_records': len(records)
                        },
                        'records': records
                    }

                    self.s3.put_object(
                        Bucket=output_bucket,
                        Key=output_key,
                        Body=json.dumps(json_data, indent=2),
                        ContentType='application/json'
                    )

                    logger.info(f"✓ SUCCESS: {len(records)} records via {method}")
                    logger.info(f"✓ Saved to s3://{output_bucket}/{output_key}")

                    results['successful'] += 1
                    if method == 'pdfplumber':
                        results['pdfplumber_count'] += 1
                    elif method == 'pymupdf':
                        results['pymupdf_count'] += 1
                    elif method == 'textract':
                        results['textract_count'] += 1

                    results['files'].append({
                        'filename': filename,
                        'success': True,
                        'method': method,
                        'records': len(records)
                    })
                else:
                    logger.error(f"✗ FAILED: No data extracted")
                    results['failed'] += 1
                    results['files'].append({
                        'filename': filename,
                        'success': False,
                        'error': 'No data extracted'
                    })

            except Exception as e:
                logger.error(f"✗ ERROR: {e}", exc_info=True)
                results['failed'] += 1
                results['files'].append({
                    'filename': filename,
                    'success': False,
                    'error': str(e)
                })

        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info("EXTRACTION SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Total files:      {results['total_files']}")
        logger.info(f"Successful:       {results['successful']}")
        logger.info(f"Failed:           {results['failed']}")
        logger.info(f"pdfplumber:       {results['pdfplumber_count']}")
        logger.info(f"PyMuPDF:          {results['pymupdf_count']}")
        logger.info(f"AWS Textract:     {results['textract_count']}")
        logger.info(f"{'='*60}")

        return results