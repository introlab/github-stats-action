import argparse
import os
import datetime

import requests

from googleapiclient.discovery import build
from google.auth import load_credentials_from_file

import pandas as pd


CLONES_VIEWS_SHEET_NAME = 'clones-views'
PATHS_SHEET_NAME = 'paths'
LAST_PATHS_SHEET_NAME = 'paths-last'
REFERRERS_SHEET_NAME = 'referrers'
LAST_REFERRERS_SHEET_NAME = 'referrers-last'


google_credentials, _ = load_credentials_from_file(os.environ['GOOGLE_APPLICATION_CREDENTIALS'])


def create_spreadsheet_sheets_if_required(spreadsheet_id: str):
    sheet_names = set(get_sheet_names(spreadsheet_id))
    if CLONES_VIEWS_SHEET_NAME not in sheet_names:
        create_sheet(spreadsheet_id,
                     CLONES_VIEWS_SHEET_NAME,
                     1,
                     ['Date', 'Clones', 'Unique Clones', 'Views', 'Unique Views'])
    if PATHS_SHEET_NAME not in sheet_names:
        create_sheet(spreadsheet_id,
                     PATHS_SHEET_NAME,
                     2,
                     ['Path', 'Count', 'Uniques'])
    if REFERRERS_SHEET_NAME not in sheet_names:
        create_sheet(spreadsheet_id,
                     REFERRERS_SHEET_NAME,
                     3,
                     ['Referrers', 'Count', 'Uniques'])
    if LAST_PATHS_SHEET_NAME not in sheet_names:
        create_sheet(spreadsheet_id,
                     LAST_PATHS_SHEET_NAME,
                     4,
                     ['Path', 'Count', 'Uniques'])
    if LAST_REFERRERS_SHEET_NAME not in sheet_names:
        create_sheet(spreadsheet_id,
                     LAST_REFERRERS_SHEET_NAME,
                     5,
                     ['Referrers', 'Count', 'Uniques'])


def get_sheet_names(spreadsheet_id: str) -> list[str]:
    service = build('sheets', 'v4', credentials=google_credentials)
    results = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return [r['properties']['title'] for r in results['sheets']]


def create_sheet(spreadsheet_id: str, sheet_name: str, index, columns_names: list[str]):
    body = {
        'requests': [{
            'addSheet': {
                'properties': {
                    'title': sheet_name,
                    'index': index
                }
            }
        }]
    }

    service = build('sheets', 'v4', credentials=google_credentials)
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

    body = {'values': [columns_names]}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet_name}!A1:AA',
        valueInputOption='USER_ENTERED',
        body=body
    ).execute()


def get_github_stats(owner_name: str, project_name: str):
    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {os.environ["GITHUB_TOKEN"]}',
        'X-GitHub-Api-Version': '2022-11-28',
        'Time-Zone': 'Etc/UCT'
    }
    clone_stats_url = f'https://api.github.com/repos/{owner_name}/{project_name}/traffic/clones?per=day'
    path_stats_url = f'https://api.github.com/repos/{owner_name}/{project_name}/traffic/popular/paths'
    referrers_stats_url = f'https://api.github.com/repos/{owner_name}/{project_name}/traffic/popular/referrers'
    views_stats_url = f'https://api.github.com/repos/{owner_name}/{project_name}/traffic/views?per=day'

    clone_stats_response = requests.get(clone_stats_url, headers=headers)
    path_stats_response = requests.get(path_stats_url, headers=headers)
    referrers_stats_response = requests.get(referrers_stats_url, headers=headers)
    views_stats_response = requests.get(views_stats_url, headers=headers)

    results = {}

    if clone_stats_response.status_code == 200:
        results['clone_stats'] = clone_stats_response.json()

    if path_stats_response.status_code == 200:
        results['path_stats'] = path_stats_response.json()

    if referrers_stats_response.status_code == 200:
        results['referrers_stats'] = referrers_stats_response.json()

    if views_stats_response.status_code == 200:
        results['views_stats'] = views_stats_response.json()

    return results


def append_clones_views(spreadsheet_id: str, github_new_stats: dict):
    today = current_date()
    actual_data = get_clones_views(spreadsheet_id)
    update_dict = {}

    if 'clone_stats' in github_new_stats:
        clone_stats = github_new_stats['clone_stats']
        if 'clones' in clone_stats:
            for clone in clone_stats['clones']:
                date = github_timestamp_to_date(clone['timestamp'])
                if actual_data['Date'].isin([date]).any() or date == today:
                    continue

                update_dict[date] = {'clone_count': clone['count'], 'clone_unique_count': clone['uniques']}
    if 'views_stats' in github_new_stats:
        view_stats = github_new_stats['views_stats']
        if 'views' in view_stats:
            for view in view_stats['views']:
                date = github_timestamp_to_date(view['timestamp'])

                # Verify if date is present in actual_data
                if actual_data['Date'].isin([date]).any() or date == today:
                    continue

                value = update_dict.get(date, {})
                value.update({'view_count': view['count'], 'view_unique_count': view['uniques']})
                update_dict[date] = value

    # Panda conversion to order by date
    update_df = pd.DataFrame(columns=actual_data.columns)
    for key, value in update_dict.items():
        update_df.loc[len(update_df)] = [key, value.get('clone_count', 0), value.get('clone_unique_count', 0),
                                         value.get('view_count', 0), value.get('view_unique_count', 0)]

    update_df = update_df.sort_values(by='Date')
    append_spreadsheet_values(spreadsheet_id, f'{CLONES_VIEWS_SHEET_NAME}!A1:E', 'USER_ENTERED', update_df.values.tolist())


def get_clones_views(spreadsheet_id: str) -> pd.DataFrame:
    values = get_spreadsheet_values(spreadsheet_id, f'{CLONES_VIEWS_SHEET_NAME}!A1:E')
    data = pd.DataFrame(values[1:], columns=values[0])
    return data


def current_date() -> str:
    dt = datetime.datetime.now(datetime.timezone.utc)
    return f'{dt.year:04}-{dt.month:02}-{dt.day:02}'


def github_timestamp_to_date(timestamp: str) -> str:
    return timestamp[:10]


def append_spreadsheet_values(spreadsheet_id: str, range_name: str, value_input_option: str, values: list[list[str]]):
    if len(values) == 0:
        return

    service = build('sheets', 'v4', credentials=google_credentials)

    body = {'values': values}
    result = service.spreadsheets().values().append(spreadsheetId=spreadsheet_id,
                                                    range=range_name,
                                                    valueInputOption=value_input_option,
                                                    body=body).execute()

    assert result['updates']['updatedRows'] == len(values), "Not all values appended"


def update_paths(spreadsheet_id: str, github_new_stats: dict):
    total_paths = paths_referrers_to_dict(get_spreadsheet_values(spreadsheet_id, f'{PATHS_SHEET_NAME}!A1:C'))
    last_paths = paths_referrers_to_dict(get_spreadsheet_values(spreadsheet_id, f'{LAST_PATHS_SHEET_NAME}!A1:C'))

    if 'path_stats' not in github_new_stats:
        return

    diff_paths = {}
    for path_stats in github_new_stats['path_stats']:
        path = path_stats['path']
        new_count = path_stats['count']
        new_uniques = path_stats['uniques']

        if path in last_paths:
            diff_paths[path] = {'count': max(new_count - last_paths[path]['count'], 0),
                                'uniques': max(new_uniques - last_paths[path]['uniques'], 0)}
        else:
            diff_paths[path] = {'count': new_count, 'uniques': new_uniques}

    for new_path in diff_paths.keys():
        if new_path in total_paths:
            total_paths[new_path]['count'] += diff_paths[new_path]['count']
            total_paths[new_path]['uniques'] += diff_paths[new_path]['uniques']
        else:
            total_paths[new_path] = diff_paths[new_path]

    update_spreadsheet_values(spreadsheet_id, f'{PATHS_SHEET_NAME}!A2:C', 'USER_ENTERED',
                              dict_to_paths_referrers(total_paths))
    update_spreadsheet_values(spreadsheet_id, f'{LAST_PATHS_SHEET_NAME}!A2:C', 'USER_ENTERED',
                              github_path_stats_to_paths(github_new_stats['path_stats']))


def update_referrers(spreadsheet_id: str, github_new_stats: dict):
    total_referrers = paths_referrers_to_dict(get_spreadsheet_values(spreadsheet_id, f'{REFERRERS_SHEET_NAME}!A1:C'))
    last_referrers = paths_referrers_to_dict(get_spreadsheet_values(spreadsheet_id, f'{LAST_REFERRERS_SHEET_NAME}!A1:C'))

    if 'referrers_stats' not in github_new_stats:
        return

    diff_referrers = {}
    for path_stats in github_new_stats['referrers_stats']:
        referrer = path_stats['referrer']
        new_count = path_stats['count']
        new_uniques = path_stats['uniques']

        if referrer in last_referrers:
            diff_referrers[referrer] = {'count': max(new_count - last_referrers[referrer]['count'], 0),
                                        'uniques': max(new_uniques - last_referrers[referrer]['uniques'], 0)}
        else:
            diff_referrers[referrer] = {'count': new_count, 'uniques': new_uniques}

    for new_referrer in diff_referrers.keys():
        if new_referrer in total_referrers:
            total_referrers[new_referrer]['count'] += diff_referrers[new_referrer]['count']
            total_referrers[new_referrer]['uniques'] += diff_referrers[new_referrer]['uniques']
        else:
            total_referrers[new_referrer] = diff_referrers[new_referrer]

    update_spreadsheet_values(spreadsheet_id, f'{REFERRERS_SHEET_NAME}!A2:C', 'USER_ENTERED',
                              dict_to_paths_referrers(total_referrers))
    update_spreadsheet_values(spreadsheet_id, f'{LAST_REFERRERS_SHEET_NAME}!A2:C', 'USER_ENTERED',
                              github_referrers_stats_to_referrers(github_new_stats['referrers_stats']))


def paths_referrers_to_dict(paths: list[list[str]]) -> dict[str, dict[str, int]]:
    return {v[0]: {'count': int(v[1]), 'uniques': int(v[2])} for v in paths[1:]}


def dict_to_paths_referrers(d: dict[str, dict[str, int]]) -> list[list[str]]:
    values = [[k, v['count'], v['uniques']] for k, v in d.items()]
    values.sort(reverse=True, key=lambda x: x[1])
    return values


def github_path_stats_to_paths(github_path_stats: dict) -> list[list[str]]:
    values = [[p['path'], p['count'], p['uniques']] for p in github_path_stats]
    values.sort(reverse=True, key=lambda x: x[1])
    return values


def github_referrers_stats_to_referrers(github_path_stats: dict) -> list[list[str]]:
    values = [[p['referrer'], p['count'], p['uniques']] for p in github_path_stats]
    values.sort(reverse=True, key=lambda x: x[1])
    return values


def get_spreadsheet_values(spreadsheet_id: str, range_name: str) -> list[list[str]]:
    service = build('sheets', 'v4', credentials=google_credentials)
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
    return result['values']


def update_spreadsheet_values(spreadsheet_id: str, range_name: str, value_input_option: str,
                              values: list[list[str]]):
    service = build('sheets', 'v4', credentials=google_credentials)

    body = {'values': values}
    result = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption=value_input_option,
        body=body,
    ).execute()

    assert result['updatedRows'] == len(values), "Not all values updated"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spreadsheet_id", type=str, required=True)
    parser.add_argument("--github_owner_name", type=str, required=True)
    parser.add_argument("--github_project_name", type=str, required=True)
    args = parser.parse_args()

    create_spreadsheet_sheets_if_required(args.spreadsheet_id)

    results = get_github_stats(args.github_owner_name, args.github_project_name)
    append_clones_views(args.spreadsheet_id, results)

    update_paths(args.spreadsheet_id, results)
    update_referrers(args.spreadsheet_id, results)


if __name__ == '__main__':
    main()
