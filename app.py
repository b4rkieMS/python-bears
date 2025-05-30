from flask import Flask, redirect, url_for, session, request
from msal import ConfidentialClientApplication
import uuid
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Use a secure secret key

CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
AUTHORITY = f"https://login.microsoftonline.com/{os.environ.get('TENANT_ID')}"
REDIRECT_PATH = "/getAToken"
SCOPE = ["User.Read"]

@app.route("/")
def index():
    if not session.get("user"):
        return redirect(url_for("login"))
    return f"Hello, {session['user']['name']}!"

@app.route("/login")
def login():
    session["state"] = str(uuid.uuid4())
    auth_app = ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    auth_url = auth_app.get_authorization_request_url(
        SCOPE,
        state=session["state"],
        redirect_uri=url_for("authorized", _external=True)
    )
    return redirect(auth_url)

@app.route(REDIRECT_PATH)
def authorized():
    if request.args.get("state") != session.get("state"):
        return redirect(url_for("index"))  # State mismatch
    if "error" in request.args:
        return f"Error: {request.args['error']}"
    code = request.args.get("code")
    auth_app = ConfidentialClientApplication(
        CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
    )
    result = auth_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPE,
        redirect_uri=url_for("authorized", _external=True)
    )
    if "id_token_claims" in result:
        session["user"] = {
            "name": result["id_token_claims"].get("name"),
            "preferred_username": result["id_token_claims"].get("preferred_username"),
        }
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        f"{AUTHORITY}/oauth2/v2.0/logout?post_logout_redirect_uri={url_for('index', _external=True)}"
    )
