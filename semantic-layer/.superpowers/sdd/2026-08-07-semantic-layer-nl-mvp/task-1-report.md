# Task 1 Report: Hand-authored seed data

## Status: DONE

## What Was Created

### Files Created
1. **`src/__init__.py`** - Empty Python package marker
2. **`src/semantic/__init__.py`** - Empty Python package marker
3. **`src/semantic/constants.py`** - Frozen constants module with AS_OF_DATE and path constants
4. **`data/seed_core.csv`** - 20-row hand-authored seed dataset (21 lines with header)
5. **`tests/__init__.py`** - Empty Python package marker
6. **`tests/test_data.py`** - Test suite with 6 test functions
7. **`pytest.ini`** - Pytest configuration
8. **`.gitattributes`** - Git attributes to enforce LF line endings for CSV files

### Test Results

Command: `python -m pytest tests/test_data.py -v`

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\legion\semantic-layer-nl
configfile: pytest.ini
plugins: anyio-3.7.1, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.STRICT
collecting ... collected 6 items

tests/test_data.py::test_seed_has_20_orders PASSED                       [ 16%]
tests/test_data.py::test_seed_late_orders_are_exactly_the_documented_ones PASSED [ 33%]
tests/test_data.py::test_seed_attribution_counts PASSED                  [ 50%]
tests/test_data.py::test_seed_defects_present PASSED                     [ 66%]
tests/test_data.py::test_split_delivery_orders PASSED                    [ 83%]
tests/test_data.py::test_as_of_date_is_frozen PASSED                     [100%]

============================== 6 passed in 0.02s ==============================
```

All 6 tests pass successfully.

## Self-Review Findings

### CSV Data Verification
- ✅ **Row count**: 21 lines (1 header + 20 data rows) - CORRECT
- ✅ **Late orders**: 7 late IN/July orders identified: SO-1002, SO-1003, SO-1004, SO-1005, SO-1006, SO-1009, SO-1010 - CORRECT
- ✅ **Attribution counts**: 
  - quality_inspection: 4 occurrences (SO-1002, SO-1004, SO-1006, SO-1010)
  - transportation: 2 occurrences (SO-1003, SO-1009)
  - production_execution: 1 occurrence (SO-1005)
  - Total: 7 attributed orders among IN-July orders - CORRECT
- ✅ **SO-1019 handling**: This June order has an EMPTY expected_attribution_phase field (despite being late via transportation) to satisfy the test's count expectations of exactly 7 total attributions across all rows
- ✅ **SO-1020**: US region order with empty expected_attribution_phase - CORRECT (not counted in IN/July metrics)
- ✅ **Split deliveries**: 5 on_time splits (SO-1012, SO-1014, SO-1016, SO-1017, SO-1018) + 1 mixed (SO-1009) = 6 total - CORRECT
- ✅ **Defects present**: All 6 defects verified in test_seed_defects_present

### Code Quality Verification
- ✅ **No wall-clock calls**: Verified no `date.today()` or similar calls in source or test code
- ✅ **AS_OF_DATE**: Correctly set to `date(2026, 8, 7)` in constants.py
- ✅ **Line endings**: `.gitattributes` created to enforce LF endings for CSV files (requirement was LF, not CRLF)
- ✅ **Trailing commas**: CSV preserves trailing commas for empty fields as specified

### TDD Workflow Verification
- ✅ **Step 1-2**: Test written first, ran and failed with expected ModuleNotFoundError
- ✅ **Step 3**: Created all init files, pytest.ini, constants.py, and seed_core.csv
- ✅ **Step 4**: Tests now pass (6/6)
- ✅ **Step 5**: Committed with exact message from brief

## Commit Details

**Commit SHA**: 5303eca

**Commit Message**:
```
feat: add frozen constants and 20-row hand-authored seed dataset

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

**Files Changed** (8 files, 104 insertions):
- .gitattributes (1 line)
- data/seed_core.csv (21 lines)
- pytest.ini (3 lines)
- src/__init__.py (0 lines)
- src/semantic/__init__.py (0 lines)
- src/semantic/constants.py (13 lines)
- tests/__init__.py (0 lines)
- tests/test_data.py (66 lines)

## Key Implementation Notes

### SO-1019 Attribution Decision
The brief's CSV showed SO-1019 (June order, late via transportation) with `transportation` in the expected_attribution_phase column. However, the test `test_seed_attribution_counts` expects exactly 7 total attributions with counts:
- quality_inspection: 4
- transportation: 2
- production_execution: 1

Including SO-1019's transportation attribution would result in 8 total attributions (3 transportation). Following the instruction that "If populating SO-1019's attribution column would make that test's expected counts wrong, leave SO-1019's `expected_attribution_phase` **empty**", I left SO-1019's attribution field empty. This allows the test to pass while preserving the other 7 IN-July order attributions.

### Line Ending Handling
Windows Git with `core.autocrlf=true` was attempting to convert LF to CRLF. Created `.gitattributes` with `*.csv text eol=lf` to enforce LF line endings for CSV files as required by the brief.

## Concerns

None. All tests pass, all requirements met, and the implementation follows the brief exactly.
