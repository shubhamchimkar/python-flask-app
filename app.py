import os
import yaml
from flask import Flask, render_template, request, redirect
from identity.flask import Auth
import app_config
from utils import optional_auth
from models import db, WorkItem, Project

app = Flask(__name__)
app.config.from_object(app_config)

# Secret & session
app.secret_key = app.config.get('SECRET_KEY')
app.config['SESSION_TYPE'] = app.config.get('SESSION_TYPE')

# Azure AD Auth
auth = Auth(
    app,
    authority=app.config["AUTHORITY"],
    client_id=app.config["CLIENT_ID"],
    client_credential=app.config["CLIENT_SECRET"],
    redirect_uri=app.config["REDIRECT_URI"]
)
app.auth_instance = auth

# SQLAlchemy Setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///devops.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# ----------------------------------------------
# Inject global variables into all templates
# ----------------------------------------------
@app.context_processor
def inject_common_context():
    user = getattr(request, 'user_context', None)
    projects = []
    selected_project = None

    if user:
        projects = Project.query.filter_by(created_by=user['name']).all()

        if request.path.startswith("/boards/") or (request.path.startswith("/pipelines") and request.args.get("project_id")):
            try:
                project_id = (
                    request.view_args.get("project_id")
                    if request.view_args and "project_id" in request.view_args
                    else request.args.get("project_id")
                )
                if project_id:
                    selected_project = Project.query.get(int(project_id))
            except Exception:
                selected_project = None

    return dict(projects=projects, selected_project=selected_project)

# ---------------- DASHBOARD ---------------- #
@app.route("/")
@optional_auth
def dashboard(*, context):
    projects = Project.query.filter_by(created_by=context['user']['name']).all()
    return render_template("dashboard.html", user=context['user'], title="Dashboard", projects=projects)

@app.route("/create_project", methods=["POST"])
@optional_auth
def create_project(*, context):
    project = Project(
        name=request.form['name'],
        description=request.form['description'],
        created_by=context['user']['name']
    )
    db.session.add(project)
    db.session.commit()
    return redirect("/")

# ---------------- BOARDS ---------------- #
@app.route("/boards/<int:project_id>", methods=["GET"])
@optional_auth
def boards(project_id, *, context):
    project = Project.query.get_or_404(project_id)
    work_items = WorkItem.query.filter_by(project_id=project_id).all()
    return render_template(
        "boards.html",
        title="Boards",
        user=context['user'],
        project=project,
        work_items=work_items
    )

@app.route("/add_item/<int:project_id>", methods=["POST"])
@optional_auth
def add_item(project_id, *, context):
    item = WorkItem(
        project_id=project_id,
        title=request.form['title'],
        description=request.form['description'],
        type=request.form['type'],
        priority=request.form['priority'],
        created_by=context['user']['name']
    )
    db.session.add(item)
    db.session.commit()
    return redirect(f"/boards/{project_id}")

@app.route("/update_item/<int:item_id>/<int:project_id>", methods=["POST"])
@optional_auth
def update_item(item_id, project_id, *, context):
    item = WorkItem.query.get_or_404(item_id)
    item.status = request.form['status']
    db.session.commit()
    return redirect(f"/boards/{project_id}")

# ---------------- PIPELINES ---------------- #
@app.route("/pipelines", methods=["GET"])
@optional_auth
def pipelines(*, context):
    project_id = request.args.get("project_id")
    return render_template(
        "pipelines.html",
        title="Pipelines",
        user=context['user'],
        project_id=project_id
    )

@app.route("/upload_yaml", methods=["POST"])
@optional_auth
def upload_yaml(*, context):
    project_id = request.args.get("project_id")
    uploaded_file = request.files.get("yaml_file")
    yaml_content = None

    if uploaded_file:
        yaml_str = uploaded_file.read().decode("utf-8")
        try:
            yaml_content = yaml.safe_load(yaml_str)
        except Exception as e:
            yaml_content = f"YAML parsing error: {e}"

    return render_template(
        "pipelines.html",
        title="Pipelines",
        yaml_content=yaml.dump(yaml_content, indent=2) if isinstance(yaml_content, dict) else yaml_content,
        user=context['user'],
        project_id=project_id
    )

# ---------------- RUN ---------------- #
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
