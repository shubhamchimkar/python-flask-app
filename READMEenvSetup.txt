setup a virtual python environment

py -m venv .venv
.venv\scripts\activate

app service in azure running on python 3.11


make a .env file in the root with these vars in it


CLIENT_ID="<Enter_your_client_id>"
CLIENT_SECRET="<Enter_your_client_secret>"
AUTHORITY="https://login.microsoftonline.com/<Enter_tenant_id>"
REDIRECT_URI="<Enter_redirect_uri>"
SCOPE=User.Read
ENDPOINT=https://graph.microsoft.com/v1.0/me


python -m flask run --debug --host=localhost --port=3000                                                              