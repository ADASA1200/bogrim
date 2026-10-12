"""נקודת הכניסה לקובץ ה-EXE (PyInstaller). בלי ארגומנטים = האפליקציה המלאה."""
import sys

from rdesk.__main__ import main

if __name__ == "__main__":
    main(sys.argv[1:])
