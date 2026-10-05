"""K10 package rules shared by download/selection (stdlib only).

The social-object rule is a K10 convention on top of Overture's taxonomy;
it is the same rule as research/next-round/K10/scripts/places_by_district.py
(round 2), copied here so the package does not import round-2 code.
"""

RELEASE = "2026-09-23.1"
BUCKET = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com"

# Size of the study square (km); fixed before selection, not tuned afterwards.
CELL_KM = 2.0

SOCIAL_GROUPS = ("school", "preschool", "college_university", "hospital",
                 "outpatient_clinic", "pharmacy", "government_office")


def social_group(taxonomy, basic_category):
    """Return K10 social group for an Overture place, or None."""
    h = (taxonomy or {}).get("hierarchy") or []
    if h[:3] == ["education", "place_of_learning", "school"]:
        return "preschool" if "preschool" in h else "school"
    if h[:3] == ["education", "place_of_learning", "college_university"]:
        return "college_university"
    if h[:2] == ["health_care", "hospital"]:
        return "hospital"
    if "outpatient_care_facility" in h or "primary_care_or_general_clinic" in h:
        return "outpatient_clinic"
    if basic_category == "pharmacy_and_drug_store":
        return "pharmacy"
    if basic_category == "government_office":
        return "government_office"
    return None


def foot_access(access_restrictions):
    """Classify explicit pedestrian access of a segment from Overture access_restrictions.

    Returns (status, detail):
      'denied'    - a 'denied' rule applies to foot (mode contains 'foot') or to all modes (no mode list)
                    over the whole segment without time/heading conditions;
      'allowed'   - an 'allowed'/'designated' rule explicitly lists mode 'foot';
      'conditional' - foot-relevant rules exist but carry time/heading/partial-range conditions;
      'unknown'   - no foot-relevant rule recorded (absence of a tag is NOT permission).
    """
    rules = access_restrictions or []
    relevant = []
    for r in rules:
        when = r.get("when") or {}
        modes = when.get("mode")
        if modes is not None and "foot" not in modes:
            continue
        relevant.append(r)
    if not relevant:
        return "unknown", []
    plain = []
    for r in relevant:
        when = r.get("when") or {}
        conditioned = bool(when.get("during") or when.get("heading") or when.get("using")
                           or when.get("recognized") or when.get("vehicle") or r.get("between"))
        plain.append((r.get("access_type"), conditioned, bool(when.get("mode"))))
    if any(t == "denied" and not c for t, c, _ in plain):
        return "denied", relevant
    if any(t in ("allowed", "designated") and not c and m for t, c, m in plain):
        return "allowed", relevant
    return "conditional", relevant


def flags_of(road_flags):
    out = set()
    for f in road_flags or []:
        out.update(f.get("values") or [])
    return sorted(out)


def levels_of(level_rules):
    return sorted({r.get("value") for r in level_rules or [] if r.get("value") is not None})
