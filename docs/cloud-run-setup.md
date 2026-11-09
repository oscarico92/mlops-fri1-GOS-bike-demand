# Cloud Run setup (Lab 6, once)

Our project is the instructor's shared project (`mlops-ece-group2-and-group3`, other teams
deploy there too). Rules for this shared project:

- every resource we create starts with `gos-`;
- IAM is only ever **added** with `add-iam-policy-binding` (never `set-iam-policy`, never
  removing a binding): one wrong command would remove other teams' access;
- nothing creates a key. GitHub Actions logs in with **direct Workload Identity Federation**:
  the roles below are granted to the identity of our repository's `main` branch itself.

Our IAM roles in the project are *Project IAM Admin*, *Create Service Accounts* and *Editor*.
Granting roles on a service account would need rights we do not have, which is why we use
direct federation (roles granted at project level to our repository identity) instead of
impersonating a deploy service account.

Run in **Cloud Shell** (console, top right `>_`), with the project selected:

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
REGION=europe-west1
REPO=oscarico92/mlops-fri1-GOS-bike-demand
echo "$PROJECT_ID $PROJECT_NUMBER"

# APIs used by the workflow (no effect if already enabled)
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

# Image repository for our team
gcloud artifacts repositories create gos-bike-demand --repository-format=docker --location="$REGION"

# Identity pool and provider trusted only for our repository's main branch
gcloud iam workload-identity-pools create gos-github --location=global \
  --display-name="GOS GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc gos-github-repo \
  --location=global --workload-identity-pool=gos-github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == '$REPO' && assertion.ref == 'refs/heads/main'"

# Roles for that identity only (added, never replacing existing bindings)
MEMBER="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gos-github/attribute.repository/$REPO"
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="$MEMBER" --role="$role" --condition=None
done

# Value for the GCP_WIF_PROVIDER variable
echo "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/gos-github/providers/gos-github-repo"
```

Why these roles: `run.admin` deploys revisions, moves traffic back and makes the service public
(`--allow-unauthenticated` sets an IAM policy on the service); `artifactregistry.writer` pushes the
image; `iam.serviceAccountUser` lets the deploy start the service as its runtime account. The
provider condition accepts tokens from this repository's `main` branch only, so a pull request or
a fork cannot deploy. Limit: `iam.serviceAccountUser` at project level is broader than needed
(it covers every service account of the shared project); granting it on the runtime account only
would need rights on that account that we do not have.

Then in GitHub: **Settings > Secrets and variables > Actions > Variables** (variables, not secrets:
none of these values is confidential):

| Variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | the project id printed above |
| `GCP_REGION` | `europe-west1` |
| `CLOUD_RUN_SERVICE` | `gos-bike-demand` |
| `GCP_ARTIFACT_REPO` | `gos-bike-demand` |
| `GCP_WIF_PROVIDER` | the provider path printed by the last command |

## After the lab

```bash
gcloud run services delete gos-bike-demand --region europe-west1
gcloud artifacts repositories delete gos-bike-demand --location europe-west1
```

Remove the repository variables to switch the deploy off: the workflow then fails at
"Deploy configured?" with an explicit message instead of deploying.
