#!/usr/bin/env python3
"""
Import NH Department of Education funding data into SQLite database.
Handles 137+ CSV/XLSX files spanning FY2004-FY2027 with varying schemas.
"""

import csv
import os
import re
import sqlite3
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    openpyxl = None
    print("WARNING: openpyxl not installed - XLSX files will be skipped")

DATA_DIR = Path(__file__).parent
DB_PATH = DATA_DIR / "education_aid.db"

# Known municipality name normalizations
NAME_FIXES = {
    "Hart's Location": "Harts Location",
    "Hart's Loc": "Harts Location",
    "Hart's Location": "Harts Location",
    "Waterville Valley": "Waterville Valley",
    "New Castle": "New Castle",
    "Newcastle": "New Castle",
    "Wentworth's Location": "Wentworths Location",
    "Wentworth's Loc": "Wentworths Location",
    "Wentworth's Location": "Wentworths Location",
}

# Base cost per pupil by fiscal year (from file headers)
BASE_COST_PER_PUPIL = {
    2004: 3390.00, 2006: 3917.00, 2007: 3917.00, 2008: 3917.00,
    2009: 3917.00, 2010: 3450.00, 2011: 3450.00, 2012: 3450.00,
    2013: 3450.00, 2014: 3498.30, 2015: 3561.27, 2016: 3561.27,
    2017: 3636.06, 2018: 3636.06, 2019: 3708.78, 2020: 3708.78,
    2021: 3708.78, 2022: 3786.66, 2023: 3786.66, 2024: 4100.00,
    2025: 4182.00, 2026: 4265.64, 2027: 4350.00,
}

# SWEPT rate per $1,000 by fiscal year
SWEPT_RATES = {
    2004: 4.92, 2006: 2.84, 2007: 2.515, 2008: 2.24, 2009: 2.14,
    2010: 2.135, 2011: 2.19, 2012: 2.325, 2013: 2.39, 2014: 2.435,
    2015: 2.48, 2016: 2.39, 2017: 2.31, 2018: 2.26, 2019: 2.14,
    2020: 2.04, 2021: 1.925, 2022: 1.88, 2023: 1.88, 2024: 1.38,
    2025: 1.22, 2026: 1.12, 2027: 1.06,
}


def parse_money(val):
    """Convert currency string to float. Handles '$1,234.56', '(1,234)', '-', etc."""
    if val is None:
        return None
    val = str(val).strip()
    if not val or val == '-' or val == '- ' or val == ' -   ' or val == '#REF!':
        return 0.0
    # Remove dollar signs, spaces, quotes
    val = val.replace('$', '').replace('"', '').replace("'", '').strip()
    if not val or val == '-' or val == '-   ':
        return 0.0
    # Handle parentheses for negative
    negative = False
    if val.startswith('(') and val.endswith(')'):
        negative = True
        val = val[1:-1]
    # Remove commas and spaces
    val = val.replace(',', '').replace(' ', '')
    if not val or val == '-':
        return 0.0
    try:
        result = float(val)
        return -result if negative else result
    except ValueError:
        return None


def normalize_name(name):
    """Normalize municipality name for consistent matching."""
    if not name:
        return None
    name = str(name).strip()
    # Remove trailing asterisks, numbers, and whitespace
    name = re.sub(r'[\*\#]+$', '', name).strip()
    name = re.sub(r'\s+', ' ', name).strip()
    # Remove trailing numbers that aren't part of town names
    name = re.sub(r'\s+\d+$', '', name).strip()
    # Remove "Cooperative" / "Coop" suffixes (school districts, not towns)
    name = re.sub(r'\s+Cooperative\s*\*?$', '', name, flags=re.IGNORECASE).strip()
    name = re.sub(r'\s+Coop\s*\*?$', '', name, flags=re.IGNORECASE).strip()
    # Remove "Regional" suffix
    name = re.sub(r'\s+Regional\s*\*?$', '', name, flags=re.IGNORECASE).strip()
    # Remove common non-town entries
    lower = name.lower()
    if not name or lower in ('', 'state', 'state total', 'state totals',
                              'state ave', 'state average', 'true', 'false',
                              '#ref!', 'nan', 'none', 'profile', 'loc #',
                              'statewide total', 'district', 'total',
                              'entitlement', 'footnote', 'districts',
                              'base adequacy', 'charter schools',
                              'district id', 'district name'):
        return None
    # Reject if it looks like a header/footnote (contains certain words)
    reject_words = ['expenditure', 'footnote', 'school year', 'education aid',
                    'equal opportunity', 'department of', 'tax rate', 'tax assessment',
                    'cover the', 'budget', 'revenue', 'when tax', 'academy',
                    'compass classical', 'village district', 'co-op', 'school district',
                    'fall mountain', 'dresden', 'contoocook', 'exeter region']
    for rw in reject_words:
        if rw in lower:
            return None
    # Reject if name is too long (> 30 chars usually means header text)
    if len(name) > 30:
        return None
    # Apply known fixes
    if name in NAME_FIXES:
        name = NAME_FIXES[name]
    # Title case
    name = name.title()
    # Fix common title-case issues
    name = name.replace("'S ", "'s ")
    return name


def is_municipality_row(row, name_col=0):
    """Check if a CSV row contains municipality data (not headers/totals/blanks)."""
    if not row or len(row) <= name_col:
        return False
    name = str(row[name_col]).strip()
    if not name:
        return False
    name_lower = name.lower()
    skip_patterns = [
        'state total', 'state totals', 'state ave', 'state', 'fy',
        'new hampshire', 'department', 'division', 'bureau', 'pleasant',
        'telephone', 'fax', 'adequacy', 'base cost', 'adm', 'per pupil',
        'replaces', 'october', 'november', 'december', 'january', 'february',
        'march', 'april', 'may', 'june', 'july', 'august', 'september',
        'see footnote', 'k <=', 'per thousand', '#ref!', 'from evals',
        'from eoy', 'true', 'false', 'grant', 'calculation', 'formula',
        'rsa', 'statewide', 'enhanced', 'targeted', 'transition',
        'equitable', 'education', 'cost of', 'information', 'commissioner',
        'estimated', 'municipal', 'loc #', 'loc#', 'district',
    ]
    for pattern in skip_patterns:
        if name_lower.startswith(pattern):
            return False
    # Must start with a letter (municipality name)
    if not re.match(r'^[A-Za-z]', name):
        return False
    return True


def read_csv_rows(filepath):
    """Read CSV file and return all rows as lists."""
    rows = []
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                reader = csv.reader(f)
                rows = list(reader)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    return rows


def read_xlsx_rows(filepath):
    """Read XLSX file and return all rows as lists."""
    if openpyxl is None:
        return []
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(list(row))
    return rows


def get_or_create_muni(cursor, name):
    """Get municipality ID, creating if needed."""
    name = normalize_name(name)
    if not name:
        return None
    cursor.execute("SELECT id FROM municipalities WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO municipalities (name) VALUES (?)", (name,))
    return cursor.lastrowid


def upsert_adequacy(cursor, muni_id, fy, **kwargs):
    """Insert or update adequacy aid record."""
    if muni_id is None:
        return
    cursor.execute("SELECT id FROM adequacy_aid WHERE municipality_id = ? AND fiscal_year = ?",
                   (muni_id, fy))
    existing = cursor.fetchone()
    if existing:
        sets = []
        vals = []
        for k, v in kwargs.items():
            if v is not None:
                sets.append(f"{k} = ?")
                vals.append(v)
        if sets:
            vals.extend([muni_id, fy])
            cursor.execute(f"UPDATE adequacy_aid SET {', '.join(sets)} WHERE municipality_id = ? AND fiscal_year = ?", vals)
    else:
        cols = ['municipality_id', 'fiscal_year'] + list(kwargs.keys())
        vals = [muni_id, fy] + list(kwargs.values())
        placeholders = ', '.join(['?'] * len(vals))
        cursor.execute(f"INSERT INTO adequacy_aid ({', '.join(cols)}) VALUES ({placeholders})", vals)


# ============================================================
# ADEQUACY AID PARSERS - one per format era
# ============================================================

def import_fy04_aid(cursor):
    """FY04: ad_ed_aid_fy04.csv - simple 6-col format."""
    filepath = DATA_DIR / "ad_ed_aid_fy04.csv"
    if not filepath.exists():
        return
    rows = read_csv_rows(filepath)
    print(f"  FY04 aid: {len(rows)} rows")
    count = 0
    for row in rows:
        if len(row) < 6:
            continue
        name = normalize_name(row[0])
        if not name:
            continue
        if not is_municipality_row(row, 0):
            continue
        muni_id = get_or_create_muni(cursor, name)
        total_cost = parse_money(row[3])  # Cost of Adequate Ed + Targeted Aid
        swept = parse_money(row[4])       # SWEPT
        grant = parse_money(row[5])       # Adequate Education Grant & Targeted Aid
        upsert_adequacy(cursor, muni_id, 2004,
                        total_cost_adequate_ed=parse_money(row[1]),
                        swept=swept,
                        total_adequacy_grant=grant,
                        total_state_grant=(grant or 0) + (swept or 0),
                        base_cost_per_pupil=3390.0,
                        swept_rate=4.92)
        count += 1
    print(f"    Imported {count} towns for FY04")


def import_fy06(cursor):
    """FY06: ad_ed_fy06.csv"""
    filepath = DATA_DIR / "ad_ed_fy06.csv"
    if not filepath.exists():
        return
    rows = read_csv_rows(filepath)
    print(f"  FY06: {len(rows)} rows")
    count = 0
    for row in rows:
        if len(row) < 11:
            continue
        name_str = row[0].strip()
        if not name_str or not re.match(r'^[A-Za-z]', name_str):
            continue
        if name_str.lower().startswith(('state', 'fy', 'statewide', 'enhanced', 'ed tax', 'per thousand')):
            continue
        name = normalize_name(name_str)
        if not name:
            continue
        muni_id = get_or_create_muni(cursor, name)
        adm = parse_money(row[1])
        total_formula = parse_money(row[5])   # Total Formula Education Grants
        transition_grant = parse_money(row[7])  # Formula Grant + Transition
        swept = parse_money(row[9])            # Enhanced Ed Tax @ $2.840
        total_state = parse_money(row[10])     # Total State Aid for Education
        # Use total_state as the combined grant (adequacy + SWEPT)
        # The adequacy grant portion is total_state - swept
        adequacy_grant = (total_state or 0) - (swept or 0)
        if adequacy_grant < 0:
            adequacy_grant = 0
        upsert_adequacy(cursor, muni_id, 2006,
                        adm=adm,
                        total_adequacy_grant=adequacy_grant,
                        swept=swept,
                        total_state_grant=total_state,
                        base_cost_per_pupil=3917.0,
                        swept_rate=2.84)
        count += 1
    print(f"    Imported {count} towns for FY06")


def import_fy07(cursor):
    """FY07: ad_ed_aid_fy07.csv"""
    filepath = DATA_DIR / "ad_ed_aid_fy07.csv"
    if not filepath.exists():
        return
    rows = read_csv_rows(filepath)
    print(f"  FY07: {len(rows)} rows")
    count = 0
    for row in rows:
        if len(row) < 5:
            continue
        name_str = row[0].strip()
        if not name_str or not re.match(r'^[A-Za-z]', name_str):
            continue
        if name_str.lower().startswith(('state', 'fy', 'see', 'k <')):
            continue
        name = normalize_name(name_str)
        if not name:
            continue
        muni_id = get_or_create_muni(cursor, name)
        adm = parse_money(row[1])
        grant = parse_money(row[2])   # FY06/FY07 Formula plus Transition Grants
        swept = parse_money(row[4])   # SWEPT at $2.515
        total = (grant or 0) + (swept or 0)
        upsert_adequacy(cursor, muni_id, 2007,
                        adm=adm,
                        total_adequacy_grant=grant,
                        swept=swept,
                        total_state_grant=total,
                        base_cost_per_pupil=3917.0,
                        swept_rate=2.515)
        count += 1
    print(f"    Imported {count} towns for FY07")


def import_fy08(cursor):
    """FY08: ad_ed_fy08.csv"""
    filepath = DATA_DIR / "ad_ed_fy08.csv"
    if not filepath.exists():
        return
    rows = read_csv_rows(filepath)
    print(f"  FY08: {len(rows)} rows")
    count = 0
    for row in rows:
        if len(row) < 8:
            continue
        name_str = row[0].strip()
        if not name_str or not re.match(r'^[A-Za-z]', name_str):
            continue
        if name_str.lower().startswith(('state', 'fy', 'see', 'k <')):
            continue
        name = normalize_name(name_str)
        if not name:
            continue
        muni_id = get_or_create_muni(cursor, name)
        adm = parse_money(row[1])
        grant = parse_money(row[6])   # FY08 HB2 Compromise
        swept = parse_money(row[7])   # Enhanced Educ Tax @$2.240
        total = (grant or 0) + (swept or 0)
        upsert_adequacy(cursor, muni_id, 2008,
                        adm=adm,
                        total_adequacy_grant=grant,
                        swept=swept,
                        total_state_grant=total,
                        base_cost_per_pupil=3917.0,
                        swept_rate=2.24)
        count += 1
    print(f"    Imported {count} towns for FY08")


def import_fy09(cursor):
    """FY09: ad_ed_aid_fy2009.csv"""
    filepath = DATA_DIR / "ad_ed_aid_fy2009.csv"
    if not filepath.exists():
        return
    rows = read_csv_rows(filepath)
    print(f"  FY09: {len(rows)} rows")
    count = 0
    for row in rows:
        if len(row) < 5:
            continue
        name_str = row[0].strip()
        if not name_str or not re.match(r'^[A-Za-z]', name_str):
            continue
        if name_str.lower().startswith(('state', 'fy', 'nh', 'bureau', 'see', 'k <')):
            continue
        name = normalize_name(name_str)
        if not name:
            continue
        muni_id = get_or_create_muni(cursor, name)
        adm = parse_money(row[1])
        grant = parse_money(row[2])   # FY08/FY09 Grants
        swept = parse_money(row[4])   # SWEPT at $2.14
        total = (grant or 0) + (swept or 0)
        upsert_adequacy(cursor, muni_id, 2009,
                        adm=adm,
                        total_adequacy_grant=grant,
                        swept=swept,
                        total_state_grant=total,
                        base_cost_per_pupil=3917.0,
                        swept_rate=2.14)
        count += 1
    print(f"    Imported {count} towns for FY09")


def import_fy10(cursor):
    """FY10: ad_ed_aid_fy2010.csv"""
    filepath = DATA_DIR / "ad_ed_aid_fy2010.csv"
    if not filepath.exists():
        return
    rows = read_csv_rows(filepath)
    print(f"  FY10: {len(rows)} rows")
    count = 0
    for row in rows:
        if len(row) < 11:
            continue
        name_str = row[0].strip()
        if not name_str or not re.match(r'^[A-Za-z]', name_str):
            continue
        if name_str.lower().startswith(('state', 'fy', 'see', 'k <', 'new hampshire',
                                        'commissioner', 'estimated', 'municipal')):
            continue
        name = normalize_name(name_str)
        if not name:
            continue
        muni_id = get_or_create_muni(cursor, name)
        grant = parse_money(row[10])  # FY10 Transition Grant (final)
        swept = parse_money(row[6])   # SWEPT at $2.135
        fiscal_disparity = parse_money(row[5])
        total = (grant or 0) + (swept or 0) if grant else (swept or 0)
        upsert_adequacy(cursor, muni_id, 2010,
                        total_adequacy_grant=grant,
                        swept=swept,
                        fiscal_capacity_aid=fiscal_disparity,
                        total_state_grant=total,
                        base_cost_per_pupil=3450.0,
                        swept_rate=2.135)
        count += 1
    print(f"    Imported {count} towns for FY10")


def import_fy11(cursor):
    """FY11: fy11_adequacy.csv"""
    filepath = DATA_DIR / "fy11_adequacy.csv"
    if not filepath.exists():
        return
    rows = read_csv_rows(filepath)
    print(f"  FY11: {len(rows)} rows")
    count = 0
    for row in rows:
        if len(row) < 11:
            continue
        name_str = row[0].strip()
        if not name_str or not re.match(r'^[A-Za-z]', name_str):
            continue
        if name_str.lower().startswith(('state', 'fy', 'see')):
            continue
        name = normalize_name(name_str)
        if not name:
            continue
        muni_id = get_or_create_muni(cursor, name)
        grant = parse_money(row[10])  # FY11 Transition Grant
        swept = parse_money(row[6])   # SWEPT at $2.19
        total = (grant or 0) + (swept or 0) if grant else (swept or 0)
        upsert_adequacy(cursor, muni_id, 2011,
                        total_adequacy_grant=grant,
                        swept=swept,
                        total_state_grant=total,
                        base_cost_per_pupil=3450.0,
                        swept_rate=2.19)
        count += 1
    print(f"    Imported {count} towns for FY11")


def import_fy12_to_fy21(cursor):
    """FY12-FY21: Wide-format files with detailed breakdowns.
    Files: ad_ed_aid_fy2012.csv through ad_ed_aid_fy2021.csv
    """
    files = {
        2012: "ad_ed_aid_fy2012.csv",
        2013: "ad_ed_aid_fy2013.csv",
        2014: "ad_ed_aid_fy2014_final.csv",
        2015: "ad_ed_aid_fy2015_final.csv",
        2016: "ad_ed_aid_fy2016_final.csv",
        2017: "ad_ed_aid_fy2017_final.csv",
        2018: "ad_ed_aid_fy2018_final.csv",
        2019: "ad_ed_aid_fy2019_final.csv",
        2020: "ad_ed_aid_fy2020_final.csv",
        2021: "ad_ed_aid_fy2021.csv",
    }
    for fy, filename in files.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  FY{fy}: FILE NOT FOUND - {filename}")
            continue
        rows = read_csv_rows(filepath)
        print(f"  FY{fy}: {len(rows)} rows from {filename}")

        # Find the data rows - look for rows where a column contains a municipality name
        # Layout varies: FY12-15 has name at col 6, FY16-21 has name at col 4 or col 1
        count = 0
        for row in rows:
            if len(row) < 15:
                continue

            # Find town name - try multiple columns (varies by year)
            name = None
            name_col = None
            skip_words = {'from', 'true', 'false', 'membership', 'base', 'free',
                         'special', 'english', 'grade', 'home', 'total', 'swept',
                         'preliminary', 'stabilization', 'calculated', 'statewide',
                         'district', 'public', 'school', 'adequacy', 'state'}
            for try_col in [6, 4, 3, 1]:
                if try_col < len(row):
                    candidate = str(row[try_col]).strip()
                    if candidate and re.match(r'^[A-Z][a-z]', candidate):
                        if candidate.lower() not in skip_words:
                            name = candidate
                            name_col = try_col
                            break

            if not name:
                continue
            name = normalize_name(name)
            if not name:
                continue

            muni_id = get_or_create_muni(cursor, name)

            # Column layout for FY12-FY21 (after the name column):
            # ADM, Base Adequacy Aid, F&R ADM, F&R Aid, SPED ADM, ELL ADM,
            # SPED Diff Aid, ELL Diff Aid, Grade 3 Reading ADM, Grade 3 Reading Aid,
            # Total Cost, SWEPT, Prelim Grants, ..., Final Grant
            try:
                base_col = name_col + 1  # First data col after name

                adm = parse_money(row[base_col]) if base_col < len(row) else None
                base_aid = parse_money(row[base_col + 1]) if base_col + 1 < len(row) else None
                fr_adm = parse_money(row[base_col + 2]) if base_col + 2 < len(row) else None
                fr_aid = parse_money(row[base_col + 3]) if base_col + 3 < len(row) else None
                sped_adm = parse_money(row[base_col + 4]) if base_col + 4 < len(row) else None
                ell_adm = parse_money(row[base_col + 5]) if base_col + 5 < len(row) else None
                sped_aid = parse_money(row[base_col + 6]) if base_col + 6 < len(row) else None
                ell_aid = parse_money(row[base_col + 7]) if base_col + 7 < len(row) else None

                # Find total cost and SWEPT - look for large values
                total_cost = None
                swept = None
                final_grant = None

                # For FY18-FY21 there are additional columns (home school)
                if fy >= 2018:
                    # Cols: ...Grade3 ADM, Grade3 Aid, HomeSchool ADM, HomeSchool Aid, Total Cost, SWEPT
                    grade3_adm_col = base_col + 8
                    grade3_aid_col = base_col + 9
                    home_adm_col = base_col + 10
                    home_aid_col = base_col + 11
                    total_cost_col = base_col + 12
                    swept_col = base_col + 13
                    prelim_col = base_col + 14
                    # For FY21: additional F&R%, F&R Additional Aid, Fiscal Capacity columns
                    if fy == 2021:
                        # FY21 has: ...HomeSchool ADM, HomeSchool Aid, Total Cost, SWEPT,
                        # %F&R, F&R Additional Aid, Fiscal Capacity Disparity Aid, Prelim Grant,
                        # FY12 Stab, Stab@100%, Adequacy Grant, Min First Est, 95% Hold Harmless
                        total_cost = parse_money(row[total_cost_col]) if total_cost_col < len(row) else None
                        swept = parse_money(row[swept_col]) if swept_col < len(row) else None
                        # Final grant - look for the adequacy grant column
                        for gc in range(len(row) - 1, base_col + 14, -1):
                            v = parse_money(row[gc])
                            if v and v > 1000:
                                final_grant = v
                                break
                    else:
                        total_cost = parse_money(row[total_cost_col]) if total_cost_col < len(row) else None
                        swept = parse_money(row[swept_col]) if swept_col < len(row) else None
                        # Final grant is typically the last non-empty large value
                        for gc in range(len(row) - 1, swept_col, -1):
                            v = parse_money(row[gc])
                            if v and v > 1000:
                                final_grant = v
                                break
                else:
                    # FY12-FY17: ...Grade3 ADM, Grade3 Aid, Total Cost, SWEPT, Prelim, ..., Final
                    grade3_aid_col = base_col + 9
                    total_cost_col = base_col + 10
                    swept_col = base_col + 11
                    total_cost = parse_money(row[total_cost_col]) if total_cost_col < len(row) else None
                    swept = parse_money(row[swept_col]) if swept_col < len(row) else None
                    # Final grant - last significant value
                    for gc in range(len(row) - 1, swept_col, -1):
                        v = parse_money(row[gc])
                        if v and v > 1000:
                            final_grant = v
                            break

                grade3_aid = parse_money(row[base_col + 9]) if base_col + 9 < len(row) else None

                total_state = ((final_grant or 0) + (swept or 0)) if final_grant else None

                upsert_adequacy(cursor, muni_id, fy,
                                adm=adm,
                                base_adequacy_aid=base_aid,
                                fr_adm=fr_adm,
                                fr_aid=fr_aid,
                                sped_adm=sped_adm,
                                ell_adm=ell_adm,
                                sped_differentiated_aid=sped_aid,
                                ell_aid=ell_aid,
                                grade3_reading_aid=grade3_aid,
                                total_cost_adequate_ed=total_cost,
                                swept=swept,
                                total_adequacy_grant=final_grant,
                                total_state_grant=total_state,
                                base_cost_per_pupil=BASE_COST_PER_PUPIL.get(fy),
                                swept_rate=SWEPT_RATES.get(fy))
                count += 1
            except (IndexError, TypeError) as e:
                continue

        print(f"    Imported {count} towns for FY{fy}")


def import_fy22_to_fy26(cursor):
    """FY22-FY26: New format with extraordinary needs, hold harmless, etc.
    Each year has a different column layout, so we hardcode column positions
    derived from the State Total rows in each file."""

    # Column mappings per fiscal year (absolute column indices)
    # Verified against State Total rows in each file
    col_map = {
        2022: {
            'file': "adequacy-fy-22-muni-summary.csv",
            'name_col': 4,
            'adm': 7,          # Base Adequacy Membership (greater of 2020 & 2021)
            'base_aid': 8,     # Base Adequacy Aid
            'fr_adm': 11,     # F&R Membership (base)
            'fr_aid': 12,     # F&R Differentiated Aid
            'sped_adm': 15,   # SPED Membership (base)
            'sped_aid': 16,   # SPED Differentiated Aid
            'ell_adm': 19,    # ELL Membership (base)
            'ell_aid': 20,    # ELL Differentiated Aid
            'total_cost': 25,  # Total Calculated Cost of Adequate Education
            'swept': 26,       # SWEPT
            'adequacy_grant': 34,  # Adequacy Grant (max of preliminary+stab or 95% HH)
            'total_state': 35,     # Final Grant (Adequacy + SWEPT)
        },
        2023: {
            'file': "adequacy-fy23-muni-estimate-summary.csv",
            'name_col': 1,
            'adm': 2,          # ADM
            'base_aid': 3,     # Base Adequacy Aid
            'fr_adm': 7,      # F&R Membership (base of 3)
            'fr_aid': 10,     # F&R Aid
            'sped_adm': 11,   # SPED Membership
            'sped_aid': 12,   # SPED Aid
            'ell_adm': 13,    # ELL Membership
            'ell_aid': 14,    # ELL Aid
            'total_cost': 17,  # Total Calculated Cost
            'swept': 18,       # SWEPT
            'adequacy_grant': 34,  # Adequacy Grant
            'total_state': 36,     # Final Grant (Adequacy + SWEPT)
        },
        2024: {
            'file': "adequacy-fy-24-muni-summary-4.1.24_0.csv",
            'name_col': 4,
            'adm': 5,          # ADM
            'base_aid': 6,     # Base Adequacy Aid
            'fr_adm': 7,      # F&R ADM
            'fr_aid': 8,      # F&R Aid
            'sped_adm': 9,    # SPED ADM
            'sped_aid': 10,   # SPED Aid
            'ell_adm': 11,    # ELL ADM
            'ell_aid': 12,    # ELL Aid
            'total_cost': 13,  # Total Calculated Cost
            'swept': 14,       # SWEPT
            'adequacy_grant': 23,  # Adequacy Grant
            'total_state': 25,     # Final Total State Grant
        },
        2025: {
            'file': "adequacy-fy-25-muni-summary-4.1.25.csv",
            'name_col': 4,
            'adm': 5,
            'base_aid': 6,
            'fr_adm': 7,
            'fr_aid': 8,
            'sped_adm': 9,
            'sped_aid': 10,
            'ell_adm': 11,
            'ell_aid': 12,
            'total_cost': 15,  # Total Calculated Cost (col 13=home_adm, col 14=home_aid)
            'swept': 16,       # SWEPT
            'adequacy_grant': 27,  # Adequacy Grant
            'total_state': 29,     # Final Total State Grant
        },
        2026: {
            'file': "adequacy-fy-26-muni-summary-estimate.csv",
            'name_col': 4,
            'adm': 5,
            'base_aid': 6,
            'fr_adm': 7,
            'fr_aid': 8,
            'sped_adm': 9,
            'sped_aid': 10,
            'ell_adm': 11,
            'ell_aid': 12,
            'total_cost': 15,  # Total Calculated Cost (col 13=home_adm, col 14=home_aid)
            'swept': 16,       # SWEPT
            'adequacy_grant': 26,  # Adequacy Grant
            'total_state': 28,     # Final Total State Grant
        },
    }

    skip_words = {'true', 'false', 'state', 'total', 'from', 'base',
                 'calculated', 'district', 'public', 'school', 'adequacy',
                 'sfy', 'loc', 'membership', 'statewide', 'loc #',
                 'state total', 'statewide total'}

    for fy, cols in col_map.items():
        filename = cols['file']
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  FY{fy}: FILE NOT FOUND - {filename}")
            continue
        rows = read_csv_rows(filepath)
        print(f"  FY{fy}: {len(rows)} rows from {filename}")

        count = 0
        nc = cols['name_col']
        for row in rows:
            if len(row) < 15:
                continue

            # Get town name from the known column
            candidate = str(row[nc]).strip() if nc < len(row) and row[nc] else ''
            if not candidate or not re.match(r'^[A-Z][a-z]', candidate) or len(candidate) <= 2:
                continue
            if candidate.lower() in skip_words:
                continue

            name = normalize_name(candidate)
            if not name:
                continue

            muni_id = get_or_create_muni(cursor, name)

            try:
                def col(key):
                    idx = cols.get(key)
                    if idx is not None and idx < len(row):
                        return parse_money(row[idx])
                    return None

                upsert_adequacy(cursor, muni_id, fy,
                                adm=col('adm'),
                                base_adequacy_aid=col('base_aid'),
                                fr_adm=col('fr_adm'),
                                fr_aid=col('fr_aid'),
                                sped_adm=col('sped_adm'),
                                sped_differentiated_aid=col('sped_aid'),
                                ell_adm=col('ell_adm'),
                                ell_aid=col('ell_aid'),
                                total_cost_adequate_ed=col('total_cost'),
                                swept=col('swept'),
                                total_adequacy_grant=col('adequacy_grant'),
                                total_state_grant=col('total_state'),
                                base_cost_per_pupil=BASE_COST_PER_PUPIL.get(fy),
                                swept_rate=SWEPT_RATES.get(fy))
                count += 1
            except (IndexError, TypeError) as e:
                continue

        print(f"    Imported {count} towns for FY{fy}")


def import_fy27(cursor):
    """FY27: XLSX files (despite .csv extension). Need to rename first.
    Hardcoded column positions (0-based list indices from XLSX)."""
    filepath = DATA_DIR / "fy-27-adequacy-muni-summary-csv.csv"
    xlsx_path = DATA_DIR / "fy-27-adequacy-muni-summary.xlsx"
    if not filepath.exists() and not xlsx_path.exists():
        print("  FY27: Skipped (file missing)")
        return
    if openpyxl is None:
        print("  FY27: Skipped (openpyxl not installed)")
        return
    # Copy to .xlsx if needed
    if filepath.exists() and not xlsx_path.exists():
        import shutil
        shutil.copy2(filepath, xlsx_path)
    rows = read_xlsx_rows(xlsx_path)
    print(f"  FY27: {len(rows)} rows from XLSX")

    # Column positions (0-based list indices, verified from state total row)
    cols = {
        'name': 4, 'adm': 5, 'base_aid': 6,
        'fr_adm': 7, 'fr_aid': 8,
        'sped_adm': 9, 'sped_aid': 10,
        'ell_adm': 11, 'ell_aid': 12,
        'total_cost': 15, 'swept': 16,
        'adequacy_grant': 25, 'total_state': 27,
    }
    skip_words = {'true', 'false', 'state', 'total', 'from', 'base',
                 'calculated', 'district', 'public', 'school', 'adequacy',
                 'sfy', 'loc', 'membership', 'statewide', 'loc #',
                 'state total'}

    count = 0
    for row in rows:
        if len(row) < 15:
            continue
        candidate = str(row[cols['name']]).strip() if cols['name'] < len(row) and row[cols['name']] else ''
        if not candidate or not re.match(r'^[A-Z][a-z]', candidate) or len(candidate) <= 2:
            continue
        if candidate.lower() in skip_words:
            continue

        name = normalize_name(candidate)
        if not name:
            continue
        muni_id = get_or_create_muni(cursor, name)
        try:
            def col(key):
                idx = cols.get(key)
                if idx is not None and idx < len(row):
                    return parse_money(row[idx])
                return None

            upsert_adequacy(cursor, muni_id, 2027,
                            adm=col('adm'),
                            base_adequacy_aid=col('base_aid'),
                            fr_adm=col('fr_adm'),
                            fr_aid=col('fr_aid'),
                            sped_adm=col('sped_adm'),
                            sped_differentiated_aid=col('sped_aid'),
                            ell_adm=col('ell_adm'),
                            ell_aid=col('ell_aid'),
                            total_cost_adequate_ed=col('total_cost'),
                            swept=col('swept'),
                            total_adequacy_grant=col('adequacy_grant'),
                            total_state_grant=col('total_state'),
                            base_cost_per_pupil=BASE_COST_PER_PUPIL.get(2027),
                            swept_rate=SWEPT_RATES.get(2027))
            count += 1
        except (IndexError, TypeError):
            continue
    print(f"    Imported {count} towns for FY27")


# ============================================================
# SPECIAL EDUCATION AID PARSERS
# ============================================================

def import_sped_catastrophic(cursor):
    """Import catastrophic special education aid files."""
    files = {
        2008: "catastrophic07_08.csv",
        2009: "catastrophic08_09.csv",
        2010: "catastrophic09_10.csv",
        2011: "catastrophic10_11.csv",
        2012: "catastrophic11_12.csv",
        2013: "catastrophic12_13.csv",
        2014: "catastrophic13_14.csv",
        2015: "catastrophic14_15.csv",
        2016: "catastrophic15_16.csv",
        2017: "catastrophic16-17.csv",
        2018: "catastrophic17-18.csv",
        2019: "catastrophic18-19.csv",
    }
    for fy, filename in files.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            continue
        rows = read_csv_rows(filepath)
        print(f"  SPED Catastrophic FY{fy}: {len(rows)} rows")
        count = 0
        for row in rows:
            if len(row) < 7:
                continue
            name_str = str(row[0]).strip()
            if not name_str or not re.match(r'^[A-Za-z]', name_str):
                continue
            if name_str.lower().startswith(('state', 'new hampshire', 'department', 'division',
                                            'bureau', 'telephone', 'fy', 'catastrophic',
                                            '101 pleasant', 'expenditures', '3 1/2')):
                continue
            name = normalize_name(name_str)
            if not name:
                continue
            muni_id = get_or_create_muni(cursor, name)
            try:
                entitlement = parse_money(row[6]) if len(row) > 6 else None
                cursor.execute("""INSERT OR REPLACE INTO sped_aid
                    (municipality_id, fiscal_year, entitlement)
                    VALUES (?, ?, ?)""", (muni_id, fy, entitlement))
                count += 1
            except (IndexError, TypeError):
                continue
        print(f"    Imported {count} districts for SPED catastrophic FY{fy}")


def import_sped_aid_detailed(cursor):
    """Import detailed SPED aid files (FY20+)."""
    files = {
        2020: "sped-aid19-20.csv",
        2021: "sped-aid-20-21.csv",
        2022: "fy22-school-year-20-21-sped-aid-final-without-students-report.csv",
        2023: "fy-23-school-year-2022-2023-sped-aid-final-no-students.csv",
        2024: "fy24-for-2022-2023.csv",
        2025: "fy-25-2023-2024-sped-aid-csv.csv",
        2026: "fy26-special-education-aid-amounts-website.csv",
    }
    for fy, filename in files.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            continue
        rows = read_csv_rows(filepath)
        print(f"  SPED Aid FY{fy}: {len(rows)} rows")
        count = 0
        for row in rows:
            if len(row) < 5:
                continue
            # Find district name - try col 1, then col 0
            name_str = None
            for try_col in [1, 0]:
                candidate = str(row[try_col]).strip() if try_col < len(row) and row[try_col] else ''
                if candidate and re.match(r'^[A-Za-z]', candidate) and len(candidate) > 2:
                    if candidate.lower() not in ('state', 'totals', 'state totals',
                                                  'district', 'district of liability',
                                                  'fy', 'sum', 'district id'):
                        name_str = candidate
                        break
            if not name_str:
                continue
            name = normalize_name(name_str)
            if not name:
                continue
            muni_id = get_or_create_muni(cursor, name)
            try:
                # Find the entitlement/appropriation (last significant column)
                entitlement = None
                for gc in range(len(row) - 1, 2, -1):
                    v = parse_money(row[gc])
                    if v and v > 100:
                        entitlement = v
                        break
                cursor.execute("""INSERT OR REPLACE INTO sped_aid
                    (municipality_id, fiscal_year, entitlement)
                    VALUES (?, ?, ?)""", (muni_id, fy, entitlement))
                count += 1
            except (IndexError, TypeError):
                continue
        print(f"    Imported {count} districts for SPED FY{fy}")


# ============================================================
# BUILDING AID PARSERS
# ============================================================

def import_building_aid(cursor):
    """Import school building aid files."""
    files_csv = {
        2007: "build_dist06_07.csv",
        2008: "build_dist07_08.csv",
        2009: "build_dist08_09.csv",
    }
    for fy, filename in files_csv.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            continue
        rows = read_csv_rows(filepath)
        print(f"  Building Aid FY{fy}: {len(rows)} rows")
        count = 0
        for row in rows:
            if len(row) < 5:
                continue
            name_str = str(row[1]).strip() if len(row) > 1 else ''
            if not name_str or not re.match(r'^[A-Za-z]', name_str):
                continue
            if name_str.lower().startswith(('state', 'new hampshire', 'division', 'office',
                                            'building', 'district', 'fy')):
                continue
            name = normalize_name(name_str)
            if not name:
                continue
            muni_id = get_or_create_muni(cursor, name)
            try:
                total = parse_money(row[4]) if len(row) > 4 else parse_money(row[3])
                cursor.execute("""INSERT OR REPLACE INTO building_aid
                    (municipality_id, fiscal_year, total_entitlement)
                    VALUES (?, ?, ?)""", (muni_id, fy, total))
                count += 1
            except (IndexError, TypeError):
                continue
        print(f"    Imported {count} districts for building aid FY{fy}")

    # XLSX building aid files
    xlsx_files = {
        # These cover FY10-FY25 in two files
    }
    for fname in ["build-dist-10-24-revised-7-1-25.csv", "build-dist-25-41-revised-7-1-25.csv"]:
        filepath = DATA_DIR / fname
        if not filepath.exists():
            continue
        rows = read_csv_rows(filepath)
        print(f"  Building Aid multi-year: {len(rows)} rows from {fname}")
        # These files have multiple FY columns - parse header to find years
        if len(rows) < 2:
            continue
        # Find year columns from header
        header = rows[0] if rows else []
        year_cols = {}
        for i, val in enumerate(header):
            val_str = str(val).strip()
            match = re.search(r'(?:FY|fy)\s*(\d{2,4})', val_str)
            if match:
                yr = int(match.group(1))
                if yr < 100:
                    yr += 2000
                year_cols[yr] = i

        count = 0
        for row in rows[1:]:
            if len(row) < 3:
                continue
            name_str = str(row[0]).strip() if row[0] else ''
            if not name_str or not re.match(r'^[A-Za-z]', name_str):
                # Try col 1
                name_str = str(row[1]).strip() if len(row) > 1 and row[1] else ''
            if not name_str or not re.match(r'^[A-Za-z]', name_str):
                continue
            if name_str.lower().startswith(('state', 'district', 'building', 'fy', 'total')):
                continue
            name = normalize_name(name_str)
            if not name:
                continue
            muni_id = get_or_create_muni(cursor, name)
            for yr, col in year_cols.items():
                if col < len(row):
                    val = parse_money(row[col])
                    if val and val > 0:
                        try:
                            cursor.execute("""INSERT OR REPLACE INTO building_aid
                                (municipality_id, fiscal_year, total_entitlement)
                                VALUES (?, ?, ?)""", (muni_id, yr, val))
                            count += 1
                        except:
                            pass
        print(f"    Imported {count} records from {fname}")


# ============================================================
# CHARTER SCHOOL AID PARSERS
# ============================================================

def import_charter_school_aid(cursor):
    """Import charter school aid files."""
    # Simple per-pupil format files
    simple_files = [
        ("charter_school06_07.csv", 2007),
        ("charter_school07_08.csv", 2008),
        ("charter_school08_09.csv", 2009),
        ("charter_school_aid_09-10.csv", 2010),
        ("charter_school_aid_10-11.csv", 2011),
        ("charter_school_aid_11-12.csv", 2012),
        ("charter_school_aid12_13.csv", 2013),
        ("charter_school_aid13_14.csv", 2014),
        ("charter_school_aid14_15.csv", 2015),
        ("charter_school_aid15_16.csv", 2016),
        ("charter_school_aid16_17.csv", 2017),
        ("charter_school_aid17-18.csv", 2018),
        ("charter-school-aid-18-19.csv", 2019),
        ("charter-school-aid-19-2020.csv", 2020),
        ("charter-school-aid-20-2021.csv", 2021),
        ("charter-school-aid-fy-22.csv", 2022),
        ("charter-school-aid-per-pupil-fy-23-for-web.csv", 2023),
        ("charter-school-aid-per-pupil-fy-24-for-web.csv", 2024),
    ]

    for filename, fy in simple_files:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            continue
        rows = read_csv_rows(filepath)
        print(f"  Charter FY{fy}: {len(rows)} rows")
        count = 0

        # Find state total row or compute total
        total_aid = 0
        for row in rows:
            if len(row) < 3:
                continue
            # Look for school names and their aid amounts
            for col in range(len(row)):
                val = str(row[col]).strip() if row[col] else ''
                if 'state total' in val.lower() or 'state' == val.lower().strip():
                    # Find the total aid value
                    for tc in range(col + 1, len(row)):
                        v = parse_money(row[tc])
                        if v and v > 10000:
                            total_aid = max(total_aid, v)
                            break

        # Store as a single charter school entry for now
        if total_aid > 0:
            try:
                cursor.execute("""INSERT OR REPLACE INTO charter_school_aid
                    (school_name, fiscal_year, total_aid)
                    VALUES (?, ?, ?)""", ("All Charter Schools", fy, total_aid))
                count = 1
            except:
                pass
        print(f"    Imported charter total for FY{fy}: ${total_aid:,.0f}" if total_aid else f"    No total found for FY{fy}")


# ============================================================
# CTE TUITION & TRANSPORTATION PARSERS
# ============================================================

def import_cte_aid(cursor):
    """Import CTE tuition and transportation files."""
    files = [
        ("cte_tnt_06_07.csv", 2007),
        ("cte_tnt_08_09.csv", 2008),
        ("cte_tnt_09_10.csv", 2010),
        ("cte_tnt_11_12.csv", 2012),
        ("cte_tnt_12_13.csv", 2013),
        ("cte_tnt_13_14.csv", 2014),
        ("cte_tnt_14_15.csv", 2015),
        ("cte_tnt_15_16.csv", 2016),
        ("cte_tnt_16_17.csv", 2017),
        ("cte_tnt_17_18.csv", 2018),
    ]
    for filename, fy in files:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            continue
        rows = read_csv_rows(filepath)
        print(f"  CTE FY{fy}: {len(rows)} rows")
        count = 0
        for row in rows:
            if len(row) < 4:
                continue
            name_str = str(row[0]).strip()
            if not name_str or not re.match(r'^[A-Za-z]', name_str):
                continue
            if name_str.lower().startswith(('state', 'new hampshire', 'department', 'division',
                                            'bureau', 'district', 'cte', '200')):
                continue
            name = normalize_name(name_str)
            if not name:
                continue
            muni_id = get_or_create_muni(cursor, name)
            try:
                tuition = parse_money(row[1])
                transport = parse_money(row[2])
                total = parse_money(row[3])
                cursor.execute("""INSERT OR REPLACE INTO cte_aid
                    (municipality_id, fiscal_year, tuition_payment, transportation_payment, total_payment)
                    VALUES (?, ?, ?, ?, ?)""", (muni_id, fy, tuition, transport, total))
                count += 1
            except (IndexError, TypeError):
                continue
        print(f"    Imported {count} districts for CTE FY{fy}")


# ============================================================
# KINDERGARTEN AID
# ============================================================

def import_kindergarten_aid(cursor):
    """Import kindergarten aid file."""
    filepath = DATA_DIR / "kindergarten-aid.csv"
    if not filepath.exists():
        return
    rows = read_csv_rows(filepath)
    print(f"  Kindergarten Aid: {len(rows)} rows")
    count = 0
    for row in rows:
        if len(row) < 7:
            continue
        # Town name is in col 4, ADM in col 5, aid in col 6
        name_str = str(row[4]).strip() if row[4] else ''
        if not name_str or not re.match(r'^[A-Za-z]', name_str):
            continue
        if name_str.lower().startswith(('state', 'municipal', 'office', 'fy', 'division',
                                        'new hampshire', 'data', 'based')):
            continue
        name = normalize_name(name_str)
        if not name:
            continue
        muni_id = get_or_create_muni(cursor, name)
        try:
            adm = parse_money(row[5])
            aid = parse_money(row[6])
            cursor.execute("""INSERT OR REPLACE INTO kindergarten_aid
                (municipality_id, fiscal_year, adm, per_pupil_rate, total_aid)
                VALUES (?, ?, ?, ?, ?)""", (muni_id, 2019, adm, 1100.0, aid))
            count += 1
        except (IndexError, TypeError):
            continue
    print(f"    Imported {count} towns for kindergarten aid")


# ============================================================
# STATEWIDE TOTALS COMPUTATION
# ============================================================

def compute_statewide_totals(cursor):
    """Compute statewide totals from individual town records."""
    print("\nComputing statewide totals...")

    cursor.execute("SELECT DISTINCT fiscal_year FROM adequacy_aid ORDER BY fiscal_year")
    years = [r[0] for r in cursor.fetchall()]

    for fy in years:
        # Adequacy totals
        cursor.execute("""
            SELECT
                SUM(total_adequacy_grant),
                SUM(adm),
                SUM(fr_adm),
                SUM(total_state_grant)
            FROM adequacy_aid WHERE fiscal_year = ?
        """, (fy,))
        row = cursor.fetchone()
        total_adequacy = row[0] or 0
        total_adm = row[1] or 0
        total_fr_adm = row[2] or 0
        total_state = row[3] or 0

        # SPED totals
        cursor.execute("SELECT SUM(entitlement) FROM sped_aid WHERE fiscal_year = ?", (fy,))
        total_sped = (cursor.fetchone()[0] or 0)

        # Building aid totals
        cursor.execute("SELECT SUM(total_entitlement) FROM building_aid WHERE fiscal_year = ?", (fy,))
        total_building = (cursor.fetchone()[0] or 0)

        # Charter school totals
        cursor.execute("SELECT SUM(total_aid) FROM charter_school_aid WHERE fiscal_year = ?", (fy,))
        total_charter = (cursor.fetchone()[0] or 0)

        # CTE totals
        cursor.execute("SELECT SUM(total_payment) FROM cte_aid WHERE fiscal_year = ?", (fy,))
        total_cte = (cursor.fetchone()[0] or 0)

        # Kindergarten totals
        cursor.execute("SELECT SUM(total_aid) FROM kindergarten_aid WHERE fiscal_year = ?", (fy,))
        total_kinder = (cursor.fetchone()[0] or 0)

        total_all = total_adequacy + total_sped + total_building + total_charter + total_cte + total_kinder
        aid_per_pupil = total_all / total_adm if total_adm > 0 else 0

        cursor.execute("""INSERT OR REPLACE INTO statewide_totals
            (fiscal_year, total_adequacy_aid, total_sped_aid, total_building_aid,
             total_charter_aid, total_cte_aid, total_kindergarten_aid,
             total_all_education_aid, base_cost_per_pupil, swept_rate,
             total_adm, total_fr_adm, aid_per_pupil)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fy, total_adequacy, total_sped, total_building,
             total_charter, total_cte, total_kinder,
             total_all, BASE_COST_PER_PUPIL.get(fy), SWEPT_RATES.get(fy),
             total_adm, total_fr_adm, aid_per_pupil))

        print(f"  FY{fy}: Total Adequacy=${total_adequacy:,.0f}  ADM={total_adm:,.0f}  Per Pupil=${aid_per_pupil:,.0f}")


# ============================================================
# MAIN
# ============================================================

def create_tables(cursor):
    """Create all database tables."""
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS municipalities (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            loc_id INTEGER,
            county TEXT
        );

        CREATE TABLE IF NOT EXISTS adequacy_aid (
            id INTEGER PRIMARY KEY,
            municipality_id INTEGER REFERENCES municipalities(id),
            fiscal_year INTEGER NOT NULL,
            adm REAL,
            base_adequacy_aid REAL,
            fr_aid REAL,
            sped_differentiated_aid REAL,
            ell_aid REAL,
            home_ed_aid REAL,
            grade3_reading_aid REAL,
            total_cost_adequate_ed REAL,
            swept REAL,
            extraordinary_needs_grant REAL,
            hold_harmless_grant REAL,
            fiscal_capacity_aid REAL,
            stabilization_grant REAL,
            total_adequacy_grant REAL,
            total_state_grant REAL,
            base_cost_per_pupil REAL,
            swept_rate REAL,
            fr_adm REAL,
            sped_adm REAL,
            ell_adm REAL,
            UNIQUE(municipality_id, fiscal_year)
        );

        CREATE TABLE IF NOT EXISTS sped_aid (
            id INTEGER PRIMARY KEY,
            municipality_id INTEGER REFERENCES municipalities(id),
            fiscal_year INTEGER NOT NULL,
            num_students INTEGER,
            district_liability REAL,
            cost_3_5_to_10x REAL,
            num_students_over_10x INTEGER,
            cost_over_10x REAL,
            total_district_cost REAL,
            entitlement REAL,
            appropriation REAL,
            UNIQUE(municipality_id, fiscal_year)
        );

        CREATE TABLE IF NOT EXISTS building_aid (
            id INTEGER PRIMARY KEY,
            municipality_id INTEGER REFERENCES municipalities(id),
            fiscal_year INTEGER NOT NULL,
            current_year_aid REAL,
            prior_year_shortfall REAL,
            total_entitlement REAL,
            UNIQUE(municipality_id, fiscal_year)
        );

        CREATE TABLE IF NOT EXISTS charter_school_aid (
            id INTEGER PRIMARY KEY,
            school_name TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            adm REAL,
            per_pupil_rate REAL,
            total_aid REAL,
            fr_aid REAL,
            sped_aid REAL,
            ell_aid REAL,
            UNIQUE(school_name, fiscal_year)
        );

        CREATE TABLE IF NOT EXISTS cte_aid (
            id INTEGER PRIMARY KEY,
            municipality_id INTEGER REFERENCES municipalities(id),
            fiscal_year INTEGER NOT NULL,
            tuition_payment REAL,
            transportation_payment REAL,
            total_payment REAL,
            UNIQUE(municipality_id, fiscal_year)
        );

        CREATE TABLE IF NOT EXISTS kindergarten_aid (
            id INTEGER PRIMARY KEY,
            municipality_id INTEGER REFERENCES municipalities(id),
            fiscal_year INTEGER NOT NULL,
            adm REAL,
            per_pupil_rate REAL,
            total_aid REAL,
            UNIQUE(municipality_id, fiscal_year)
        );

        CREATE TABLE IF NOT EXISTS statewide_totals (
            fiscal_year INTEGER PRIMARY KEY,
            total_adequacy_aid REAL,
            total_sped_aid REAL,
            total_building_aid REAL,
            total_charter_aid REAL,
            total_cte_aid REAL,
            total_kindergarten_aid REAL,
            total_all_education_aid REAL,
            base_cost_per_pupil REAL,
            swept_rate REAL,
            total_adm REAL,
            total_fr_adm REAL,
            aid_per_pupil REAL
        );

        CREATE INDEX IF NOT EXISTS idx_adequacy_muni_fy ON adequacy_aid(municipality_id, fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_adequacy_fy ON adequacy_aid(fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_sped_muni_fy ON sped_aid(municipality_id, fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_building_muni_fy ON building_aid(municipality_id, fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_cte_muni_fy ON cte_aid(municipality_id, fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_muni_name ON municipalities(name);
    """)


def main():
    """Main import pipeline."""
    print(f"NH Education Aid Data Import")
    print(f"Database: {DB_PATH}")
    print(f"Data dir: {DATA_DIR}")
    print("=" * 60)

    # Remove existing DB for clean import
    if DB_PATH.exists():
        os.remove(DB_PATH)
        print("Removed existing database")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")

    create_tables(cursor)
    conn.commit()

    print("\n--- Importing Adequacy Aid ---")
    import_fy04_aid(cursor)
    conn.commit()
    import_fy06(cursor)
    conn.commit()
    import_fy07(cursor)
    conn.commit()
    import_fy08(cursor)
    conn.commit()
    import_fy09(cursor)
    conn.commit()
    import_fy10(cursor)
    conn.commit()
    import_fy11(cursor)
    conn.commit()
    import_fy12_to_fy21(cursor)
    conn.commit()
    import_fy22_to_fy26(cursor)
    conn.commit()
    import_fy27(cursor)
    conn.commit()

    print("\n--- Importing Special Education Aid ---")
    import_sped_catastrophic(cursor)
    conn.commit()
    import_sped_aid_detailed(cursor)
    conn.commit()

    print("\n--- Importing Building Aid ---")
    import_building_aid(cursor)
    conn.commit()

    print("\n--- Importing Charter School Aid ---")
    import_charter_school_aid(cursor)
    conn.commit()

    print("\n--- Importing CTE Aid ---")
    import_cte_aid(cursor)
    conn.commit()

    print("\n--- Importing Kindergarten Aid ---")
    import_kindergarten_aid(cursor)
    conn.commit()

    print("\n--- Computing Statewide Totals ---")
    compute_statewide_totals(cursor)
    conn.commit()

    # Summary
    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    cursor.execute("SELECT COUNT(*) FROM municipalities")
    print(f"  Municipalities: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM adequacy_aid")
    print(f"  Adequacy aid records: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(DISTINCT fiscal_year) FROM adequacy_aid")
    print(f"  Fiscal years with adequacy data: {cursor.fetchone()[0]}")
    cursor.execute("SELECT MIN(fiscal_year), MAX(fiscal_year) FROM adequacy_aid")
    min_fy, max_fy = cursor.fetchone()
    print(f"  Year range: FY{min_fy} - FY{max_fy}")
    cursor.execute("SELECT COUNT(*) FROM sped_aid")
    print(f"  SPED aid records: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM building_aid")
    print(f"  Building aid records: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM charter_school_aid")
    print(f"  Charter school aid records: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM cte_aid")
    print(f"  CTE aid records: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM kindergarten_aid")
    print(f"  Kindergarten aid records: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM statewide_totals")
    print(f"  Statewide total years: {cursor.fetchone()[0]}")

    conn.close()
    print(f"\nDone! Database saved to {DB_PATH}")


if __name__ == "__main__":
    main()
