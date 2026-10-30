# EP-<name>

| Field | Value | Evidence |
| --- | --- | --- |
| Kind | REST / listener / scheduled / CLI / startup | |
| Address | `POST /api/...` / topic / cron / main class + args | |
| Security | roles, auth | |
| Transaction | boundary, propagation | |

## Contract

**Request**

| Field | Type | Required | Validation | JSON name / format |
| --- | --- | --- | --- | --- |

**Response / output**

| Status | Body | When |
| --- | --- | --- |

## Call path

```text
Controller.method (path:line)
  -> Service.method (path:line)
     -> Repository.query (path:line)   SQL: ...
     -> Client.call (path:line)        GET ${x.url}/...
```

## Rules

| ID | Condition | Effect | Evidence |
| --- | --- | --- | --- |

## Errors

| Exception | Mapped to | Evidence |
| --- | --- | --- |

## Side effects

## Tests covering this entry point

## NOTES for replication
