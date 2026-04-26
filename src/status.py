from enum import Enum

class Status(Enum):
    NEW = "NEW"
    DRAFTED = "DRAFTED"
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    FAILED = "FAILED"