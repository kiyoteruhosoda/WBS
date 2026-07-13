from __future__ import annotations
import enum

class DependencyType(str, enum.Enum):
    FS = "FS"  # Finish-to-Start
    SS = "SS"  # Start-to-Start
    FF = "FF"  # Finish-to-Finish
    SF = "SF"  # Start-to-Finish
