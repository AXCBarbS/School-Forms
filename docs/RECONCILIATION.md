# Excel-to-database reconciliation

Source: `Consolidated_2026-2027_SF4.xlsx`, sheet "Public Schools" (opened read-only, never modified).
Command: `python manage.py import_master <file> --with-enrollment --reconcile`

## Master list

| Item | Workbook | Database after import |
|---|---|---|
| Districts | 14 | 14 |
| Schools (unique DepEd IDs) | 430 | 430 |
| Duplicate school IDs | 0 | – |
| Sector values | all "Public" | all "Public" |

Schools per district: Buguias 50, Mankayan 45, Bokod 42, Tuba 39, Bakun 33, La Trinidad 31, Kapangan 30, Atok 27,
Kibungan 27, Kabayan 25, Itogon I 24, Itogon II 22, Tublay 21, Sablan 14 (= 430). Each count equals the number of
school sheets in the corresponding district workbook.

Re-running the import is idempotent (second run: 0 created, 430 unchanged).

## Enrollment figures (K-12 grand total, male + female)

| District | Database (calculated) | Workbook (saved) | Result |
|---|---:|---:|---|
| Atok | 3,368 | 3,367 | differs by 1 (see below) |
| Bakun | 2,522 | 2,522 | match |
| Bokod | 3,222 | 3,222 | match |
| Buguias | 9,952 | 9,952 | match |
| Itogon I | 6,023 | 6,023 | match |
| Itogon II | 4,188 | 4,188 | match |
| Kabayan | 3,066 | 3,066 | match |
| Kapangan | 3,861 | 3,824 | differs by 37 (see below) |
| Kibungan | 3,432 | 3,432 | match |
| La Trinidad | 18,497 | 18,497 | match |
| Mankayan | 8,303 | 8,303 | match |
| Sablan | 1,492 | 1,492 | match |
| Tuba | 7,814 | 7,814 | match |
| Tublay | 4,242 | 4,242 | match |

427 of 430 schools reproduce every saved total in the workbook exactly. The three exceptions are typed-over or
inconsistent totals that are already wrong in the workbook; the portal calculates from the male/female counts:

1. **Cagui-ing Integrated School (Atok), Grade 8 total** – workbook has a typed 33; 22 + 12 = 34.
   Effect: JHS total and K-12 total +1.
2. **Kapangan National High School, Grade 11 total** – the workbook total cell for Grade 12 ACAD holds a typed 0 although
   11 + 26 = 37. Effect: Grade 12, Senior High and K-12 totals +37.
3. **Twin Peaks NHS (Tuba), Grade 11 male total** – workbook has a typed 63; 22 + 40 = 62. Effect: male Senior High
   and male K-12 totals −1 (the district total is unchanged because the district row sums the underlying columns).

Import warnings (1): Twin Peaks NHS Grade 11 SPORTS Male contains whitespace text instead of a number; treated as blank.
