from firebase_admin import credentials as firebase_credentials
from threading import Lock
import firebase_admin
import os


initialization_lock = Lock()


def firebase_app():
    with initialization_lock:
        try:
            return firebase_admin.get_app("kinu-auth")
        except ValueError:
            project_id = os.environ["FIREBASE_PROJECT_ID"]
            return firebase_admin.initialize_app(
                credential=firebase_credentials.ApplicationDefault(),
                options={"projectId": project_id, "httpTimeout": 10},
                name="kinu-auth",
            )
