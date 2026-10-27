# Cloud Run setup (Lab 6, once per project)

Run these commands **only in the Google Cloud project the instructor gives the team**, as a
member who has the IAM rights to create service accounts and identity pools. Nothing here
creates a key: GitHub Actions logs in with Workload Identity Federation (short-lived tokens).

```bash
PROJECT_ID=<project id from the instructor>
REGION=europe-west1
REPO=oscarico92/mlops-fri1-GOS-bike-demand
SA=bike-demand-deploy
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud config set project "$PROJECT_ID"

# APIs used by the workflow
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

# Image repository
gcloud artifacts repositories create bike-demand --repository-format=docker --location="$REGION"

# Deploy identity with the smallest set of roles the workflow needs
gcloud iam service-accounts create "$SA" --display-name="GitHub deploy (bike-demand)"
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA@$PROJECT_ID.iam.gserviceaccount.com" --role="$role"
done

# Identity pool trusted only for this repository
gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github-repo \
  --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == '$REPO' && assertion.ref == 'refs/heads/main'"
gcloud iam service-accounts add-iam-policy-binding "$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"
```

Why these roles: `run.admin` deploys revisions, moves traffic back and makes the service public
(`--allow-unauthenticated` sets an IAM policy); `artifactregistry.writer` pushes the image;
`iam.serviceAccountUser` lets the deploy identity start the service as its runtime account.
The provider condition accepts tokens from this repository's `main` branch only, so a pull
request or a fork cannot deploy.

Then, in GitHub: **Settings > Secrets and variables > Actions > Variables** (variables, not
secrets: none of these values is confidential):

| Variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | the project id |
| `GCP_REGION` | `europe-west1` |
| `CLOUD_RUN_SERVICE` | `bike-demand` |
| `GCP_ARTIFACT_REPO` | `bike-demand` |
| `GCP_WIF_PROVIDER` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github-repo` |
| `GCP_DEPLOY_SA` | `bike-demand-deploy@<PROJECT_ID>.iam.gserviceaccount.com` |

## After the lab

Delete what costs money or stays exposed:

```bash
gcloud run services delete bike-demand --region "$REGION"
gcloud artifacts repositories delete bike-demand --location "$REGION"
```

Remove the repository variables to switch the deploy off; the workflow then fails at
"Deploy configured?" with an explicit message instead of deploying.
