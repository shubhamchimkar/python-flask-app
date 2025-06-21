import os
import logging
import base64
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
from identity.flask import Auth
import app_config
from utils import optional_auth

# ------------------------- Load .env -------------------------
load_dotenv()
AZURE_ORG = os.getenv("AZURE_ORGANIZATION")
AZURE_PAT = os.getenv("AZURE_DEVOPS_PAT")
if not AZURE_ORG or not AZURE_PAT:
    raise Exception("Please set .env ➜ AZURE_ORGANIZATION & AZURE_DEVOPS_PAT")

API_BASE = f"https://dev.azure.com/{AZURE_ORG}"

# ------------------------- App Config -------------------------
app = Flask(__name__)
app.config.from_object(app_config)
app.secret_key = app.config.get('SECRET_KEY')

# ------------------------- Azure AD Auth -------------------------
auth = Auth(app,
    authority=app.config["AUTHORITY"],
    client_id=app.config["CLIENT_ID"],
    client_credential=app.config["CLIENT_SECRET"],
    redirect_uri=app.config["REDIRECT_URI"]
)
app.auth_instance = auth

# ------------------------- Azure DevOps Helpers -------------------------
def get_headers():
    token = base64.b64encode(f":{AZURE_PAT}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def azure_get(path, params=None):
    try:
        resp = requests.get(f"{API_BASE}/{path}", headers=get_headers(), params=params)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.JSONDecodeError as e:
        logging.error(f"JSONDecodeError for GET {path}: {e}")
        logging.error(f"Response text: {resp.text}")
        return {}
    except requests.exceptions.RequestException as e:
        logging.error(f"RequestException for GET {path}: {e}")
        return {}

def azure_post(path, data):
    try:
        resp = requests.post(f"{API_BASE}/{path}", headers=get_headers(), json=data)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.JSONDecodeError as e:
        logging.error(f"JSONDecodeError for POST {path}: {e}")
        logging.error(f"Response text: {resp.text}")
        return {}
    except requests.exceptions.RequestException as e:
        logging.error(f"RequestException for POST {path}: {e}")
        return {}

def azure_get_pipeline_details(pipeline_id):
    project = session.get("project")
    if not project:
        raise Exception("No project selected")
    return azure_get(f"{project}/_apis/pipelines/{pipeline_id}?api-version=7.1-preview.1")

def azure_run_pipeline(pipeline_id):
    project = session.get("project")
    if not project:
        raise Exception("No project selected")
    return azure_post(f"{project}/_apis/pipelines/{pipeline_id}/runs?api-version=7.1-preview.1", {})

# ------------------------- Context for templates -------------------------
@app.context_processor
def inject_globals():
    return dict(
        user=session.get("user"),
        selected_project=session.get("project")
    )

# ------------------------- Routes -------------------------
@app.route("/login")
def login():
    return redirect(app.auth_instance.get_login_redirect_url())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("dashboard"))

@app.route("/")
@optional_auth
def dashboard(*, context):
    projects = azure_get("_apis/projects?api-version=7.1-preview.4").get("value", [])
    return render_template("dashboard.html", title="Dashboard", projects=projects)

@app.route("/select/<project>")
def select_project(project):
    session["project"] = project
    return redirect(url_for("dashboard"))

@app.route("/boards")
@optional_auth
def boards(*, context):
    project = session.get("project")
    if not project:
        return redirect(url_for("dashboard"))

    wiql = {
        "query": "SELECT [System.Id], [System.Title], [System.State] FROM WorkItems ORDER BY [System.CreatedDate] DESC"
    }

    result = azure_post(f"{project}/_apis/wit/wiql?api-version=7.1", wiql)
    ids = [str(i["id"]) for i in result.get("workItems", [])][:20]

    if not ids:
        return render_template("boards.html", title="Boards", work_items=[])

    items = azure_get(f"{project}/_apis/wit/workitems?ids={','.join(ids)}&api-version=7.1").get("value", [])
    return render_template("boards.html", title="Boards", work_items=items)

@app.route("/pipelines")
@optional_auth
def pipelines(*, context):
    project = session.get("project")
    if not project:
        return redirect(url_for("dashboard"))

    pipelines = azure_get(f"{project}/_apis/pipelines?api-version=7.1-preview.1").get("value", [])

    for p in pipelines:
        runs = azure_get(f"{project}/_apis/pipelines/{p['id']}/runs?api-version=7.1-preview.1").get("value", [])
        p["latest"] = runs[0] if runs else None

    return render_template("pipelines.html", title="Pipelines", pipelines=pipelines)

@app.route('/pipelines/<pipeline_id>')
def view_pipeline(pipeline_id):
    pipeline = azure_get_pipeline_details(pipeline_id)
    return render_template('pipeline_detail.html', title="Pipeline Detail", pipeline=pipeline)

@app.route('/pipelines/<pipeline_id>/run', methods=['POST', 'GET'])
def run_pipeline(pipeline_id):
    if request.method == 'POST':
        azure_run_pipeline(pipeline_id)
        return redirect(url_for('pipelines'))
    return render_template('confirm_run.html', title="Run Pipeline", pipeline_id=pipeline_id)

@app.route('/pipelines/<pipeline_id>/yaml', methods=['GET', 'POST'])
def edit_pipeline_yaml(pipeline_id):
    project = session.get("project")
    if not project:
        return redirect(url_for("dashboard"))

    pipeline = azure_get(f"{project}/_apis/pipelines/{pipeline_id}?api-version=7.1-preview.1")
    config = pipeline.get("configuration", {})
    yaml_path = config.get("path")
    repo = config.get("repository", {})
    repo_id = repo.get("id")
    repo_type = repo.get("type")
    branch = repo.get("defaultBranch", "refs/heads/main").replace("refs/heads/", "")

    if not yaml_path or not repo_id:
        return "YAML path or repo info missing. Check if the pipeline uses a classic editor or non-azureReposGit source."

    if repo_type != "azureReposGit":
        return "Only azureReposGit is supported."

    if request.method == 'POST':
        new_content = request.form.get('yaml_content', '')

        branch_ref = azure_get(
            f"{project}/_apis/git/repositories/{repo_id}/refs",
            params={"filter": f"heads/{branch}", "api-version": "7.1-preview"}
        )
        old_object_id = branch_ref.get("value", [{}])[0].get("objectId")

        if not old_object_id:
            return "Could not determine latest commit for the branch.", 500

        data = {
            "refUpdates": [{
                "name": f"refs/heads/{branch}",
                "oldObjectId": old_object_id
            }],
            "commits": [{
                "comment": f"Update pipeline YAML for pipeline ID {pipeline_id}",
                "changes": [{
                    "changeType": "edit",
                    "item": { "path": yaml_path },
                    "newContent": {
                        "content": new_content,
                        "contentType": "rawtext"
                    }
                }]
            }]
        }

        azure_post(f"{project}/_apis/git/repositories/{repo_id}/pushes?api-version=7.1", data)
        return redirect(url_for('pipelines'))

    # Get file metadata to find the blob ID (SHA)
    item_metadata = azure_get(
        f"{project}/_apis/git/repositories/{repo_id}/items",
        params={"path": yaml_path, "api-version": "7.1"}
    )
    blob_id = item_metadata.get("objectId")

    if not blob_id:
        return "Could not find file in repository.", 500

    # Get the raw file content from the blob endpoint
    headers = get_headers()
    headers["Accept"] = "text/plain"
    content_resp = requests.get(
        f"{API_BASE}/{project}/_apis/git/repositories/{repo_id}/blobs/{blob_id}?api-version=7.1",
        headers=headers
    )
    content_resp.raise_for_status()
    yaml_content = content_resp.text
    return render_template("edit_yaml.html", title="Edit Pipeline YAML", yaml=yaml_content,
                           file_path=yaml_path, pipeline_id=pipeline_id)


# ------------------------- Start -------------------------
if __name__ == "__main__":
    app.run(debug=True)
