# github-stats-action

This is an action to accumulate the repository traffic in a Google Spreadsheet document.

## How to Use?

### 1. Create the following action secrets
- `STATS_TOKEN``: A GitHub Personnal Token that has the `administration:read` permission.
- `GOOGLE_APPLICATION_CREDENTIALS`: The JSON key of the service account that perform the changes in the Google Spreadsheet document.
- `SPREADSHEET_ID `: The id of the Google Spreadsheet document.

### 2. Add the following workflow
```yml
name: Scheduled Stats Extraction From GitHub

on:
    workflow_dispatch:
    schedule:
        - cron: '0 5 * * *'
jobs:
    get_stats:
        runs-on: ubuntu-latest
        steps:
            - name: Update Stats
              uses: introlab/github-stats-action@v1
              with:
                  github-stats-token: ${{ secrets.STATS_TOKEN }}
                  google-application-credentials: ${{ secrets.GOOGLE_APPLICATION_CREDENTIALS }}
                  spreadsheet-id: ${{ secrets.SPREADSHEET_ID }}
```
