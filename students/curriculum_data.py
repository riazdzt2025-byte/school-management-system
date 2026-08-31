"""
Reference data for Bangladesh's national curriculum, used to auto-populate
SubjectRequirement rows for a given Institution + Class (+ Group).

This is a practical starting point, not a legal document — boards and
institutions vary slightly and syllabi change over time. Every row created
from this data can still be edited or deleted afterwards from the Subject
Assignments page; nothing here is locked.

Layout:
    SUBJECTS            -- master list of (code, name, full_marks, category)
                           used to get_or_create Subject rows on demand.
    PRIMARY_CLASSES     -- classes with compulsory-only subjects, no groups.
    JUNIOR_CLASSES      -- classes with compulsory-only subjects, no groups.
    SSC_CLASSES / SSC_COMMON / SSC_GROUPS       -- class 9-10, group-wise.
    HSC_CLASSES / HSC_COMMON / HSC_GROUPS       -- class 11-12, group-wise.
    VOCATIONAL_CLASSES / VOCATIONAL_COMMON / VOCATIONAL_GROUPS -- SSC(Voc).
"""

# ---- Master subject list ----------------------------------------------
# (code, name, full_marks, category)
SUBJECTS = [
    # Compulsory / core
    ('BAN1', 'Bangla 1st Paper', 100, 'COMPULSORY'),
    ('BAN2', 'Bangla 2nd Paper', 100, 'COMPULSORY'),
    ('BAN', 'Bangla', 100, 'COMPULSORY'),
    ('ENG1', 'English 1st Paper', 100, 'COMPULSORY'),
    ('ENG2', 'English 2nd Paper', 100, 'COMPULSORY'),
    ('ENG', 'English', 100, 'COMPULSORY'),
    ('MATH', 'General Mathematics', 100, 'COMPULSORY'),
    ('ICT', 'Information & Communication Technology', 50, 'COMPULSORY'),
    ('BGS', 'Bangladesh & Global Studies', 100, 'COMPULSORY'),
    ('SCI-GEN', 'General Science', 100, 'COMPULSORY'),
    ('CAREER', 'Career Education', 50, 'COMPULSORY'),
    ('HPE', 'Health & Physical Education', 50, 'COMPULSORY'),
    ('ART', 'Art & Culture', 50, 'COMPULSORY'),

    # Optional / group subjects (SSC & HSC Science/Business/Humanities)
    ('PHY', 'Physics', 100, 'OPTIONAL'),
    ('CHEM', 'Chemistry', 100, 'OPTIONAL'),
    ('BIO', 'Biology', 100, 'OPTIONAL'),
    ('HMATH', 'Higher Mathematics', 100, 'OPTIONAL'),
    ('AGRI', 'Agriculture Studies', 100, 'OPTIONAL'),
    ('ACC', 'Accounting', 100, 'OPTIONAL'),
    ('BOM', 'Business Organization & Management', 100, 'OPTIONAL'),
    ('FIN', 'Finance, Banking & Insurance', 100, 'OPTIONAL'),
    ('ECO', 'Economics', 100, 'OPTIONAL'),
    ('CIVICS', 'Civics & Good Governance', 100, 'OPTIONAL'),
    ('HISTORY', 'History of Bangladesh & World Civilization', 100, 'OPTIONAL'),
    ('GEO', 'Geography & Environment', 100, 'OPTIONAL'),
    ('LOGIC', 'Logic', 100, 'OPTIONAL'),
    ('SOC', 'Sociology', 100, 'OPTIONAL'),
    ('PSY', 'Psychology', 100, 'OPTIONAL'),
    ('STAT', 'Statistics', 100, 'OPTIONAL'),
    ('PMS', 'Production Management & Marketing', 100, 'OPTIONAL'),
    ('SOCWORK', 'Social Work', 100, 'OPTIONAL'),
    ('ISLHIST', 'Islamic History & Culture', 100, 'OPTIONAL'),

    # Religion (conditional — one auto-added per student's religion)
    ('ISLAM', 'Islam & Moral Education', 100, 'RELIGION'),
    ('HINDU', 'Hindu Religion & Moral Education', 100, 'RELIGION'),
    ('CHRIS', 'Christian Religion & Moral Education', 100, 'RELIGION'),
    ('BUDDHIST', 'Buddhist Religion & Moral Education', 100, 'RELIGION'),

    # Vocational trades (SSC Vocational)
    ('DCS', 'Computer & Information Technology (Vocational)', 100, 'VOCATIONAL'),
    ('DEL', 'Electrical Works & Services (Vocational)', 100, 'VOCATIONAL'),
    ('DCV', 'Civil Construction & Maintenance (Vocational)', 100, 'VOCATIONAL'),

    # 4th subject variants
    ('ENG3', 'General Science (4th Subject)', 100, 'FOURTH'),
    ('MATH4', 'Higher Mathematics (4th Subject)', 100, 'FOURTH'),
    ('AGRI4', 'Agriculture Studies (4th Subject)', 100, 'FOURTH'),
    ('STAT4', 'Statistics (4th Subject)', 100, 'FOURTH'),
]

# ---- Primary (no groups) -----------------------------------------------
PRIMARY_CLASSES = ['Shishu', '1', '2', '3', '4', '5']
PRIMARY_COMMON = [
    ('BAN', 'MANDATORY', '', ''),
    ('ENG', 'MANDATORY', '', ''),
    ('MATH', 'MANDATORY', '', ''),
    ('BGS', 'MANDATORY', '', ''),
    ('SCI-GEN', 'MANDATORY', '', ''),
    ('ART', 'MANDATORY', '', ''),
    ('HPE', 'MANDATORY', '', ''),
    ('ISLAM', 'CONDITIONAL', '', 'Islam'),
    ('HINDU', 'CONDITIONAL', '', 'Hindu'),
    ('CHRIS', 'CONDITIONAL', '', 'Christian'),
    ('BUDDHIST', 'CONDITIONAL', '', 'Buddhist'),
]

# ---- Junior secondary (no groups) --------------------------------------
JUNIOR_CLASSES = ['6', '7', '8']
JUNIOR_COMMON = [
    ('BAN1', 'MANDATORY', '', ''),
    ('BAN2', 'MANDATORY', '', ''),
    ('ENG1', 'MANDATORY', '', ''),
    ('ENG2', 'MANDATORY', '', ''),
    ('MATH', 'MANDATORY', '', ''),
    ('ICT', 'MANDATORY', '', ''),
    ('BGS', 'MANDATORY', '', ''),
    ('SCI-GEN', 'MANDATORY', '', ''),
    ('CAREER', 'MANDATORY', '', ''),
    ('HPE', 'MANDATORY', '', ''),
    ('ART', 'MANDATORY', '', ''),
    ('ISLAM', 'CONDITIONAL', '', 'Islam'),
    ('HINDU', 'CONDITIONAL', '', 'Hindu'),
    ('CHRIS', 'CONDITIONAL', '', 'Christian'),
    ('BUDDHIST', 'CONDITIONAL', '', 'Buddhist'),
]

# ---- SSC (class 9-10), group-wise --------------------------------------
SSC_CLASSES = ['9', '10']
SSC_COMMON = [
    ('BAN1', 'MANDATORY', '', ''),
    ('BAN2', 'MANDATORY', '', ''),
    ('ENG1', 'MANDATORY', '', ''),
    ('ENG2', 'MANDATORY', '', ''),
    ('ICT', 'MANDATORY', '', ''),
    ('BGS', 'MANDATORY', '', ''),
    ('CAREER', 'MANDATORY', '', ''),
    ('HPE', 'MANDATORY', '', ''),
    ('ART', 'MANDATORY', '', ''),
    ('ISLAM', 'CONDITIONAL', '', 'Islam'),
    ('HINDU', 'CONDITIONAL', '', 'Hindu'),
    ('CHRIS', 'CONDITIONAL', '', 'Christian'),
    ('BUDDHIST', 'CONDITIONAL', '', 'Buddhist'),
]
SSC_GROUPS = {
    'SCI': [
        ('MATH', 'MANDATORY', '', ''),
        ('PHY', 'MANDATORY', '', ''),
        ('CHEM', 'MANDATORY', '', ''),
        ('BIO', 'OPTIONAL', 'sci_4th', ''),
        ('HMATH', 'OPTIONAL', 'sci_4th', ''),
    ],
    'BUS': [
        ('MATH', 'MANDATORY', '', ''),
        ('ACC', 'MANDATORY', '', ''),
        ('BOM', 'MANDATORY', '', ''),
        ('FIN', 'OPTIONAL', 'bus_4th', ''),
        ('ECO', 'OPTIONAL', 'bus_4th', ''),
    ],
    'HUM': [
        ('SCI-GEN', 'MANDATORY', '', ''),
        ('CIVICS', 'OPTIONAL', 'hum_elective_1', ''),
        ('HISTORY', 'OPTIONAL', 'hum_elective_1', ''),
        ('GEO', 'OPTIONAL', 'hum_elective_1', ''),
        ('ECO', 'OPTIONAL', 'hum_elective_1', ''),
        ('LOGIC', 'OPTIONAL', 'hum_elective_2', ''),
        ('SOC', 'OPTIONAL', 'hum_elective_2', ''),
        ('PSY', 'OPTIONAL', 'hum_elective_2', ''),
        ('MATH', 'OPTIONAL', 'hum_elective_2', ''),
    ],
    # SSC Vocational trades — same class numbers (9-10) as general SSC, but
    # a separate group. Merged into SSC_GROUPS below so a Vocational
    # institution's 9/10 + DCS/DEL/DCV combination is still found.
    'DCS': [('DCS', 'MANDATORY', '', '')],
    'DEL': [('DEL', 'MANDATORY', '', '')],
    'DCV': [('DCV', 'MANDATORY', '', '')],
}

# ---- HSC (class 11-12), group-wise --------------------------------------
HSC_CLASSES = ['11', '12']
HSC_COMMON = [
    ('BAN1', 'MANDATORY', '', ''),
    ('BAN2', 'MANDATORY', '', ''),
    ('ENG1', 'MANDATORY', '', ''),
    ('ENG2', 'MANDATORY', '', ''),
    ('ICT', 'MANDATORY', '', ''),
    ('ISLAM', 'CONDITIONAL', '', 'Islam'),
    ('HINDU', 'CONDITIONAL', '', 'Hindu'),
    ('CHRIS', 'CONDITIONAL', '', 'Christian'),
    ('BUDDHIST', 'CONDITIONAL', '', 'Buddhist'),
]
HSC_GROUPS = {
    'SCI': [
        ('PHY', 'MANDATORY', '', ''),
        ('CHEM', 'MANDATORY', '', ''),
        ('BIO', 'OPTIONAL', 'sci_4th', ''),
        ('HMATH', 'OPTIONAL', 'sci_4th', ''),
    ],
    'BUS': [
        ('ACC', 'MANDATORY', '', ''),
        ('FIN', 'MANDATORY', '', ''),
        ('BOM', 'MANDATORY', '', ''),
        ('PMS', 'OPTIONAL', 'bus_4th', ''),
        ('STAT', 'OPTIONAL', 'bus_4th', ''),
    ],
    'HUM': [
        ('CIVICS', 'MANDATORY', '', ''),
        ('ECO', 'OPTIONAL', 'hum_elective_1', ''),
        ('HISTORY', 'OPTIONAL', 'hum_elective_1', ''),
        ('ISLHIST', 'OPTIONAL', 'hum_elective_1', ''),
        ('GEO', 'OPTIONAL', 'hum_elective_1', ''),
        ('LOGIC', 'OPTIONAL', 'hum_elective_2', ''),
        ('SOC', 'OPTIONAL', 'hum_elective_2', ''),
        ('SOCWORK', 'OPTIONAL', 'hum_elective_2', ''),
        ('PSY', 'OPTIONAL', 'hum_elective_2', ''),
        ('STAT', 'OPTIONAL', 'hum_elective_2', ''),
    ],
}


def curriculum_for_class(admission_class):
    """Return (common_rows, group_rows_dict) for a given class label, or
    (None, None) if this class isn't covered by the built-in curriculum
    (e.g. a diploma semester) — the caller should skip auto-fill in that case."""
    cls = str(admission_class).strip()
    if cls in PRIMARY_CLASSES:
        return PRIMARY_COMMON, {}
    if cls in JUNIOR_CLASSES:
        return JUNIOR_COMMON, {}
    if cls in HSC_CLASSES:
        return HSC_COMMON, HSC_GROUPS
    if cls in SSC_CLASSES:
        return SSC_COMMON, SSC_GROUPS
    return None, None
