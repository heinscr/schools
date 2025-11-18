"""
Utility functions for PDF salary contract extraction
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

# Import common extraction utilities
from .extraction_common import (
    parse_salary_value,
    is_salary_value,
    extract_step_number as common_extract_step_number,
    is_step_marker,
    has_salary_table_signal as common_has_salary_table_signal,
    looks_like_step_header as common_looks_like_step_header,
)

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
    """Check if text looks like a step header - delegates to common implementation"""
    return common_looks_like_step_header(text)


STEP_MARKER_PATTERN = re.compile(r'^\d{1,2}(?:[-/]\d{1,2})?$')


def is_column_step_marker(text: str) -> bool:
    """Check if text is a step marker - delegates to common implementation"""
    return is_step_marker(text)


def is_column_salary_value(text: str) -> bool:
    """Check if text is a salary value - delegates to common implementation"""
    return is_salary_value(text)


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
    """Check if text has salary table signals - delegates to common implementation"""
    return common_has_salary_table_signal(text)


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


