"""Field structure of the SF4 workbook (sheet 'Public Schools', row 9 = one school).

Column letters come from the workbook: every level has M, F, T columns; the T column and all
aggregate columns are formulas in the workbook and are calculated in code here.
"""
from collections import OrderedDict

# (key, workbook label, section, first column letter of the M/F/T triple)
LEVELS = [
    ("kinder", "Kinder", "ES", "F"),
    ("g1", "Grade 1", "ES", "I"),
    ("g2", "Grade 2", "ES", "L"),
    ("g3", "Grade 3", "ES", "O"),
    ("g4", "Grade 4", "ES", "R"),
    ("g5", "Grade 5", "ES", "U"),
    ("g6", "Grade 6", "ES", "X"),
    ("sned_es", "SNED (Non-Graded ES)", "ES", "AA"),
    ("g7", "Grade 7", "JHS", "AG"),
    ("g8", "Grade 8", "JHS", "AJ"),
    ("g9", "Grade 9", "JHS", "AM"),
    ("g10", "Grade 10", "JHS", "AP"),
    ("sned_jhs", "SNED (Non-Graded ES)", "JHS", "AS"),     # label as printed in the workbook
    ("g11_acad", "Grade 11 ACAD", "SHS", "AY"),
    ("g11_tvl", "Grade 11 TVL", "SHS", "BB"),
    ("g11_sports", "Grade 11 SPORTS", "SHS", "BE"),
    ("g12_acad", "Grade 12 ACAD", "SHS", "BK"),
    ("g12_tvl", "Grade 12 TVL", "SHS", "BN"),
    ("g12_sports", "Grade 12 SPORTS", "SHS", "BQ"),
]
LEVEL_KEYS = [l[0] for l in LEVELS]
LEVEL_LABEL = {l[0]: l[1] for l in LEVELS}
SECTION_TITLES = OrderedDict([("ES", "Elementary School"), ("JHS", "Junior High School"), ("SHS", "Senior High School")])

# Aggregates, in workbook column order, each defined by what it sums.
AGGREGATES = OrderedDict([
    ("es", ("ELEMENTARY TOTAL", ["kinder", "g1", "g2", "g3", "g4", "g5", "g6", "sned_es"], "AD")),
    ("jhs", ("TOTAL JHS", ["g7", "g8", "g9", "g10", "sned_jhs"], "AV")),
    ("g11", ("TOTAL GRADE 11", ["g11_acad", "g11_tvl", "g11_sports"], "BH")),
    ("g12", ("TOTAL GRADE 12", ["g12_acad", "g12_tvl", "g12_sports"], "BT")),
    ("shs", ("TOTAL SENIOR HIGH SCHOOL", ["g11_acad", "g11_tvl", "g11_sports", "g12_acad", "g12_tvl", "g12_sports"], "BW")),
    ("k12", ("K-12 GRAND TOTAL", LEVEL_KEYS, "BZ")),
])
AGGREGATE_LABEL = {k: v[0] for k, v in AGGREGATES.items()}

# Workbook column order for exports: level triples with aggregates after their section.
EXPORT_ORDER = (
    [("level", k) for k in LEVEL_KEYS[:8]] + [("agg", "es")] +
    [("level", k) for k in LEVEL_KEYS[8:13]] + [("agg", "jhs")] +
    [("level", k) for k in LEVEL_KEYS[13:16]] + [("agg", "g11")] +
    [("level", k) for k in LEVEL_KEYS[16:19]] + [("agg", "g12")] +
    [("agg", "shs"), ("agg", "k12")]
)
