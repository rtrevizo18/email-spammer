from datetime import datetime, timezone
import email_validator

from status import Status

def validate_scheduler(scheduler):
    columns = ["LastSentAtUTC", "ActionsPerDay", "Officer", "Role"]

    if len(scheduler) != 1:
        raise Exception(f"Expected number of rows: 1, Given: {len(scheduler)}")

    scheduler_row = scheduler[0]

    for col in columns:
        if col not in scheduler_row:
            raise Exception(f"Column {col} does not exist on scheduler row.")

    last_sent_utc = scheduler_row["LastSentAtUTC"]
    if not last_sent_utc:
        last_sent_utc = datetime.now(timezone.utc).isoformat()

    dt = datetime.fromisoformat(last_sent_utc)
    if dt.tzinfo != timezone.utc:
        raise Exception("Read timestamp does not correspond to UTC timezone.")

    amount_sent = scheduler_row["ActionsPerDay"]
    if not isinstance(amount_sent, int):
        raise Exception("ActionsPerDay is not a number.")

    officer_name = scheduler_row["Officer"]
    if not isinstance(officer_name, str) or len(officer_name) == 0:
        raise Exception("Officer name is not a non-empty string.")

    officer_role = scheduler_row["Role"]
    if not isinstance(officer_role, str) or len(officer_role) == 0:
        raise Exception("Officer role is not a non-empty string.")

    return dt, amount_sent, officer_name, officer_role

def validate_email(email):
    email_info = email_validator.validate_email(email, check_deliverability=True)
    return email_info.normalized

def validate_contact(row):
    columns = ["Company", "FirstName", "LastName", "Email"]

    for col in columns:
        if col not in row:
            raise Exception(f"Column {col} does not exist on this row.")

        value = row[col]
        if not isinstance(value, str):
            raise Exception(f"Value of column {col} must be string, got {type(value)}.")
        if len(value) == 0:
            raise Exception(f"Value of column {col} is empty.")

    row["Email"] = validate_email(row["Email"])
    return row

def validate_row(row):
    validated_contact_row = validate_contact(row)

    status = validated_contact_row.get("Status")
    if not status:
        status = Status.NEW.value

    try:
        validated_contact_row["Status"] = Status(status)
    except ValueError:
        raise Exception(f"Invalid status in sheet: {status}")

    return validated_contact_row


def is_blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def is_empty_row(row):
    if is_blank(row.get("ID")):
        return False

    content_columns = [
        "Company",
        "FirstName",
        "LastName",
        "Email",
    ]

    return all(is_blank(row.get(column)) for column in content_columns)