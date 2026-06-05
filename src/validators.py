from datetime import datetime, timezone, timedelta
import email_validator

from status import Status

def validate_scheduler(scheduler):
    columns = ["LastSentAtUTC", "ActionsPerDay", "Officer", "Role", "StopAction"]

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
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
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

    stop_action = scheduler_row.get("StopAction")
    if isinstance(stop_action, bool):
        stop_action_value = stop_action
    elif stop_action is None:
        stop_action_value = False
    elif isinstance(stop_action, str):
        normalized = stop_action.strip().lower()
        if normalized in ("true", "yes", "1"):
            stop_action_value = True
        elif normalized in ("false", "no", "0", ""):
            stop_action_value = False
        else:
            raise Exception("StopAction is not a boolean value.")
    elif isinstance(stop_action, (int, float)):
        stop_action_value = stop_action != 0
    else:
        raise Exception("StopAction is not a boolean value.")

    return dt, amount_sent, officer_name, officer_role, stop_action_value

def validate_email(email):
    # Emails can either be single value or comma-seperated list of emails
    # If the email contains a comma, then consider it a list for parsing
    email = email.strip()
    email_list = email.split(',')
    norm_emails = []
    for em in email_list:
        trimmed_em = em.strip()
        print(trimmed_em)
        validated_email = email_validator.validate_email(trimmed_em, check_deliverability=True)
        norm_emails.append(validated_email.normalized)
    # returns comma-sep list, preferred format for gmail
    return ", ".join(norm_emails)

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
    elif status == "DRAFTED":
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
    content_columns = [
        "Company",
        "FirstName",
        "LastName",
        "Email",
    ]
    if is_blank(row.get("ID")):
        return all(is_blank(row.get(column)) for column in content_columns)

    return all(is_blank(row.get(column)) for column in content_columns)