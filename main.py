"""Entry point for Viper Mini Config."""

import sys

# Ensure the project directory is on the path when double-clicked
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from gui import App

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
