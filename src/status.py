from enum import Enum

class Status(Enum):
    NEW = "NEW"
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    FAILED = "FAILED"