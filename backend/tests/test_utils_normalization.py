"""
Tests for normalization utilities
"""
import sys
from pathlib import Path
from decimal import Decimal

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.normalization import pad_number, generate_calculated_entries


class TestPadNumber:
    """Tests for pad_number function"""

    def test_pad_number_basic(self):
        """Test padding with zeros"""
        assert pad_number(5, 3) == "005"
        assert pad_number(42, 3) == "042"

    def test_pad_number_no_padding_needed(self):
        """Test when number already has sufficient digits"""
        assert pad_number(100, 3) == "100"
        assert pad_number(999, 3) == "999"

    def test_pad_number_longer_than_width(self):
        """Test when number is longer than requested width"""
        assert pad_number(1234, 3) == "1234"

    def test_pad_number_zero(self):
        """Test padding zero"""
        assert pad_number(0, 3) == "000"
        assert pad_number(0, 2) == "00"

    def test_pad_number_single_digit_various_widths(self):
        """Test single digit with various widths"""
        assert pad_number(5, 1) == "5"
        assert pad_number(5, 2) == "05"
        assert pad_number(5, 4) == "0005"


class TestGenerateCalculatedEntries:
    """Tests for generate_calculated_entries function"""

    def test_generate_calculated_entries_fill_down(self):
        """Test filling down a column (same edu+credit, different steps)"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        # Real entries: B+0 at steps 1 and 3
        real_entries = [
            {
                'education': 'B',
                'credits': 0,
                'step': 1,
                'salary': Decimal('50000')
            },
            {
                'education': 'B',
                'credits': 0,
                'step': 3,
                'salary': Decimal('55000')
            }
        ]

        max_step = 5
        all_edu_credit_combos = ['B+0']
        edu_order = {'B': 1, 'M': 2, 'D': 3}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        # Should generate entries for steps 2, 4, and 5
        # Step 2 should use step 1 as source (highest <= 2)
        # Steps 4 and 5 should use step 3 as source
        assert len(calculated) == 3

        # Find the calculated entry for step 2
        step_2 = next((e for e in calculated if e['step'] == 2), None)
        assert step_2 is not None
        assert step_2['salary'] == Decimal('50000')
        assert step_2['is_calculated'] is True
        assert step_2['source_step'] == 1

    def test_generate_calculated_entries_fill_right(self):
        """Test filling right (missing edu+credit combinations)"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        # Real entries: only B+0
        real_entries = [
            {
                'education': 'B',
                'credits': 0,
                'step': 1,
                'salary': Decimal('50000')
            }
        ]

        max_step = 2
        all_edu_credit_combos = ['B+0', 'B+15', 'M+0']
        edu_order = {'B': 1, 'M': 2, 'D': 3}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        # Should generate:
        # - Step 2 for B+0 (fill down)
        # - Steps 1 and 2 for B+15 (fill right)
        # - Steps 1 and 2 for M+0 (fill right)
        assert len(calculated) == 5

        # Check B+15 entries
        b15_entries = [e for e in calculated if e['education'] == 'B' and e['credits'] == 15]
        assert len(b15_entries) == 2

        # Check M+0 entries
        m0_entries = [e for e in calculated if e['education'] == 'M' and e['credits'] == 0]
        assert len(m0_entries) == 2

    def test_generate_calculated_entries_no_missing_combos(self):
        """Test when all combinations are already present"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        real_entries = [
            {'education': 'B', 'credits': 0, 'step': 1, 'salary': Decimal('50000')},
            {'education': 'B', 'credits': 0, 'step': 2, 'salary': Decimal('52000')},
        ]

        max_step = 2
        all_edu_credit_combos = ['B+0']
        edu_order = {'B': 1}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        # No calculated entries needed - all real entries exist for all steps
        assert len(calculated) == 0

    def test_generate_calculated_entries_sort_key_format(self):
        """Test that generated entries have correct DynamoDB key format"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        real_entries = [
            {'education': 'B', 'credits': 15, 'step': 1, 'salary': Decimal('50000')}
        ]

        max_step = 2
        all_edu_credit_combos = ['B+15']
        edu_order = {'B': 1}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        assert len(calculated) == 1
        entry = calculated[0]

        # Check PK and SK format
        assert entry['PK'] == 'DISTRICT#district-123'
        assert entry['SK'] == 'SCHEDULE#2024-2025#full-year#EDU#B#CR#015#STEP#02'

        # Check GSI keys
        assert entry['GSI1PK'] == 'YEAR#2024-2025#PERIOD#full-year#EDU#B#CR#015'
        assert entry['GSI1SK'] == 'STEP#02#DISTRICT#district-123'
        assert entry['GSI2PK'] == 'YEAR#2024-2025#PERIOD#full-year#DISTRICT#district-123'
        assert entry['GSI2SK'] == 'EDU#B#CR#015#STEP#02'

    def test_generate_calculated_entries_preserves_decimal_type(self):
        """Test that salary values remain as Decimal"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        real_entries = [
            {'education': 'B', 'credits': 0, 'step': 1, 'salary': Decimal('50000.50')}
        ]

        max_step = 2
        all_edu_credit_combos = ['B+0']
        edu_order = {'B': 1}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        assert len(calculated) == 1
        assert isinstance(calculated[0]['salary'], Decimal)
        assert calculated[0]['salary'] == Decimal('50000.50')

    def test_generate_calculated_entries_converts_float_to_decimal(self):
        """Test that float salaries are converted to Decimal"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        real_entries = [
            {'education': 'B', 'credits': 0, 'step': 1, 'salary': 50000.50}  # float
        ]

        max_step = 2
        all_edu_credit_combos = ['B+0']
        edu_order = {'B': 1}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        assert len(calculated) == 1
        assert isinstance(calculated[0]['salary'], Decimal)

    def test_generate_calculated_entries_tracks_source(self):
        """Test that is_calculated_from correctly tracks the source"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        real_entries = [
            {'education': 'B', 'credits': 0, 'step': 1, 'salary': Decimal('50000')}
        ]

        max_step = 2
        all_edu_credit_combos = ['B+0']
        edu_order = {'B': 1}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        assert len(calculated) == 1
        entry = calculated[0]

        assert entry['is_calculated'] is True
        assert 'is_calculated_from' in entry
        assert entry['is_calculated_from']['education'] == 'B'
        assert entry['is_calculated_from']['credits'] == 0
        assert entry['is_calculated_from']['step'] == 1

    def test_generate_calculated_entries_education_level_ordering(self):
        """Test that fill right respects education level ordering"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        # Only have M+0
        real_entries = [
            {'education': 'M', 'credits': 0, 'step': 1, 'salary': Decimal('60000')}
        ]

        max_step = 1
        all_edu_credit_combos = ['B+0', 'M+0', 'D+0']
        edu_order = {'B': 1, 'M': 2, 'D': 3}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        # The algorithm does not allow using a higher education level as source
        # So B+0 cannot be generated from M+0 (M is higher than B in the ordering)
        # But D+0 can use M+0 as source (M is lower than D in the ordering)
        assert len(calculated) == 1

        d0_entry = next((e for e in calculated if e['education'] == 'D'), None)
        assert d0_entry is not None

        # B+0 should not be generated because M is a higher edu level
        b0_entry = next((e for e in calculated if e['education'] == 'B'), None)
        assert b0_entry is None

    def test_generate_calculated_entries_multiple_steps_complete(self):
        """Test comprehensive scenario with multiple education levels and steps"""
        district_id = "district-123"
        district_name = "Test District"
        year = "2024-2025"
        period = "full-year"

        real_entries = [
            {'education': 'B', 'credits': 0, 'step': 1, 'salary': Decimal('50000')},
            {'education': 'B', 'credits': 0, 'step': 3, 'salary': Decimal('54000')},
            {'education': 'M', 'credits': 0, 'step': 1, 'salary': Decimal('60000')},
        ]

        max_step = 3
        all_edu_credit_combos = ['B+0', 'M+0', 'M+15']
        edu_order = {'B': 1, 'M': 2, 'D': 3}

        calculated = generate_calculated_entries(
            district_id, district_name, year, period,
            real_entries, max_step, all_edu_credit_combos, edu_order
        )

        # Expected calculated entries:
        # B+0: step 2 (from step 1)
        # M+0: steps 2 and 3 (from step 1)
        # M+15: steps 1, 2, 3 (all from M+0)

        b0_calculated = [e for e in calculated if e['education'] == 'B' and e['credits'] == 0]
        m0_calculated = [e for e in calculated if e['education'] == 'M' and e['credits'] == 0]
        m15_calculated = [e for e in calculated if e['education'] == 'M' and e['credits'] == 15]

        assert len(b0_calculated) == 1  # step 2
        assert len(m0_calculated) == 2  # steps 2, 3
        assert len(m15_calculated) == 3  # steps 1, 2, 3
