#!/usr/bin/env python3
"""
Improved PDF salary table extraction using PyMuPDF and pypdfium2
Handles both row-oriented and column-oriented table layouts
"""
import argparse
import csv
import fitz  # PyMuPDF
import re
from decimal import Decimal, InvalidOperation
import decimal
from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import pypdfium2 as pdfium
    PYPDFIUM_AVAILABLE = True
except ImportError:
    pdfium = None  # type: ignore
    PYPDFIUM_AVAILABLE = False
    print("Warning: pypdfium2 not available. Install with: pip install pypdfium2")

try:
    import pdfplumber  # type: ignore
    PDFPLUMBER_AVAILABLE = True
except Exception as e:
    pdfplumber = None  # type: ignore
    PDFPLUMBER_AVAILABLE = False
    print(f"Warning: pdfplumber not available: {e}")

ROOT_DIR = Path(__file__).resolve().parents[0]
DEFAULT_CONTRACTS_DIR = ROOT_DIR / 'data' / 'results_contracts'


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
}


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


def normalize_lane_key(text: Any) -> str:
    if text is None:
        return 'NONE'
    raw = str(text).upper()
    raw = raw.replace('–', '-').replace('—', '-').replace(':', '-')
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

    # Normalize BA-15 / BA15 to BA+15 for consistent mapping
    raw = raw.replace('-', '+')
    raw = re.sub(r'\+L(\d)', r'+1\1', raw)
    raw = re.sub(r'\+I(\d)', r'+1\1', raw)
    raw = re.sub(r'\b(BA|MA)(\d{1,3})\b', r'\1+\2', raw)
    raw = re.sub(r'\b(B|M)(\d{1,3})\b', r'\1+\2', raw)

    tokens = tokenize_lane_labels(raw)
    if tokens:
        return tokens[0]

    simplified = re.sub(r'[^A-Z0-9+ ]', '', raw).replace(' ', '')

    # Handle explicit lane references (Lane 1, Pay Scale 2, Level III, etc.)
    lane_match = re.match(r'LANE(\d+)', simplified)
    if lane_match:
        return f"LANE{lane_match.group(1)}"

    pay_scale_match = re.match(r'PAYSCALE(\d+)', simplified)
    if pay_scale_match:
        return f"PAYSCALE{pay_scale_match.group(1)}"

    level_match = re.match(r'LEVEL(\d+)', simplified)
    if level_match:
        return f"LEVEL{level_match.group(1)}"

    roman_match = re.fullmatch(r'[IVXLCDM]+', simplified)
    if roman_match:
        roman_value = roman_to_int(roman_match.group(0))
        if roman_value:
            return f"LANE{roman_value}"

    if simplified:
        return simplified

    return 'NONE'



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


def tokenize_lane_labels(text: str) -> List[str]:
    if not text:
        return []

    normalized = text.upper()
    normalized = normalized.replace('B.A.', 'BA').replace('M.A.', 'MA')
    normalized = normalized.replace('BACCALAUREATE', 'BA').replace('BACHELOR', 'BA')
    normalized = normalized.replace('MASTERS', 'MA').replace('MASTER', 'MA')
    normalized = normalized.replace('/', ' ')
    normalized = normalized.replace('-', '+')
    normalized = re.sub(r'\([IVX]+\)', ' ', normalized)
    normalized = re.sub(r'[^A-Z0-9+ ]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = normalized.replace(' + ', '+').strip()
    normalized = re.sub(r'\b(BA|MA)(\d{1,3})\b', r'\1+\2', normalized)
    normalized = re.sub(r'\b(B|M)(\d{1,3})\b', r'\1+\2', normalized)

    token_pattern = re.compile(r'(?:BA|MA)(?:\+\d+)?|B\+\d+|M\+\d+|CAGS|DOC|DR|EDD', re.I)
    tokens = token_pattern.findall(normalized)
    cleaned = [token.upper().replace(' ', '') for token in tokens]
    return cleaned


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
    """Convert raw table cells to trimmed string lists for consistent comparisons."""
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
    """Split a table that contains multiple 'Step' headers into separate sub tables."""
    if not table or not table[0]:
        return []

    header = table[0]
    step_indices = [idx for idx, cell in enumerate(header)
                    if str(cell).strip().upper() == 'STEP']

    if not step_indices or len(step_indices) == 1 and step_indices[0] == 0:
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


def summarize_method_bucket(method: str) -> str:
    method = method.lower()
    if method.startswith('pypdfium2'):
        return 'pypdfium'
    if method.startswith('pymupdf'):
        return 'pymupdf'
    if method.startswith('pdfplumber'):
        return 'pdfplumber'
    return 'other'


def extract_year_from_text(text: str) -> str:
    """Extract school year from text"""
    if not text:
        return "unknown"

    # Pattern 1: YYYY-YYYY
    match = re.search(r'(\d{4})\s*[-–—]\s*(\d{4})', text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"

    # Pattern 2: "Effective [Month] [Day,] YYYY"
    match = re.search(
        r'Effective\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+(\d{4})',
        text,
        re.IGNORECASE
    )
    if match:
        year = int(match.group(1))
        return f"{year}-{year + 1}"

    # Pattern 3: "FY YYYY" or "FY YY"
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

    # Pattern 4: Any 4-digit year
    years = re.findall(r'\b(20\d{2})\b', text)
    if years:
        year = int(max(years))
        return f"{year}-{year + 1}"

    return "unknown"


def split_row_tokens(line: str) -> List[str]:
    """Split a line into tokens using double-space or tab delimiters."""
    if not line:
        return []
    # Replace tabs with spaces and collapse multiple spaces for splitting
    normalized = line.replace('\t', '    ')
    tokens = [tok.strip() for tok in re.split(r'\s{2,}', normalized) if tok.strip()]
    if len(tokens) > 1:
        return tokens
    # Fall back to generic whitespace split if double-space heuristic failed
    fallback = [tok.strip() for tok in normalized.split() if tok.strip()]
    return fallback


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
    """Extract a step value from token list, supporting formats like 'Step 1', '1-1', etc."""
    for idx, token in enumerate(tokens):
        candidate = token.replace('–', '-').replace('—', '-')
        match = re.match(r'^(?:STEP)?\s*(\d{1,2})(?:[-/]\d+)?$', candidate, re.I)
        if match:
            step_value = match.group(1)
            remaining = tokens[:idx] + tokens[idx + 1:]
            return step_value, remaining
    return None, tokens


def parse_row_oriented_table(lines: List[str]) -> Optional[List[List[str]]]:
    """
    Parse typical row-oriented tables where each line contains a full row, e.g.:

    Step   BA   BA+15   MA
    1    $40,100 $41,500 $43,000
    """
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
                # No step number found; stop scanning this block
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

    print(f"  Found 'Step' header at line {header_idx}")

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
            print(f"  Line {i}: '{first_token}' looks like first step marker")
            break

        if len(tokens) == 1:
            token = tokens[0]
            if looks_like_lane_header_token(token):
                print(f"  Line {i}: '{token}' is education level")
                header.append(token)
                i += 1
                continue
            if re.match(r'^\d{1,2}$', token) and not re.search(r'[A-Z]', token, re.I):
                print(f"  Line {i}: '{token}' could be education level")
                header.append(token)
                i += 1
                continue

        if len(tokens) > 1 and all(looks_like_lane_header_token(tok) for tok in tokens):
            print(
                f"  Line {i}: parsed {len(tokens)} lane header token(s) from '{edu}'"
            )
            header.extend(tokens)
            i += 1
            continue

        print(f"  Line {i}: '{edu}' - stopping header collection")
        break

    if len(header) < 2:
        print(f"  ERROR: Only found {len(header)} columns")
        return None, line_count

    num_cols = len(header)
    print(f"  Detected column-oriented table with {num_cols} columns: {header}")

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
                idx += 1
                continue

            print(f"  Encountered new section token '{token}' at stream index {idx}; stopping table parse")
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


def parse_column_oriented_tables(lines: List[str]) -> List[List[List[str]]]:
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


def parse_column_oriented_table(lines: List[str]) -> Optional[List[List[str]]]:
    tables = parse_column_oriented_tables(lines)
    return tables[0] if tables else None


def extract_text_with_pypdfium(pdf_path: str) -> List[Tuple[int, str]]:
    """
    Extract text from PDF using pypdfium2

    Returns:
        List of (page_num, text) tuples
    """
    if not PYPDFIUM_AVAILABLE or pdfium is None:
        return []

    try:
        pdf = pdfium.PdfDocument(pdf_path)  # type: ignore
        pages_text = []

        for page_num in range(len(pdf)):
            page = pdf[page_num]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            pages_text.append((page_num + 1, text))

        return pages_text
    except Exception as e:
        print(f"  pypdfium2 extraction failed: {e}")
        return []


def extract_tables_from_pdf(pdf_path: str) -> Tuple[List[Dict], List[str]]:
    """
    Extract salary tables from PDF using multiple strategies to maximize coverage.

    Returns a list of dicts containing 'page', 'year', 'table', and 'method'.
    Duplicate tables (same method, page, and cell contents) are deduplicated.
    """
    results: List[Dict] = []
    seen_tables = set()
    attempted_methods: List[str] = []
    trigger_pattern = re.compile(
        r'(SALARY|COMPENSATION|TEACHERS?|SCHEDULE|PAY\s*SCALES?|ACADEMIC|STEP)',
        re.I
    )

    def add_result(
        page_num: int,
        year: str,
        table_data: Optional[Sequence[Sequence[Any]]],
        method: str,
        alias_map: Optional[Dict[str, str]] = None
    ) -> None:
        normalized = normalize_table_data(table_data)
        if len(normalized) < 2:
            return

        for sub_table in split_table_on_step_columns(normalized):
            if len(sub_table) < 2:
                continue

            key = (method, page_num, tuple(tuple(row) for row in sub_table))
            if key in seen_tables:
                continue

            seen_tables.add(key)
            results.append({
                'page': page_num,
                'year': year,
                'table': sub_table,
                'method': method,
                'aliases': alias_map or {}
            })

    if PYPDFIUM_AVAILABLE and pdfium is not None:
        attempted_methods.append('pypdfium')
        print("  Trying pypdfium2 extraction...")
        pypdfium_pages = extract_text_with_pypdfium(pdf_path)

        for page_num, text in pypdfium_pages:
            if not trigger_pattern.search(text):
                continue

            year = extract_year_from_text(text)
            print(f"\nPage {page_num}: Detected salary schedule for {year} (pypdfium2)")
            lines = text.split('\n')
            alias_map = collect_lane_aliases(text)
            column_tables = parse_column_oriented_tables(lines)

            for block_idx, table_data in enumerate(column_tables, start=1):
                if table_data:
                    print(
                        f"  pypdfium2 success (block {block_idx}): "
                        f"{len(table_data)} rows x {len(table_data[0])} cols"
                    )
                    add_result(page_num, year, table_data, 'pypdfium2-column', alias_map)

            row_table = parse_row_oriented_table(lines)
            if row_table:
                print(f"  pypdfium2 row-parse success: {len(row_table)} rows x {len(row_table[0])} cols")
                add_result(page_num, year, row_table, 'pypdfium2-row', alias_map)

    else:
        print("  pypdfium2 not available; skipping pypdfium pass.")

    attempted_methods.append('pymupdf')
    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            page_num = page_index + 1
            page = doc[page_index]
            text = str(page.get_text() or '')

            if not trigger_pattern.search(text):
                continue

            year = extract_year_from_text(text)
            print(f"\nPage {page_num}: Detected salary schedule for {year} (PyMuPDF)")
            alias_map = collect_lane_aliases(text)

            table_finder = getattr(page, 'find_tables', None)
            tables = table_finder() if callable(table_finder) else None
            table_objects = getattr(tables, 'tables', None) if tables is not None else None
            if table_objects:
                print(f"  Built-in table detection: {len(table_objects)} tables")
                for table_obj in table_objects:
                    table_data = table_obj.extract()
                    if table_data:
                        table_year = year
                        if table_data[0] and table_data[0][0]:
                            first_cell = str(table_data[0][0]).strip()
                            extracted_year = extract_year_from_text(first_cell)
                            if extracted_year != "unknown":
                                table_year = extracted_year

                        add_result(page_num, table_year, table_data, 'pymupdf-table', alias_map)

            print("  Trying column-oriented table parsing...")
            lines = text.split('\n')
            column_tables = parse_column_oriented_tables(lines)

            for block_idx, table_data in enumerate(column_tables, start=1):
                print(
                    f"  Successfully parsed block {block_idx}: "
                    f"{len(table_data)} rows x {len(table_data[0])} cols"
                )
                add_result(page_num, year, table_data, 'pymupdf-text-column', alias_map)

            row_table = parse_row_oriented_table(lines)
            if row_table:
                print(f"  Row-oriented parse: {len(row_table)} rows x {len(row_table[0])} cols")
                add_result(page_num, year, row_table, 'pymupdf-text-row', alias_map)
    finally:
        doc.close()

    if PDFPLUMBER_AVAILABLE and pdfplumber is not None:
        attempted_methods.append('pdfplumber')
        print("  Trying pdfplumber extraction...")
        try:
            with pdfplumber.open(pdf_path) as plumber_doc:  # type: ignore[arg-type]
                for page_index, page in enumerate(plumber_doc.pages):  # type: ignore[attr-defined]
                    page_num = page_index + 1
                    text = page.extract_text() or ''
                    if not trigger_pattern.search(text):
                        continue

                    year = extract_year_from_text(text)
                    alias_map = collect_lane_aliases(text)
                    tables = page.extract_tables() or []
                    if tables:
                        print(f"  pdfplumber page {page_num}: {len(tables)} table(s)")
                    for table_data in tables:
                        add_result(page_num, year, table_data, 'pdfplumber-table', alias_map)
        except Exception as plumber_exc:
            print(f"  WARNING: pdfplumber extraction failed: {plumber_exc}")
    else:
        print("  pdfplumber not installed; skipping pdfplumber extraction pass.")

    return results, attempted_methods


def parse_salary_table(
    table: List[List[str]],
    district_name: str,
    year: str,
    alias_map: Optional[Dict[str, str]] = None
) -> List[Dict]:
    """Parse table data into salary records"""
    if not table or len(table) < 2:
        return []

    records = []

    # Find the actual header row (look for "Step" in first column)
    header_row_idx = 0
    for idx, row in enumerate(table):
        if row and str(row[0]).strip().upper() == 'STEP':
            header_row_idx = idx
            break

    if header_row_idx > 0:
        print(f"    Skipping {header_row_idx} non-header row(s) at top of table")

    # Parse header
    raw_header = table[header_row_idx]
    normalized_header = [normalize_lane_key(h) for h in raw_header]
    alias_map = alias_map or {}

    # Map each column to education level
    edu_columns = []
    for i, (raw_cell, normalized_cell) in enumerate(zip(raw_header, normalized_header)):
        if i == 0:  # Skip first column (step numbers)
            continue

        display_label = str(raw_cell).strip() or normalized_cell
        if normalized_cell in EDU_MAP:
            edu_columns.append((i, display_label, EDU_MAP[normalized_cell]))
            continue

        alias_key = normalize_lane_key(display_label)
        mapped_key = alias_map.get(alias_key) or alias_map.get(normalized_cell)
        if mapped_key and mapped_key in EDU_MAP:
            edu_columns.append((i, display_label, EDU_MAP[mapped_key]))
            continue
        else:
            print(f"    WARNING: Unknown education level '{display_label}' (normalized: '{normalized_cell}') in column {i}")

    print(f"    Mapped columns: {[(h, edu, cr) for _, h, (edu, cr) in edu_columns]}")

    # Parse data rows (skip everything up to and including the header row)
    for row_idx, row in enumerate(table[header_row_idx + 1:], header_row_idx + 2):
        if not row or len(row) < 2:
            continue

        # Extract step number
        step_str = str(row[0]).strip()
        step_match = re.search(r'(\d+)', step_str)
        if not step_match:
            continue
        step = int(step_match.group(1))

        # Extract salaries for each education column
        for col_idx, col_name, (education, credits) in edu_columns:
            if col_idx >= len(row):
                continue

            salary_str = str(row[col_idx]).strip()
            if not salary_str:
                continue

            # Clean and parse salary
            salary_cleaned = re.sub(r'[$,\s]', '', salary_str)
            try:
                salary = float(Decimal(salary_cleaned))

                if salary > 0:  # Sanity check
                    records.append({
                        'district_id': district_name.lower().replace(' ', '-'),
                        'district_name': district_name,
                        'school_year': year,
                        'period': 'full-year',
                        'education': education,
                        'credits': credits,
                        'step': step,
                        'salary': salary
                    })
            except (ValueError, InvalidOperation) as e:
                print(f"    WARNING: Could not parse salary '{salary_str}' at row {row_idx}, col {col_idx}: {e}")

    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract teacher salary tables from PDF contracts"
    )
    parser.add_argument(
        '--dir',
        type=str,
        default=None,
        help=f"Directory to scan for PDFs (default: {DEFAULT_CONTRACTS_DIR})"
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Only process the first N PDFs (useful for testing)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='extracted_salaries.json',
        help='Path to write extracted salary records (JSON)'
    )
    parser.add_argument(
        '--summary-output',
        type=str,
        default='extraction_summary.csv',
        help='Path to write per-document summary table (CSV)'
    )
    parser.add_argument(
        'pdf_files',
        nargs='*',
        help='Specific PDF files to process (overrides automatic directory scan)'
    )

    args = parser.parse_args()

    # Resolve PDF list: explicit args take precedence, otherwise scan directory
    pdf_paths: List[Path]
    if args.pdf_files:
        pdf_paths = [Path(p).expanduser().resolve() for p in args.pdf_files]
    else:
        target_dir = Path(args.dir).expanduser().resolve() if args.dir else DEFAULT_CONTRACTS_DIR
        if not target_dir.exists():
            raise FileNotFoundError(f"PDF directory not found: {target_dir}")
        pdf_paths = sorted(p for p in target_dir.rglob('*.pdf') if p.is_file())

    if args.limit:
        pdf_paths = pdf_paths[:args.limit]

    if not pdf_paths:
        print("No PDF files found to process.")
        return

    print(f"Found {len(pdf_paths)} PDF(s) to process.")
    all_records: List[Dict] = []
    per_pdf_summary: List[Dict[str, Any]] = []

    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            print(f"ERROR: File not found: {pdf_path}")
            continue

        district = pdf_path.stem.split('_')[0].title()
        method_counts: Dict[str, int] = {'pypdfium': 0, 'pymupdf': 0, 'pdfplumber': 0, 'other': 0}

        print(f"\n{'='*70}")
        print(f"Processing: {pdf_path.name}")
        print(f"District: {district}")
        print(f"{'='*70}")

        attempted: List[str] = []
        try:
            tables, attempted = extract_tables_from_pdf(str(pdf_path))

            if not tables:
                print("  WARNING: No tables found in PDF")
                continue

            for table_info in tables:
                records = parse_salary_table(
                    table_info['table'],
                    district,
                    table_info['year'],
                    table_info.get('aliases')
                )
                all_records.extend(records)
                method = table_info.get('method', 'unknown')
                bucket = summarize_method_bucket(method)
                method_counts.setdefault(bucket, 0)
                method_counts[bucket] += len(records)
                print(f"  ✓ Extracted {len(records)} salary records (method: {method})")

        except Exception as exc:  # pragma: no cover - debugging helper
            print(f"  ERROR: Failed to process PDF: {exc}")
            import traceback
            traceback.print_exc()

        per_pdf_summary.append({
            'document': pdf_path.name,
            'pypdfium_records': method_counts.get('pypdfium', 0),
            'pymupdf_records': method_counts.get('pymupdf', 0),
            'pdfplumber_records': method_counts.get('pdfplumber', 0),
            'other_records': method_counts.get('other', 0),
            'total_records': sum(method_counts.values()),
            'attempted_pypdfium': 'pypdfium' in attempted,
            'attempted_pymupdf': 'pymupdf' in attempted,
            'attempted_pdfplumber': 'pdfplumber' in attempted,
        })

    print(f"\n{'='*70}")
    print(f"TOTAL RECORDS EXTRACTED: {len(all_records)}")
    print(f"{'='*70}")

    if all_records:
        by_district: Dict[Tuple[str, str], List[Dict]] = {}
        for rec in all_records:
            key = (rec['district_name'], rec['school_year'])
            by_district.setdefault(key, []).append(rec)

        print("\nBreakdown:")
        for (dist, year), recs in sorted(by_district.items()):
            steps = len({r['step'] for r in recs})
            edu_levels = len({(r['education'], r['credits']) for r in recs})
            print(f"  {dist} ({year}): {len(recs)} records ({steps} steps × {edu_levels} edu levels)")

        print("\nSample records (first 15):")
        for rec in sorted(all_records, key=lambda x: (x['school_year'], x['step'], x['credits']))[:15]:
            print(
                f"  {rec['district_name']:15s} | {rec['school_year']} | "
                f"Step {rec['step']:2d} | {rec['education']}+{rec['credits']:2d} | "
                f"${rec['salary']:>9,.2f}"
            )

        if per_pdf_summary:
            print("\nPer-document summary (records by extraction engine; ✓ = attempted method)")
            header = (
                f"{'Document':45s} | {'pypdfium':12s} | {'pymupdf':11s} | "
                f"{'pdfplumb':11s} | {'other':7s} | {'total':5s}"
            )
            print(header)
            print('-' * len(header))
            for entry in per_pdf_summary:
                def fmt(col: str, attempted_key: str, width: int) -> str:
                    return f"{entry[col]:{width - 2}d} {'✓' if entry[attempted_key] else '✗'}"

                print(
                    f"{entry['document'][:45]:45s} | "
                    f"{fmt('pypdfium_records', 'attempted_pypdfium', 12)} | "
                    f"{fmt('pymupdf_records', 'attempted_pymupdf', 11)} | "
                    f"{fmt('pdfplumber_records', 'attempted_pdfplumber', 11)} | "
                    f"{entry['other_records']:7d} | "
                    f"{entry['total_records']:5d}"
                )

        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump({
                'records': all_records,
                'summary': per_pdf_summary,
            }, f, indent=2)
        print(f"\n💾 Saved {len(all_records)} records plus summary to {output_path}")

        summary_path = Path(args.summary_output).expanduser().resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, 'w', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=[
                'document',
                'pypdfium_records',
                'attempted_pypdfium',
                'pymupdf_records',
                'attempted_pymupdf',
                'pdfplumber_records',
                'attempted_pdfplumber',
                'other_records',
                'total_records',
            ])
            writer.writeheader()
            for entry in per_pdf_summary:
                writer.writerow(entry)
        print(f"💾 Saved summary table to {summary_path}")
    else:
        print("\n⚠️  No salary records extracted")


if __name__ == '__main__':
    main()
