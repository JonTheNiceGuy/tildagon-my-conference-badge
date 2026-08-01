"""Run this ON the badge (via exec()) to pull the app straight from GitHub
over HTTPS, for testing when mpremote/serial access isn't available.

From the badge's REPL:

    import requests;exec(requests.get("https://raw.githubusercontent.com/JonTheNiceGuy/tildagon-my-conference-badge/<branch>/deploy_device.py").text)

Replace <branch> with whichever branch you want to pull.
"""

import os
import requests

BASE = "https://raw.githubusercontent.com/JonTheNiceGuy/tildagon-my-conference-badge/next"
APP_DIR = "/apps/badgeapp"
FILES = [
    "__init__.py", "app.py", "helpers.py", "page_indicator.py", "qr.py",
    "web.py", "tildagon.toml", "metadata.json",
    "event_images/emfcamp-2024.jpg", "event_images/emfcamp-2026.jpg",
]


def rm_rf(path):
    try:
        items = os.listdir(path)
    except OSError:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    for name in items:
        rm_rf(path + "/" + name)
    os.rmdir(path)


def mkdir_p(path):
    parts = path.strip("/").split("/")
    built = ""
    for part in parts:
        built += "/" + part
        try:
            os.mkdir(built)
        except OSError:
            pass


rm_rf(APP_DIR)
mkdir_p(APP_DIR + "/event_images")
for name in FILES:
    resp = requests.get(BASE + "/" + name)
    data = resp.content
    resp.close()
    with open(APP_DIR + "/" + name, "wb") as out:
        out.write(data)
    print("wrote " + name)
print("done")
