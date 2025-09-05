
# GitHub Copilot Extension for Microsoft 365 Agents Toolkit – Product and Data Overview Template

## 1. Product Overview

The GitHub Copilot Extension for Microsoft 365 Agents Toolkit (a.k.a GH Copilot extension for MATK, GH Copilot extension for TTK, @m365agents, ATK extension, or ATK Copilot extension) streamlines the development of applications and agents for Microsoft 365 platform — including Microsoft Teams, Microsoft 365 Copilot, and other Microsoft 365 apps — with built-in chat capabilities. It has several key features:

- Provide details about your intended app or agent to get relevant examples.
- Explore applications and agents for Microsoft 365 platform development prompts.
- Resolve issues encountered during applications and agents for Microsoft 365 platform development.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: MATK Copilot Extension
- **Kusto Cluster**: `https://kustoforprod2.eastus2.kusto.windows.net/`
- **Kusto Database**: `prod`
- **Primary Metrics**: 

## 3. Table Schemas in Azure Data Explorer

### 3.1 Table `Span`

| Column                       | Type     | Description                          |
| ---------------------------- | -------- | ------------------------------------ |
| TIMESTAMP                    | datetime | Timestamp of the record              |
| CustomerResourceId           | string   | Customer resource identifier         |
| LocationId                   | string   | Location identifier                  |
| Metrics                      | string   | Metric values or summary             |
| env\_dt\_spanId              | string   | Distributed tracing span ID. One trace can have multi spans. A span can contain other spans. |
| env\_dt\_traceId             | string   | Distributed tracing trace ID. One request has only one trace. Used for joining with Span table. |
| env\_name                    | string   | Environment name                     |
| env\_time                    | datetime | Environment event time               |
| env\_ver                     | string   | Environment version                  |
| kind                         | long     | Kind or type indicator               |
| model\_name                  | string   | Model name, gpt-4o or gpt-4.1         |
| name                         | string   | Event or metric name. Name of the Span, e.g., heartbeat, handle_turn_request, tools, retrieve_resources, retrieve_schema |
| service.name                 | string   | Service name                         |
| startTime                    | string   | Start time of the operation          |
| success                      | bool     | Indicates if the operation succeeded |
| telemetry.sdk.language       | string   | SDK language                         |
| telemetry.sdk.name           | string   | SDK name                             |
| telemetry.sdk.version        | string   | SDK version                          |
| **AuthType**                 | string   | Authentication type                  |
| **AuthIdentity**             | string   | Authentication identity              |
| SourceNamespace              | string   | Source namespace                     |
| SourceMoniker                | string   | Source moniker                       |
| SourceVersion                | string   | Source version                       |
| completion\_token\_count\_v2 | long     | Completion token count (v2). Count of the completion tokens |
| intention                    | string   | User or system intention             |
| prompt\_token\_count\_v2     | long     | Prompt token count (v2). Count of the prompt tokens |
| thread\_id                   | string   | Copilot Thread ID, which represents the session of GitHub Copilot ChatThread ID |
| time\_to\_first\_token\_v2   | long     | Time to first token (v2) in ms.      |
| user\_id                     | string   | Hashed GitHub User ID                |
| statusMessage                | string   | Status message                       |
| app\_version                 | string   | Application version                  |
| **IsTrusted**                | string   | Whether the data is trusted          |
| matched                      | string   | A JSON string to present a list of matched resources, such as samples, docs, issues, or schema URL |
| parentId                     | string   | Parent span or event ID              |
| resource\_type               | string   | Type of resource involved, e.g., issues, samples, templates, documents, or App Manifest |
| tool\_name                   | string   | Name of the tool used, e.g., retrieve_resources, retrieve_schema |
| Role                         | string   | Role name                            |
| RoleInstance                 | string   | Instance of the role                 |
| Tenant                       | string   | Tenant identifier                    |
| env\_cloud\_role             | string   | Cloud role environment               |
| tool\_args                   | string   | Arguments passed to the tool         |
| tool\_description            | string   | Description of the tool              |
| schema\_version              | string   | Schema version identifier for "retrieve_schema" tool, e.g., default, 1.0 |


### 3.2 Function `getHandleTurnRequests`

Returns the HandleTurnRequests with a filter of including internal users 

Query Example 

```kusto
    let data = Span
        | where name == 'handle_turn_request'
        | project TIMESTAMP, user_id, thread_id, success,
                intention, model_name,
                total_time = (TIMESTAMP - todatetime(startTime)) / 1s,
                time_to_first_token = iff(time_to_first_token_v2 > 0, (datetime(1970-01-01) + tolong(time_to_first_token_v2 / 1e6) * 1ms - todatetime(startTime)) / 1s, 0.0),
                prompt_token_count = prompt_token_count_v2,
                completion_token_count = completion_token_count_v2
        | union (
            Log
            | where table__table_name == "handleturn" and table__lifecycle != "start"
            | project TIMESTAMP, user_id = table__user_id, thread_id = table__thread_id, success = table__lifecycle == "success",
                    intention = table__intention, model_name = table__model_name,
                    total_time = round(table__total_time_cost / 1e3, 3),
                    time_to_first_token = iff(table__time_to_first_token > 0, round(table__time_to_first_token / 1e3, 3), 0.0),
                    prompt_token_count = table__prompt_token_count,
                    completion_token_count = table__completion_token_count
        )
        | order by TIMESTAMP desc;
    union (data | where show_internal), (data | where show_internal == False and user_id !in (getInternalUserIds()))
```

### 3.3 Function `getToolUsages`

Returns the usage of tools with a filter of including internal users 

Query Example 

```kusto
let users = Span | project env_dt_traceId, user_id;
    let data = Log
        | project env_dt_traceId, TIMESTAMP, tool_name, type
        | where isnotempty(tool_name)
        | join kind=leftouter users on env_dt_traceId
        | summarize take_any(TIMESTAMP, user_id) by env_dt_traceId, tool_name, type;
    union (data | where show_internal), (data | where show_internal == False and user_id !in (getInternalUserIds()))
```

## 4. Common Analytical Scenarios

### 4.1 New Onboarding Users (Daily)

Query Example 

```kusto
let public_preview = datetime('2024-11-18');
let start = datetime(1970-01-01) + $__from * 1ms;
let end = datetime(1970-01-01) + $__to * 1ms;
getHandleTurnRequests(tobool($ShowInternalUsers))
| where TIMESTAMP between (public_preview .. end)
| summarize onboard_date = startofday(todatetime(min(TIMESTAMP))) by user_id
| make-series n = dcount(user_id) default = 0 on onboard_date 
              from startofday(start) to startofday(end, 1) step 1d
| mv-expand n, onboard_date
| project Time = todatetime(onboard_date), totalusers = toint(n)
```

### 4.2 New Onboard Users (Growth Trend)

Query Example 

```kusto
let public_preview = datetime('2024-11-18');
let start = datetime(1970-01-01) + $__from * 1ms;
let end = datetime(1970-01-01) + $__to * 1ms;
getHandleTurnRequests(tobool($ShowInternalUsers))
| where TIMESTAMP between (public_preview .. end)
| summarize onboard_date = startofday(todatetime(min(TIMESTAMP))) by user_id
| make-series n = dcount(user_id) default = 0 on onboard_date 
              from startofday(start) to startofday(end, 1) step 1d
| mv-expand n, onboard_date
| serialize  acc_onboard=row_cumsum(toint(n))
| extend Time = todatetime(onboard_date), n = toint(acc_onboard)
| project Time, n
```

### 4.3 Active 1 day (active1d) Users (Daily)

Query Example 

```kusto
let publicPreview = datetime('2024-11-18');
let start = datetime(1970-01-01) + $__from * 1ms;
let end = datetime(1970-01-01) + $__to * 1ms;
getHandleTurnRequests(tobool($ShowInternalUsers))
| where $__timeFilter(TIMESTAMP)
| project TIMESTAMP, user_id
| make-series n = dcount(user_id) default = 0 on TIMESTAMP 
              in range(startofday(start, 1), startofday(end, 1), 1d)
| mv-expand n, week = TIMESTAMP
| project Time = todatetime(week), totalusers = toint(n)
```

### 4.4 Engaged 2 days (engeage2d) Users (Daily)

Query Example 

```kusto
let public_preview = datetime('2024-11-18');
let start = datetime(1970-01-01) + $__from * 1ms + 1d - 1s;
let end = datetime(1970-01-01) + $__to * 1ms;
getHandleTurnRequests(tobool($ShowInternalUsers))
| where $__timeFilter(TIMESTAMP)
| extend day = startofday(todatetime(TIMESTAMP))
| summarize messages = count() by user_id, day
| extend week = startofweek(day)
| summarize days = dcount(day) by week, user_id
| make-series n = dcountif(user_id, days >= 2) default = 0 on week 
              from startofweek(start) to startofweek(end, 1) step 7d
| mv-expand n, week
| project Time = todatetime(week), activeUsers = toint(n)
```

### 4.5 Tools Usage (Count by Request)

Query Example 

```kusto
getToolUsages(tobool($ShowInternalUsers))
| where $__timeFilter(TIMESTAMP)
| summarize n = count() by resource_type
```

### 4.6 Documentation Matched (Count by Request)

Query Example 

```kusto
getToolUsages(tobool($ShowInternalUsers))
| where $__timeFilter(TIMESTAMP)
| where resource_type == "documents"
| mv-expand matched
| extend matched = tostring(matched)
| summarize times = count_distinct(env_dt_traceId) by matched
| sort by times desc
```

### 4.7 Issues Matched (Count by Request)

Query Example 

```kusto
getToolUsages(tobool($ShowInternalUsers))
| where $__timeFilter(TIMESTAMP)
| where resource_type == "issues"
| mv-expand matched
| extend matched = tostring(matched)
| summarize times = count_distinct(env_dt_traceId) by matched
| sort by times desc
```

### 4.8 Total Time

Query Example 

```kusto
getHandleTurnRequests(tobool($ShowInternalUsers))
| extend week = startofweek(TIMESTAMP), n = total_time
| summarize Max = max(n), Avg = avg(n), Median_50 = percentile(n, 50) by week
```

### 4.9 Time to First Token

Query Example 

```kusto
getHandleTurnRequests(tobool($ShowInternalUsers))
| where time_to_first_token > 0
| extend week = startofweek(TIMESTAMP), n = time_to_first_token
| summarize Max = max(n), Avg = avg(n), Median_50 = percentile(n, 50) by week
```

## 6. Notes and Considerations

- All timestamps are in **UTC**.
- Data refresh is **daily** with ~2-hour delay.
- For performance, limit query ranges to **<6 months** and results to **≤100 rows**.
- Always exclude usage from internal to focus on external customer behavior.
