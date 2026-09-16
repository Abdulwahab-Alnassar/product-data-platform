"""Keep obvious contact details out of search results and model prompts."""

import re

EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)")


def redact(text):
    # This is a modest contact-detail filter, not a claim of complete anonymization.
    return PHONE.sub("[phone removed]", EMAIL.sub("[email removed]", str(text or "")))
