# VS Code AI Foundry - Product and Data Overview Template

## 1. Product Overview

> Draft: VS Code AI Foundry Metrics (Internal). This dataset centers on a single event fact table for the VS Code AI Foundry extension.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
> VS Code AI Foundry
- **Product Nick Names**: 
> **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
> https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx
- **Kusto Database**:
> vscode-ext-aggregate
- **Access Control**:
> **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

## Overview

- Product: VS Code AI Foundry
- Summary: VS Code AI Foundry Metrics (Internal)
- Primary cluster: https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx
- Database: vscode-ext-aggregate
- Notes: This dataset centers on a single event fact table for the VS Code AI Foundry extension.

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - ClientTimestamp (client-side event time; frequently used for filters and 1d binning)
  - ServerTimestamp (service-side ingestion/processing time; used in daily/rolling counts and cohort/retention-like logic)
  - Derived day keys via startofday(ClientTimestamp) and startofday(ServerTimestamp)
- Canonical Time Column:
  - Use ClientTimestamp as the canonical event time for interactive trends and filtering.
  - When you must use ServerTimestamp (e.g., rolling-28 “days seen” patterns), keep the analysis entirely in that time domain.
- Alias pattern:
  ```kusto
  // Normalize different timestamp columns to a canonical name
  | project-rename TimeCol = ClientTimestamp
  // or when analyzing ingestion-time-based days:
  | project-rename TimeCol = ServerTimestamp
  ```
- Typical windows:
  - Dashboard parameters: _startTime, _endTime
  - Rolling windows: last 28 days using Date between ((<EndDate> - 27d) .. <EndDate>)
  - Weekly cohorts: startofweek() to endofweek() steps
- Common bin() usage:
  - bin(ClientTimestamp, 1d) for DAU and daily trends
- Timezone:
  - Unknown. Assume UTC by default. Be consistent and avoid mixing ClientTimestamp and ServerTimestamp within a single metric unless you intentionally design for it.

### Freshness & Completeness Gates
- Ingestion cadence: unknown.
- Current-day completeness: unknown; avoid using “today” for production metrics until verified. Queries often stop at ago(1d) or endofday(ago(1d)).
- Effective end time template:
  ```kusto
  let _endTime = endofday(ago(1d));  // avoid same-day partial ingestion
  let _startTime = _endTime - 30d;
  ```
- Multi-slice completeness gate (example: require all OS slices present for a date):
  ```kusto
  let INPUT_OS = dynamic(['win32','darwin','linux']);
  let CompleteDays =
    ai_foundry_vsc
    | project Date = startofday(ServerTimestamp),
              OS = tostring(Properties['common.os'])
    | where OS in (INPUT_OS)
    | summarize slices = dcount(OS) by Date
    | where slices >= array_length(INPUT_OS)
    | project Date;
  // Join to CompleteDays to keep only complete dates
  ai_foundry_vsc
  | project Date = startofday(ServerTimestamp), *
  | join kind=inner (CompleteDays) on Date
  ```
- Conservative practice: Prefer previous full week/month for monthly/weekly reporting.

### Joins & Alignment
- Frequent keys:
  - VSCodeMachineId: primary user proxy key for dcount(), retention, funnels.
  - EventName / EventNameShort: used to bucket features and funnel steps.
  - Derived Feature via case() mapping from EventNameShort to “model” or “agent.”
- Common join kinds:
  - inner joins:
    - event-to-step mapping tables (datatable then mv-expand)
    - cross-join with date/weekly ranges via “dummy = 1” hack
  - leftouter occasionally for enrichment (not observed explicitly in provided set)
- Post-join hygiene:
  - Drop temporary keys and duplicates with project-away.
  - Normalize keys/time before summarize to avoid misaligned grouping.
  ```kusto
  | project-away dummy, dummy1
  | project-rename TimeCol = ClientTimestamp
  ```

### Filters & Idioms
- Default event exclusions:
  - EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
- OS filter:
  - OS = tostring(Properties['common.os'])
  - OS in (['INPUT_OS']) in dashboard context, or define a dynamic array for ad-hoc runs:
    ```kusto
    let INPUT_OS = dynamic(['win32','darwin','linux']);
    | where OS in (INPUT_OS)
    ```
- Success/failure:
  - Result = Properties.result
  - Connection Success Rate = countif(Result == 'Succeeded') / count()
- Feature bucketing:
  - EventNameShort = split(EventName, '/')[1]
  - case() mapping to Feature in { model | agent | other }

### Cross-cluster/DB & Sharding
- Only one cluster/database is referenced. If your environment is sharded:
  - Use cluster()/database() qualification and union the shards with normalization:
    ```kusto
    union isfuzzy=true
      (cluster('<clusterA>').database('<db>').ai_foundry_vsc),
      (cluster('<clusterB>').database('<db>').ai_foundry_vsc)
    | extend OS = tostring(Properties['common.os'])
    | project-rename TimeCol = ClientTimestamp
    | summarize count() by bin(TimeCol, 1d), OS
    ```
- Order matters: union → normalize keys/time → summarize.

### Table classes
- ai_foundry_vsc: Fact (event telemetry). It is not a snapshot and not pre-aggregated.
  - Use for event counts, DAU/WAU/MAU, funnels, error/success rates.
  - Avoid cost analytics; no price mapping is present.

## Entity & Counting Rules (Core Definitions)

- Entity model:
  - Machine (proxy for user) → VSCodeMachineId
  - Event (feature/step) → EventName, EventNameShort, Feature
- Standard grouping levels:
  - Daily trends: bin(ClientTimestamp, 1d)
  - User activity/retention: distinct VSCodeMachineId by day (ServerTimestamp-based days in rolling-28 patterns); DAU dcount(VSCodeMachineId)
  - Feature-level analysis: group by Feature or EventNameShort
- Business definitions observed:
  - Connection Success Rate:
    - Definition: round((countif(Result == 'Succeeded') * 100.0) / count(), 2)
    - Apply optionally by whole set or by EventNameShort or Feature.
  - Active/Engaged/Dedicated (rolling-28 window; ServerTimestamp day domain):
    - Compute DaysSeenInPrev28 per user as count of distinct days in the last 28 days.
    - Active1d: dcount(VSCodeMachineId) [any user with >= 1 day in the window]
    - Engaged2d: dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 2)
    - Dedicated10d: dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 10)
- Counting Do/Don’t:
  - Do keep time domain consistent: if you compute “days seen,” stay in ServerTimestamp day domain for the entire metric.
  - Don’t mix ClientTimestamp and ServerTimestamp in a single metric unless the method clearly requires and explains it.
  - Do exclude activation/info noise events by default.
  - Don’t treat VSCodeMachineId as a unique person; it’s a machine proxy.

## Canonical Tables

### Table name: ai_foundry_vsc
- Cluster: https://kustoproxytest.azure-api.net/rentu-test-product/teamsfx
- Database: vscode-ext-aggregate
- Priority: Normal

- What this table represents:
  - Event telemetry fact table for the VS Code AI Foundry extension.
  - Each row is a client-side event; not a snapshot or aggregate.
  - Zero rows in a time window generally implies no usage/events emitted (not table deletion).

- Freshness expectations:
  - Time is typically filtered on ClientTimestamp; some analyses also use ServerTimestamp for daily bucketing.
  - Timezone is unknown. Be consistent when mixing ClientTimestamp vs ServerTimestamp to avoid off-by-one-day issues.
  - Ingestion delay is unknown; use conservative windows and avoid “today” until you verify lateness.

- When to use / When to avoid:
  - Use:
    - Counting feature usage and unique machines by event (EventName/EventNameShort).
    - DAU/WAU/MAU or rolling-28 activity based on VSCodeMachineId.
    - Funnels by mapping events into steps (e.g., model vs agent flows).
    - Success rate and error rate using Properties.result and Properties.errormessage.
    - OS breakdowns via Properties['common.os'].
  - Avoid:
    - Financial/cost analytics (no price/usage mapping here).
    - Identity-level user analytics (VSCodeMachineId is a machine proxy, not a person).
    - Real-time dashboards on same-day data (ingestion delay unknown).
    - Mixing ClientTimestamp and ServerTimestamp in the same metric without a clear rule.

- Similar tables & how to choose:
  - No sibling tables are documented in this dataset. If your environment shards across clusters/databases, use union across the shard set; otherwise query this table directly.

- Common Filters:
  - Time: ClientTimestamp between(_startTime .. _endTime).
  - Event exclusions: EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info').
  - OS selection: OS = tostring(Properties['common.os']) and OS in (['win32','darwin','linux'] or the provided INPUT_OS).
  - Result filter: Properties.result == 'Succeeded' (or != for failures).
  - Feature bucketing: derive EventNameShort = split(EventName, '/')[1], then map groups to “model” or “agent”.

- Table columns:
  Note: We attempted to fetch the authoritative schema via the adx-mcp-server get_table_schema/getschema, but the table was not resolvable from the configured product endpoint. The following columns are inferred from the provided queries and should be verified in your cluster.

  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | EventName         | string   | Full event name emitted by the extension (e.g., 'teamsdevapp.vscode-ai-foundry/…'). Used to derive EventNameShort. |
  | ClientTimestamp   | datetime | Client-side event timestamp. Primary filter for time windows in dashboards. |
  | ServerTimestamp   | datetime | Service-side ingestion/processing timestamp. Often used for date bucketing in daily/rolling metrics. |
  | ExtensionVersion  | string   | Version of the VS Code extension emitting the event. Useful for release impact. |
  | VSCodeMachineId   | string   | Anonymous machine identifier; used as the user key for dcount/retention. |
  | Properties        | dynamic  | JSON bag of event properties. Common fields: result (e.g., 'Succeeded'), errormessage, 'common.os' (e.g., 'win32','darwin','linux'). |

- Column Explain:
  - EventName:
    - Use when you need the canonical event path or to derive EventNameShort = split(EventName, '/')[1].
    - Common for grouping and mapping events to funnel steps or features (e.g., “model” vs “agent”).
  - ClientTimestamp:
    - Use for time range filters and binning for DAU/WAU and trend charts.
    - Prefer consistent use across a query to avoid mixing time domains.
  - ServerTimestamp:
    - Use when building day-based distinct counts with startofday(ServerTimestamp), especially in retention/rolling-28 patterns seen in queries.
    - Keep consistent with ClientTimestamp or clearly separate analyses.
  - VSCodeMachineId:
    - Primary entity for user-level metrics: dcount(VSCodeMachineId) for DAU, engaged users, retention.
    - Join key for segmenting users by steps/features.
  - ExtensionVersion:
    - Use to compare behavior/health between releases.
  - Properties (dynamic):
    - result: For success-rate calculations (e.g., countif(Properties.result == 'Succeeded')/count()).
    - errormessage: For top error diagnostics and categorization.
    - 'common.os': For OS filtering and breakdowns; typical values include 'win32', 'darwin', 'linux'.

- Practical usage notes:
  - Default filters:
    - Always include a bounded time range on ClientTimestamp.
    - Exclude activation/info noise events unless specifically needed.
    - Apply OS filter if the dashboard or scenario expects it.
  - Feature mapping:
    - Map EventNameShort sets to “model” and “agent” as shown in views to keep analyses consistent.
  - Scaling queries:
    - Start with narrower time windows and top N aggregations (e.g., top 10 errors) before expanding.
  - Current-day caution:
    - Refresh delay and timezone are unknown; avoid assuming complete data for today.

## Views (Reusable Layers)

- View: base
  - Purpose: Define the core filtered and augmented event set for downstream metrics with time window, OS, event exclusions, and feature mapping.
  - Inputs: ai_foundry_vsc; Parameters: _startTime, _endTime, and INPUT_OS (dashboard token written as ['INPUT_OS']).
  - Outputs: Columns EventName, ClientTimestamp, ExtensionVersion, VSCodeMachineId, Properties, EventNameShort, Result, ErrorMessage, OS, Feature.
  - Dependencies: Directly used by many queries as the starting dataset.
  - Full definition:
    ```kusto
    // Please enter your KQL query (Example):
    // <table name>
    // | where <datetime column> between (['_startTime'] .. ['_endTime']) // Time range filtering
    // | take 100
    let end_date = _endTime;
    let start_date = _startTime;
    let baseQuery = ai_foundry_vsc
    | where ClientTimestamp between(start_date .. end_date)
    | where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
    | project
        EventName,
        ClientTimestamp,
        ExtensionVersion,
        VSCodeMachineId,
        Properties
    | extend EventNameShort = tostring(split(EventName, '/')[1])
    | extend Result = Properties.result
    | extend ErrorMessage = Properties.errormessage
    | extend OS = tostring(Properties['common.os'])
    | where OS in (['INPUT_OS'])
    | extend Feature = case(  
        EventNameShort in ( 
            'azure-ai-foundry.commandpalette.llmdeploy',
             'azure-ai-foundry.viewcontext.llmdeploy',
             'model.update',
             'model.delete',
             'azure-ai-foundry.viewcontext.viewmodel',
             'azure-ai-foundry.viewcontext.model.openinplayground',
             'azure-ai-foundry.viewcontext.opencodefile',
             'azure-ai-foundry.commandpalette.opencodefile',
             'azure-ai-foundry.commandpalette.opencatalog'), "model",  
        EventNameShort in (
            'azure-ai-foundry.editortitle.openagentdesigner',
            'azure-ai-foundry.explorercontext.openagentdesigner',
            'azure-ai-foundry.commandpalette.runagent',
            'azure-ai-foundry.viewcontext.agent.delete',
            'azure-ai-foundry.viewcontext.createagent',
            'agentdesignerwebview.openyamlfile',
            'agentdesignerwebview.openplayground',
            'agentdesignerwebview.synctofile',
            'agentdesignerwebview.deployagent',
            'agentdesignerwebview.savetolocal',
            'azure-ai-foundry.viewcontext.openagentdesigner',
            'agentdesignerwebview.addtool',
            'agentroottreenode.getchildren',
            'playgroundwebview.createthread',
            'project.sendmessage'), "agent",  
        "other"  
      );
    baseQuery
    ```
  - Runnable tip: If you want to reuse it as “base”, define and return a symbol named base:
    ```kusto
    let INPUT_OS = dynamic(['win32','darwin','linux']);
    let _endTime = endofday(ago(1d));
    let _startTime = _endTime - 30d;
    let base = ai_foundry_vsc
    | where ClientTimestamp between(_startTime .. _endTime)
    | where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
    | extend EventNameShort = tostring(split(EventName, '/')[1]),
             Result = Properties.result,
             ErrorMessage = Properties.errormessage,
             OS = tostring(Properties['common.os'])
    | where OS in (INPUT_OS)
    | extend Feature = case(
        EventNameShort in ('azure-ai-foundry.commandpalette.llmdeploy','azure-ai-foundry.viewcontext.llmdeploy','model.update','model.delete','azure-ai-foundry.viewcontext.viewmodel','azure-ai-foundry.viewcontext.model.openinplayground','azure-ai-foundry.viewcontext.opencodefile','azure-ai-foundry.commandpalette.opencodefile','azure-ai-foundry.commandpalette.opencatalog'), 'model',
        EventNameShort in ('azure-ai-foundry.editortitle.openagentdesigner','azure-ai-foundry.explorercontext.openagentdesigner','azure-ai-foundry.commandpalette.runagent','azure-ai-foundry.viewcontext.agent.delete','azure-ai-foundry.viewcontext.createagent','agentdesignerwebview.openyamlfile','agentdesignerwebview.openplayground','agentdesignerwebview.synctofile','agentdesignerwebview.deployagent','agentdesignerwebview.savetolocal','azure-ai-foundry.viewcontext.openagentdesigner','agentdesignerwebview.addtool','agentroottreenode.getchildren','playgroundwebview.createthread','project.sendmessage'), 'agent',
        'other'
    );
    base
    ```

- View: base_error
  - Purpose: Filter out certain error categories after light categorization, producing a cleaned error-focused dataset.
  - Inputs: base
  - Outputs: base columns plus ErrorCategory; excludes categories in ('host','user','data').
  - Dependencies: Used by success-rate and error breakdown queries.
  - Full definition:
    ```kusto
    // Please enter your KQL query (Example):
    // <table name>
    // | where <datetime column> between (['_startTime'] .. ['_endTime']) // Time range filtering
    // | take 100
    base
    | extend ErrorCategory='uncategorized'
    | extend ErrorCategory=case(ErrorMessage == "Operation cancelled.", "user", ErrorCategory)
    | where ErrorCategory !in ('host','user', 'data')
    ```

## Query Building Blocks (Copy-paste snippets)

- Time window template
  ```kusto
  // Use effective end time to avoid partial same-day ingestion
  let _endTime = endofday(ago(1d));
  let _startTime = _endTime - 30d;
  let INPUT_OS = dynamic(['win32','darwin','linux']);
  ai_foundry_vsc
  | where ClientTimestamp between (_startTime .. _endTime)
  | extend OS = tostring(Properties['common.os'])
  | where OS in (INPUT_OS)
  ```

- Join template (step mapping)
  ```kusto
  // 1) Build event→step mapping
  let stepEvents = datatable(step: string, events: dynamic)
  [
    "Choose a project", dynamic(["azure-ai-foundry.commandpalette.setdefault","azure-ai-foundry.commandpalette.createproject","azure-ai-foundry.viewcontext.openinfoundryview","azure-ai-foundry.viewcontext.switchdefaultproject"]),
    "Deploy a model", dynamic(["azure-ai-foundry.commandpalette.llmdeploy","azure-ai-foundry.viewcontext.llmdeploy"]),
    "Open Playground - Model", dynamic(["azure-ai-foundry.viewcontext.model.openinplayground"]),
    "Open Code file - Model", dynamic(["azure-ai-foundry.commandpalette.opencodefile","azure-ai-foundry.viewcontext.opencodefile"]),
    "Deploy an agent", dynamic(["agentdesignerwebview.deployagent"]),
    "Open Playground - Agent", dynamic(["agentdesignerwebview.openplayground","playgroundwebview.initialize"])
  ];
  let eventToStep = stepEvents | mv-expand events | project step, event = tostring(events);
  // 2) Prepare events (from base)
  base
  | distinct event = EventNameShort, uid = VSCodeMachineId, result = tostring(Result)
  | join kind=inner (eventToStep) on $left.event == $right.event
  | distinct step, uid, result
  | summarize users = dcount(uid) by step, result
  ```

- Rolling-28 activity (Active / Engaged / Dedicated)
  ```kusto
  let INPUT_OS = dynamic(['win32','darwin','linux']);
  let DayRange = range Day from startofday(ago(60d)) to ago(1d) step 1d
               | extend DayEndDate = startofday(Day), dummy = 1;
  let UserDays =
    ai_foundry_vsc
    | where EventName !in ('teamsdevapp.vscode-ai-foundry/activate','teamsdevapp.vscode-ai-foundry/info')
    | extend OS = tostring(Properties['common.os'])
    | where OS in (INPUT_OS)
    | project VSCodeMachineId, Date = startofday(ServerTimestamp)
    | distinct VSCodeMachineId, Date
    | extend dummy = 1;
  DayRange
  | join kind=inner (UserDays) on dummy
  | project-away dummy, dummy1
  | where Date between ((DayEndDate - 27d) .. DayEndDate)
  | summarize DaysSeenInPrev28 = count() by VSCodeMachineId, DayEndDate
  | summarize Active1d = dcount(VSCodeMachineId),
              Engaged2d = dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 2),
              Dedicated10d = dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 10)
              by DayEndDate
  ```

- De-dup pattern
  ```kusto
  // Distinct entity-date or entity-event
  | distinct VSCodeMachineId, Date
  // Or a last-record per key example if needed:
  // | summarize arg_max(ClientTimestamp, *) by VSCodeMachineId
  ```

- Important filters (defaults)
  ```kusto
  // Exclude activation/info events
  | where EventName !in ('teamsdevapp.vscode-ai-foundry/activate','teamsdevapp.vscode-ai-foundry/info')
  // OS filter (dashboard token form)
  | where OS in (['INPUT_OS'])
  // OS filter (ad-hoc form)
  | where OS in (dynamic(['win32','darwin','linux']))
  // Success only
  | where Result == 'Succeeded'
  ```

- ID parsing/derivation
  ```kusto
  // Derive EventNameShort from EventName path
  | extend EventNameShort = tostring(split(EventName, '/')[1])
  // Extract dynamic bag fields
  | extend Result = Properties.result,
           ErrorMessage = Properties.errormessage,
           OS = tostring(Properties['common.os'])
  ```

- Sharded union template (if applicable later)
  ```kusto
  union isfuzzy=true
    (cluster('<clusterA>').database('vscode-ext-aggregate').ai_foundry_vsc),
    (cluster('<clusterB>').database('vscode-ext-aggregate').ai_foundry_vsc)
  | extend OS = tostring(Properties['common.os'])
  | project-rename TimeCol = ClientTimestamp
  | summarize Events = count() by bin(TimeCol, 1d), OS
  ```

## Example Queries (with explanations)

1) Event popularity by EventNameShort
- Description: Uses the base view to count events grouped by EventNameShort. Adapt start/end time or OS cohort via the base parameters.
```kusto
base
| summarize EventCount = count() by EventNameShort
| order by EventCount desc;
```

2) Overall connection success rate (filtered errors)
- Description: Computes connection success rate after excluding certain error categories via base_error. Adjust time window and OS via base.
```kusto
let end_date = _endTime;
let start_date = _startTime;
base_error
| summarize ConnectionSuccessRate = round(((countif(Result == 'Succeeded') * 100.0) / count()), 2)
| project ConnectionSuccessRate, ['Connection success rate display'] = strcat(ConnectionSuccessRate, "%");
```

3) Connection success rate by EventNameShort
- Description: Same as above but broken down by EventNameShort to find weak/strong events. Sort ascending to spot low-success events.
```kusto
let end_date = _endTime;
let start_date = _startTime;
base_error
| summarize ConnectionSuccessRate = round(((countif(Result == 'Succeeded') * 100.0) / count()), 2) by EventNameShort
| project EventNameShort, ConnectionSuccessRate, ['Connection success rate display'] = strcat(ConnectionSuccessRate, "%")
| order by ConnectionSuccessRate asc;
```

4) Top 10 error messages (excluding successes)
- Description: Focuses on failures by ErrorMessage. Use this to prioritize fixes; OS and time filters inherited from base_error.
```kusto
let end_date = _endTime;
let start_date = _startTime;
base_error
| where Result != 'Succeeded'
| summarize Count = count() by tostring(ErrorMessage)
| project ErrorMessage, Count
| order by Count
| take 10;
```

5) Daily Active Users (DAU)
- Description: Distinct machines per day using ClientTimestamp. Change bin() to 7d for WAU, 30d for MAU-style trend proxies (with caution).
```kusto
base
| summarize DailyActiveUsers = dcount(VSCodeMachineId) by bin(ClientTimestamp, 1d);
```

6) Rolling-28 activity: Active/Engaged/Dedicated per day
- Description: Builds a day grid and counts how many days each machine appears in the trailing 28-day window (ServerTimestamp domain). Produces Active1d, Engaged2d, and Dedicated10d.
```kusto
let daterange = range Day from startofday(datetime(2025-03-01)) to ago(1d) step 1d  
| extend DayEndDate = startofday(Day)  
| extend dummy = 1;
let UserDays = ai_foundry_vsc  
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')  
| extend OS = tostring(Properties['common.os'])
| where OS in (['INPUT_OS'])
| project VSCodeMachineId, Date = startofday(ServerTimestamp)  
| distinct VSCodeMachineId, Date  
| extend dummy = 1;
daterange  
| join kind=inner (UserDays) on dummy  
| project-away dummy, dummy1
| where Date between ((DayEndDate - 27d) .. (DayEndDate))  
| summarize DaysSeenInPrev28 = count() by VSCodeMachineId, DayEndDate  
| summarize Active1d = dcount(VSCodeMachineId), Engaged2d = dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 2), Dedicated10d = dcountif(VSCodeMachineId, DaysSeenInPrev28 >= 10) by DayEndDate  
| where DayEndDate > datetime(2025-03-01);
```

7) Weekly Active users by Feature (model vs agent)
- Description: Produces weekly “Active1d” counts per Feature using a week grid cross-join and a 28-day trailing window. Uses ServerTimestamp days and Feature mapping. Adjust start date and OS as needed.
```kusto
let daterange = range Week from startofweek(datetime(2025-03-01)) to startofweek(ago(7d)) step 7d
| extend WeekEndDate = startofday(endofweek(Week))
| extend dummy = 1;
let UserDays = ai_foundry_vsc
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
| extend OS = tostring(Properties['common.os'])
| where OS in (['INPUT_OS'])
| project VSCodeMachineId, Date = startofday(ServerTimestamp), EventName
| distinct VSCodeMachineId, Date, EventName
| extend EventNameShort = tostring(split(EventName, '/')[1])
| extend Feature = case(  
    EventNameShort in ( 'azure-ai-foundry.commandpalette.llmdeploy','azure-ai-foundry.viewcontext.llmdeploy','model.update','model.delete','azure-ai-foundry.viewcontext.viewmodel','azure-ai-foundry.viewcontext.model.openinplayground','azure-ai-foundry.viewcontext.opencodefile','azure-ai-foundry.commandpalette.opencodefile','azure-ai-foundry.commandpalette.opencatalog'), "model",  
    EventNameShort in ( 'azure-ai-foundry.editortitle.openagentdesigner','azure-ai-foundry.explorercontext.openagentdesigner','azure-ai-foundry.commandpalette.runagent','azure-ai-foundry.viewcontext.agent.delete','azure-ai-foundry.viewcontext.createagent','agentdesignerwebview.openyamlfile','agentdesignerwebview.openplayground','agentdesignerwebview.synctofile','agentdesignerwebview.deployagent','agentdesignerwebview.savetolocal','azure-ai-foundry.viewcontext.openagentdesigner','agentdesignerwebview.addtool','agentroottreenode.getchildren','playgroundwebview.createthread','project.sendmessage'), "agent",  
    "other"  
  )
| extend dummy = 1;
daterange
| join kind=inner (UserDays) on dummy
| project-away dummy, dummy1
| where Date between ((WeekEndDate - 27d) .. (WeekEndDate))
| summarize DaysSeenInPrev28 = count() by VSCodeMachineId, WeekEndDate, Feature
| summarize Active1d = dcount(VSCodeMachineId) by WeekEndDate, Feature
| where WeekEndDate > datetime(2025-03-01) and Feature in ("model", "agent");
```

8) Step funnel: succeeded users per step
- Description: Maps EventNameShort to funnel steps and counts distinct machines per step for successful results only. Modify steps/events to fit new funnels.
```kusto
let stepEvents = datatable(step: string, events: dynamic)
[
    "Choose a project", dynamic(["azure-ai-foundry.commandpalette.setdefault", "azure-ai-foundry.commandpalette.createproject", "azure-ai-foundry.viewcontext.openinfoundryview", "azure-ai-foundry.viewcontext.switchdefaultproject"]),
    "Deploy a model", dynamic(["azure-ai-foundry.commandpalette.llmdeploy", "azure-ai-foundry.viewcontext.llmdeploy"]),
    "Open Playground - Model", dynamic(["azure-ai-foundry.viewcontext.model.openinplayground"]),
    "Open Code file - Model", dynamic(["azure-ai-foundry.commandpalette.opencodefile", "azure-ai-foundry.viewcontext.opencodefile"]),
    "Deploy an agent", dynamic(["agentdesignerwebview.deployagent"]),
    "Open Playground - Agent", dynamic(["agentdesignerwebview.openplayground", "playgroundwebview.initialize"]),
];
let eventToStep = stepEvents
| mv-expand events
| project step, event = tostring(events);
(
    base
    | where Result == "Succeeded"
    | distinct event = EventNameShort, uid = VSCodeMachineId
)
| join kind=inner 
( eventToStep )
on $left.event == $right.event
| distinct step, uid
| summarize users = dcount(uid) by step
| order by users desc;
```

9) Specific event DAU
- Description: Active machines per day among those who triggered a specific event (e.g., azure-ai-foundry.openinvscodeazure). Adjust event name and time window as needed.
```kusto
base  
| where EventNameShort == "azure-ai-foundry.openinvscodeazure"
| summarize UserCount = dcount(VSCodeMachineId) by bin(ClientTimestamp, 1d);
```

10) Monthly new-user cohort retention (M1–M6)
- Description: Computes first active month per machine and whether the machine returns in months 1–6 thereafter (ClientTimestamp day domain for first-seen logic). Useful for longer-term engagement trends.
```kusto
let endmonth = startofmonth(now() - 1d);
let baseQuery = ai_foundry_vsc
| where EventName !in ('teamsdevapp.vscode-ai-foundry/activate', 'teamsdevapp.vscode-ai-foundry/info')
| project EventName, ClientTimestamp, ExtensionVersion, VSCodeMachineId, Properties
| extend EventNameShort = tostring(split(EventName, '/')[1])
| extend Result = Properties.result
| extend ErrorMessage = Properties.errormessage
| extend OS = tostring(Properties['common.os'])
| extend Feature = case(  
    EventNameShort in ( 'azure-ai-foundry.commandpalette.llmdeploy','azure-ai-foundry.viewcontext.llmdeploy','model.update','model.delete','azure-ai-foundry.viewcontext.viewmodel','azure-ai-foundry.viewcontext.model.openinplayground','azure-ai-foundry.viewcontext.opencodefile','azure-ai-foundry.commandpalette.opencodefile','azure-ai-foundry.commandpalette.opencatalog'), "model",  
    EventNameShort in ( 'azure-ai-foundry.editortitle.openagentdesigner','azure-ai-foundry.explorercontext.openagentdesigner','azure-ai-foundry.commandpalette.runagent','azure-ai-foundry.viewcontext.agent.delete','azure-ai-foundry.viewcontext.createagent','agentdesignerwebview.openyamlfile','agentdesignerwebview.openplayground','agentdesignerwebview.synctofile','agentdesignerwebview.deployagent','agentdesignerwebview.savetolocal','azure-ai-foundry.viewcontext.openagentdesigner','agentdesignerwebview.addtool','agentroottreenode.getchildren','playgroundwebview.createthread','project.sendmessage'), "agent",  
    "other"  
  )
| extend eventDay = startofday(ClientTimestamp)
| distinct MachineId = VSCodeMachineId, Time = eventDay;
let active_day = baseQuery
| summarize ActiveDay = min(Time) by MachineId;
baseQuery
| join kind=inner active_day on MachineId
| extend m1 = iff(Time > ActiveDay and Time < datetime_add('month', 1, ActiveDay), 1, 0)
| extend m2 = iff(Time >= datetime_add('month', 1, ActiveDay) and Time < datetime_add('month', 2, ActiveDay), 1, 0)
| extend m3 = iff(Time >= datetime_add('month', 2, ActiveDay) and Time < datetime_add('month', 3, ActiveDay), 1, 0)
| extend m4 = iff(Time >= datetime_add('month', 3, ActiveDay) and Time < datetime_add('month', 4, ActiveDay), 1, 0)
| extend m5 = iff(Time >= datetime_add('month', 4, ActiveDay) and Time < datetime_add('month', 5, ActiveDay), 1, 0)
| extend m6 = iff(Time >= datetime_add('month', 5, ActiveDay) and Time < datetime_add('month', 6, ActiveDay), 1, 0)
| summarize max(m1), max(m2), max(m3), max(m4), max(m5), max(m6) by MachineId, ActiveMonth = startofmonth(ActiveDay)
| summarize m1 = sum(max_m1), m2 = sum(max_m2), m3 = sum(max_m3), m4 = sum(max_m4), m5 = sum(max_m5), m6 = sum(max_m6), all = count()
          by ActiveMonth
| order by ActiveMonth asc
| where datetime_add('month', 1, ActiveMonth) < endmonth
| project ["Month | NewUsers"] = strcat(format_datetime(ActiveMonth, "yyyy/MM"),"  |  ",all),
          ["Rate: M1"] = iff(datetime_add('month', 2, ActiveMonth) <= endmonth, round(m1 * 1.0 / all, 2), 0.0),
          ["M2"] = iff(datetime_add('month', 3, ActiveMonth) <= endmonth, round(m2 * 1.0 / all, 2), 0.0),
          ["M3"] = iff(datetime_add('month', 4, ActiveMonth) <= endmonth, round(m3 * 1.0 / all, 2), 0.0),
          ["M4"] = iff(datetime_add('month', 5, ActiveMonth) <= endmonth, round(m4 * 1.0 / all, 2), 0.0),
          ["M5"] = iff(datetime_add('month', 6, ActiveMonth) <= endmonth, round(m5 * 1.0 / all, 2), 0.0),
          ["M6"] = iff(datetime_add('month', 7, ActiveMonth) <= endmonth, round(m6 * 1.0 / all, 2), 0.0);
```

## Reasoning Notes (only if uncertain)

- Timezone: Not specified. Adopt UTC to avoid ambiguity; adjust only if your pipeline guarantees a different zone.
- Canonical time choice: ClientTimestamp for general trends; ServerTimestamp for rolling “days seen” to avoid client clock skew. Adopted based on patterns in provided queries.
- OS cohort parameter: Dashboard uses OS in (['INPUT_OS']); for ad-hoc queries we recommend let INPUT_OS = dynamic([...]) and OS in (INPUT_OS) to be runnable.
- Feature mapping: Derived strictly from EventNameShort sets shown; no other categories inferred. Adopted as-is.
- Error categorization: Only explicit rule maps “Operation cancelled.” to user, then filters out host/user/data to leave remaining errors. Adopted as-is; other categories are unknown.
- Daily vs weekly windows: Weekly queries materialize WeekEndDate and still use a 28d backward window; this is a design choice to align weekly reporting to a standard comparable trailing window. Adopted as provided.
- Identity: VSCodeMachineId represents a machine proxy; we avoid person-level claims. Adopted conservatively.
- Completeness gates: Not present explicitly; we propose OS-slice-based gating as a safe pattern when needed.