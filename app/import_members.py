"""Import unambiguous members from a CSV without creating or deleting users."""
import csv
import io
import re
from collections import defaultdict

from db.models import User
from sqlalchemy import select

TAG = re.compile(r"^[A-Za-z]{4}$")
LEGACY_TAG = re.compile(r"^[A-Z]{4}$")


def parse_csv(data: bytes):
    """Collect row-level problems; malformed CSV syntax rejects the whole file."""
    try:
        source = io.StringIO(data.decode("utf-8-sig"), newline="")
        reader = csv.reader(source, strict=True)
        rows, issues = [], []
        for row in reader:
            if not row or all(not value.strip() for value in row):
                continue
            values = [value.strip() for value in row]
            first, last, email, tag = (values + [""] * 4)[:4]
            issue = {"line": reader.line_num, "name": f"{first} {last}".strip(),
                     "reference_tag": tag}
            reason = None
            if len(row) != 4:
                reason = "Expected four columns"
            elif not TAG.fullmatch(tag):
                reason = "Reference tag must be four letters"
            elif not first or not last or len(first) > 255 or len(f"{first} {last}") > 255:
                reason = "First and last name are required and must fit in the database"
            elif not email or "@" not in email or len(email) > 255:
                reason = "A valid email is required"
            if reason:
                issues.append({**issue, "reason": reason})
            else:
                rows.append({**issue, "first": first, "full_name": f"{first} {last}",
                             "email": email, "reference_tag": tag.upper()})
        return rows, issues
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"Cannot read CSV; no changes were made: {exc}") from exc


async def import_members(db, data: bytes) -> dict:
    rows, issues = parse_csv(data)
    groups = defaultdict(list)
    for row in rows:
        groups[row["reference_tag"]].append(row)
    # Even an invalid row with a recognizable tag makes that tag ambiguous.
    invalid_tags = {issue["reference_tag"].upper() for issue in issues
                    if TAG.fullmatch(issue["reference_tag"])}
    result = await db.execute(select(User).with_for_update())
    matches = defaultdict(dict)
    for user in result.scalars():
        candidates = set()
        if user.reference_tag and TAG.fullmatch(user.reference_tag):
            candidates.add(user.reference_tag.upper())
        for value in (user.name, user.full_name):
            if value and LEGACY_TAG.fullmatch(value):
                candidates.add(value)
        for tag in candidates & groups.keys():
            matches[tag][user.uid] = user

    updated = unchanged = 0
    for tag, entries in groups.items():
        def problem(reason):
            for entry in entries:
                issues.append({key: entry[key] for key in ("line", "name", "reference_tag")} | {"reason": reason})

        identities = {(r["first"], r["full_name"], r["email"]) for r in entries}
        if len(identities) > 1 or tag in invalid_tags:
            problem("Conflicting or invalid CSV rows share this tag")
            continue
        users = list(matches[tag].values())
        if not users:
            problem("No database user matches this tag")
            continue
        if len(users) > 1:
            problem("Multiple database users match this tag")
            continue
        user = users[0]
        if user.reference_tag and user.reference_tag.upper() != tag:
            problem("Database user has a different reference tag")
            continue
        # Another uploaded tag may point to the same user through a legacy field.
        if any(other != tag and user.uid in candidates for other, candidates in matches.items()):
            problem("Database user matches multiple CSV tags")
            continue
        entry = entries[0]
        desired = {"reference_tag": tag, "name": entry["first"],
                   "full_name": entry["full_name"], "campus_id": entry["email"]}
        if any(getattr(user, key) != value for key, value in desired.items()):
            for key, value in desired.items():
                setattr(user, key, value)
            updated += 1
        else:
            unchanged += 1
    await db.commit()
    issues.sort(key=lambda issue: issue["line"])
    return {"updated": updated, "unchanged": unchanged, "issues": issues}
