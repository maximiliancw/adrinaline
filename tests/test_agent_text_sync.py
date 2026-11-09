from adrinaline.prime import RULES
from adrinaline.repo import data_text


def test_skill_and_prime_rules_share_the_workflow():
    skill = data_text("skills/adr/SKILL.md")
    for phrase in (
        "adr for <path>",
        "--body-file -",
        "--supersedes N",
        "--amends N",
        "proposed",
        "adr check",
        "adr accept N",
        "adr review N",
        "ADR: N",
        "ADR-Exempt:",
    ):
        assert phrase in skill and phrase in RULES, phrase
