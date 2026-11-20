# RT.app status page

Public status page for RT.app at https://status.rt.app (free: GitHub Actions + GitHub Pages).

## How it works
- Every 5 minutes `.github/workflows/status.yml` runs `scripts/check.py`. It calls RT's own public pages and health checks only (rt.app, app.rt.app/login, the payment and banking API health and job-queue checks), then saves up / slow / down per service in `site/data/`. Response bodies are never saved.
- The page (`site/`) reads those files. Each bar is one day.
- GitHub may run the 5-minute schedule a few minutes late when it is busy.

## Post an incident (staff)
1. Open **Issues > New issue > Incident note** in this repository (https://github.com/Cooraez12/rt-status/issues/new/choose).
2. Write a short title and plain-English text for customers. It is public: no partner names, customer details, IDs, logs or secrets.
3. Submit. The note appears on the page within about a minute.
4. Post updates as comments. Close the issue when fixed; it then shows as Resolved for 30 days.

Only notes labelled `incident` and written by repository collaborators are shown. Ask the repo owner to add you as a collaborator.

## Change the services
Edit `CHECKS` and `COMPONENTS` in `scripts/check.py`. Only use RT's own public endpoints.
