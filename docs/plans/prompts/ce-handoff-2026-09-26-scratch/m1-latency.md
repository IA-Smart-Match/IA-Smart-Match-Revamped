| route | n | p50 ms | p95 ms | max ms | statuses |
|---|---|---|---|---|---|
| GET /instructor/events | 2 | 36 | 66 | 66 | {409: 1, 200: 1} |
| GET /instructor/workspaces | 1 | 15 | 15 | 15 | {200: 1} |
| GET /instructor/workspaces/{n} | 1 | 20 | 20 | 20 | {200: 1} |
| GET /workspaces/current/asking-choice | 12 | 8 | 11 | 12 | {200: 12} |
| GET /workspaces/current/events/{ev}/list | 35 | 30 | 92 | 97 | {200: 35} |
| GET /workspaces/current/events/{ev}/list.csv | 1 | 22 | 22 | 22 | {200: 1} |
| GET /workspaces/current/events/{ev}/results | 37 | 11 | 16 | 20 | {200: 35, 404: 2} |
| GET /workspaces/current/events/{ev}/settings | 37 | 10 | 42 | 175 | {200: 37} |
| GET /workspaces/current/events/{ev}/settings/compare | 6 | 185 | 213 | 213 | {200: 6} |
| POST /instructor/events/{ev}/unlock | 4 | 12 | 18 | 18 | {409: 1, 200: 3} |
| POST /instructor/login | 2 | 193 | 252 | 252 | {401: 1, 200: 1} |
| POST /instructor/workspaces/{n}/reset | 1 | 28 | 28 | 28 | {200: 1} |
| POST /workspaces | 6 | 97 | 166 | 166 | {200: 6} |
| POST /workspaces/current/asking-choice | 12 | 26 | 46 | 51 | {200: 6, 409: 6} |
| POST /workspaces/current/events/{ev}/results | 59 | 35 | 194 | 209 | {409: 20, 422: 13, 404: 13, 201: 13} |
| POST /workspaces/current/refresh | 18 | 23 | 173 | 186 | {409: 12, 200: 6} |
| PUT /workspaces/current/events/{ev}/settings/{name} | 39 | 55 | 82 | 104 | {200: 39} |