from flask import Flask, redirect, url_for, session, request, render_template_string
from msal import ConfidentialClientApplication
from openai import AzureOpenAI
from dotenv import load_dotenv
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import uuid
import os

from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Add ProxyFix to trust Azure's proxy headers
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Force Flask to use HTTPS in URL generation (important for Azure)
if "WEBSITE_HOSTNAME" in os.environ:
    app.config["PREFERRED_URL_SCHEME"] = "https"


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
        redirect_uri=url_for("authorized", _external=True, _scheme="https")
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

def get_azure_openai_client():
    load_dotenv()
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )

def get_openai_response(client, prompt):
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
        messages=[
            {"role": "system", "content": "You are a helpful assistant. You speak French only."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=100
    )
    return response.choices[0].message.content.strip()

@app.route("/ask", methods=["GET", "POST"])
def ask():
    answer = None
    if request.method == "POST":
        user_question = request.form.get("question")
        client = get_azure_openai_client()
        answer = get_openai_response(client, user_question)
    return render_template_string("""
        <h2>Ask Azure OpenAI</h2>
        <form method="post">
            <input name="question" placeholder="Enter your question" required>
            <input type="submit" value="Ask">
        </form>
        {% if answer %}
            <h3>Response:</h3>
            <p>{{ answer }}</p>
        {% endif %}
    """, answer=answer)