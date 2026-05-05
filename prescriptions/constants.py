DOCTOR_SPECIALTY_LABELS = (
    "طبيب عام",
    "قلبية",
    "عصبية",
    "أطفال",
    "نسائية",
    "عظمية",
    "باطنية",
    "أسنان",
    "أخرى",
)


DOCTOR_SPECIALTY_OPTIONS = tuple(
    {"value": label, "label": label} for label in DOCTOR_SPECIALTY_LABELS
)
