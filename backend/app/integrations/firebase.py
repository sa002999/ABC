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
            path=os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
            credential=firebase_credentials.Certificate(path) if path else None
            return firebase_admin.initialize_app(credential=credential,options={
                "projectId": os.getenv("FIREBASE_PROJECT_ID"), "httpTimeout": 10
            }, name="kinu-auth")
