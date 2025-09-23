# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

VS Code Java Upgrade is a Visual Studio Code extension workflow that guides developers through upgrading Java versions and dependencies within their projects. This template captures data sources, key identifiers, and Kusto analytics playbook to enable PMAgent to correctly interpret and analyze product-specific telemetry.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
VS Code Java Upgrade
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
https://ddtelvscode.kusto.windows.net/
- **Kusto Database**:
VSCodeExt
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# VS Code Java Upgrade - Kusto Query Playbook

## Overview
- Product: VS Code Java Upgrade
- Summary: Kusto dashboard for VS Code Java Upgrade with multiple pages, tiles, base queries, and parameters.
- Cluster: https://ddtelvscode.kusto.windows.net/
- Database: VSCodeExt

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - ServerTimestamp (primary event timestamp)
  - startTime is aliased from ServerTimestamp in the `result` view
- Canonical Time Column: ServerTimestamp
- Alias pattern:
  - Use project-rename or extend when aligning time fields
  - Example: extend startTime = ServerTimestamp
- Typical time windows:
  - Parameterized range: ServerTimestamp between (['_startTime'] .. ['_endTime'])
  - Many queries do not use bin(); if aggregation by time is needed, default to bin(ServerTimestamp, 1d)
- Timezone: Unknown. Treat timestamps as UTC and avoid same-day data unless you validate completeness.

### Freshness & Completeness Gates
- Ingestion cadence: Unknown.
- Current day can be incomplete: Unknown. Recommended pattern:
  - Prefer previous complete day/week when building KPIs.
  - Use an effective end time gate based on last complete slice across key events.

Example completeness gate pattern:
```kusto
// Effective end time: last day with both confirm and openrewrite end events present
let lastCompleteDay =
    toscalar(
        database("VSCodeExt").RawEventsVSCodeExt
        | where ExtensionName == "vscjava.vscode-java-upgrade"
        | summarize hasConfirm = countif(EventName == "vscjava.vscode-java-upgrade/confirmplan.end"),
                    hasOpenRewrite = countif(EventName == "vscjava.vscode-java-upgrade/openrewrite.end")
                  by day = startofday(ServerTimestamp)
        | where hasConfirm > 0 and hasOpenRewrite > 0
        | summarize arg_max(day, *)
        | project day
    );
database("VSCodeExt").RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| where ServerTimestamp between (['_startTime'] .. datetime_add("day", 1, lastCompleteDay))
```

### Joins & Alignment
- Frequent keys:
  - DevDeviceId (device/user key)
  - VSCodeMachineId (machine key)
  - VSCodeSessionId (VS Code session key)
  - sessionId (feature-level session id from Properties["sessionid"])
  - EventName (event type)
  - ExtensionVersion, majorVersion, minorVersion
- Typical join kinds:
  - inner to constrain cohorts (e.g., link to fact_user_isinternal)
  - leftouter when enriching while preserving base rows (e.g., build result classification)
  - leftantisemi when excluding matches (e.g., remove failed sessions)
- Post-join hygiene:
  - Resolve column collisions via project-rename or use join-scoped names (e.g., sessionId1, sessionId2)
  - Use coalesce() when combining alternative sources
  - Drop unused columns with project-away after joins

### Filters & Idioms
- Core predicates:
  - has, startswith, in, between, isempty(), isnotempty()
- Standard filters seen:
  - ExtensionName == "vscjava.vscode-java-upgrade"
  - tostring(Properties["sessionid"]) != "MOCKSESSION"
  - majorVersion > 0 or minorVersion >= 10
  - Internal user gating via IsInternal (parameterized)
- Cohort construction:
  - Build allowlists with distinct/summarize and join kind=inner
  - Use leftouter to annotate optional features, leftantisemi to exclude error cohorts

### Cross-cluster/DB & Sharding
- Cross-database qualification:
  - database("VSCodeExt").RawEventsVSCodeExt
  - database("VSCodeInsights").fact_user_isinternal
- Sharding: Not explicitly present. If regional shards exist with identical schemas, union then normalize, then aggregate.

Union + normalize pattern (template):
```kusto
union
    cluster("YourCluster").database("VSCodeExt").RawEventsVSCodeExt,
    cluster("YourClusterEU").database("VSCodeExt").RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| extend sessionId = tostring(Properties["sessionid"])
| summarize dcount(sessionId) by EventName
```

### Table classes
- Fact/events:
  - VSCodeExt.RawEventsVSCodeExt (event stream with Properties/Measures; use for sessions, counts, funnels)
- Dimension/snapshot:
  - VSCodeInsights.fact_user_isinternal (maps DevDeviceId to IsInternal; use for cohort gating)

### Usage Guidance and Patterns
- Time window and scoping:
  - Always apply ServerTimestamp time filters.
  - Scope to ExtensionName == "vscjava.vscode-java-upgrade".
  - Exclude MOCKSESSION for session hygiene: tostring(Properties["sessionid"]) != "MOCKSESSION".
- Deriving fields from dynamic data:
  - SessionId: extend sessionId = tostring(Properties["sessionid"]).
  - Versions: derive major/minor with split(ExtensionVersion, ".", ...), cast using toint().
  - Error messages: error = tostring(Properties["errormessage"]); categorize via case(...).
  - Tokens: toint(Measures["tokens"]), prompt/completion token extracts; summarize for averages/percentiles.
- Success/failure classification:
  - OpenRewrite: Properties["result"] == "succeed"/"failed".
  - BuildFix: Properties["result"] == "true" => Succeeded; else failure.
  - CVE validation: Properties["cves"] empty => passed.
  - Consistency validation: Measures["behaviorchangescount"] == 0 and Measures["brokenfilescount"] == 0 => passed.
- Conservative defaults:
  - Use narrow time windows (e.g., last 7–14 days) before expanding.
  - Start with top N or percentiles to avoid scanning entire datasets.
  - When computing funnels, prefer distinct sessionId and dcount(VSCodeMachineId) to avoid double-counting.
- Cross-source agent analytics within RawEventsVSCodeExt:
  - GitHub Copilot Chat events:
    - Request: EventName == "github.copilot-chat/panel.request" with Properties["toolcounts"] has "javaupgrade".
    - Response: EventName == "github.copilot-chat/response.success" with Measures["tokencount"] for token usage.
  - Correlate by VSCodeSessionId and ConversationId / RequestId.
- Example schema check (run in ADX if needed):
```kusto
cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt | getschema
cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal | getschema
```
- Notes:
  - Refresh delay/timezone: Not provided; unknown.
  - Usage-to-cost mapping: Not provided; if you cost tokens, convert with a placeholder rate (e.g., <UnitPriceToken>) outside of KQL.

## Entity & Counting Rules (Core Definitions)
- Entity tiers and keys:
  - User/device: DevDeviceId (primary in many counts)
  - Machine: VSCodeMachineId (alternate counting key)
  - VS Code session: VSCodeSessionId (IDE-level session)
  - Feature session: sessionId from Properties (feature-level). Adopted for workflow funnels and outcomes.
- Standard grouping:
  - By EventName for step metrics
  - By sessionId for per-session funnels and outcomes
  - By DevDeviceId or VSCodeMachineId for unique user counts
  - By ExtensionVersion / majorVersion / minorVersion for version breakdowns
- Business definitions (present in input, do not apply by default):
  - Result classification (view result):
    - Succeeded: buildfix.end with Properties["result"] == "true"
    - OpenResultFailed: openrewrite.end with Properties["result"] == "failed"
    - BuildFixFailed: buildfix.end with Properties["result"] != "true"
    - Incomplete: no definitive result signals joined
  - CVE Validation Passed: validatecves.end with empty cves
  - Consistency Validation Passed: validatecodebehaviorconsistency.end with behaviorChangesCount == 0 and brokenFilesCount == 0

## Views (Reusable Layers)

### raw
Purpose: Base filtered event stream for the Java Upgrade extension with session/user cohort gating and version parsing.
Dependencies: Directly used by most queries; other views depend on it.
Inputs: VSCodeExt.RawEventsVSCodeExt, VSCodeInsights.fact_user_isinternal
Outputs: Adds sessionId, majorVersion, minorVersion fields; filters by ExtensionName, time, version, and user type.

Full definition:
```kusto
let base = database("VSCodeExt").RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| where tostring(Properties["sessionid"]) != "MOCKSESSION"
| where ServerTimestamp  between (['_startTime'] .. ['_endTime']) // Time range filtering
| extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]), minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
| where majorVersion > 0 or minorVersion >=10
| join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId;
base
| where isempty(['_versions']) or ExtensionVersion in (['_versions']) // Multiple selection filtering
// regrad all users before code complete as internal users
| where isempty( ['_user_types']) or IsInternal in ( ['_user_types'])
| extend sessionId = tostring(Properties["sessionid"])
```

### result
Purpose: Classifies session outcomes (Succeeded, BuildFixFailed, OpenResultFailed, Incomplete) for funnels and success metrics.
Dependencies: Uses raw.
Outputs: result, version, startTime, majorVersion, minorVersion.

Full definition:
```kusto
let all = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| distinct VSCodeMachineId, startTime = ServerTimestamp, sessionId, majorVersion, minorVersion;
let openRewriteFailedResults = raw
| where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "failed"
| distinct VSCodeMachineId, sessionId, majorVersion, minorVersion
| project sessionId, orResult = "OpenResultFailed";
let buildFixResult = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end"
| extend buildResult = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")
| distinct VSCodeMachineId, sessionId, majorVersion, minorVersion, buildResult
| project sessionId, buildResult;
all
| join kind=leftouter openRewriteFailedResults on sessionId
| join kind=leftouter buildFixResult on sessionId
| extend result = case(isnotempty( buildResult), buildResult, isnotempty(orResult), orResult, "Incomplete")
| project VSCodeMachineId, startTime, sessionId, result, majorVersion, minorVersion, version = strcat(majorVersion, ".", minorVersion);
```

### updatedependencies
Purpose: Extracts dependency upgrade pairs from plan-started events for migration analysis.
Dependencies: Uses raw.
Outputs: dependency, source version, target version, session.

Full definition:
```kusto
raw
| where EventName == "vscjava.vscode-java-upgrade/javaupgrade.planstarted"
| extend dependencies = parse_json(tostring(Properties["updateddependencies"])), session = tostring(Properties["sessionid"])
| project dependencies, session
| mv-expand dependencies
| project dependency = tostring(dependencies["source"]["id"]), source=tostring(dependencies["source"]["version"]), target=tostring(dependencies["target"]["version"]), session;
```

### compileFailedSessions
Purpose: Identifies sessions that did not fail due to OpenRewrite but had early task failures (task 1), used for debugging pipeline issues.
Dependencies: Uses raw.
Outputs: sessionId cohort to exclude.

Full definition:
```kusto
let openrewriteFailed = raw
| extend outputMessage = tostring(Properties["output.message"])
| extend sessionid = tostring(Properties["sessionid"])
| where outputMessage has "Failed to run OpenRewrite"
| distinct sessionId;
let failedTask1 = raw
| extend taskId = tostring(Properties["taskid"])
| extend task = toint(split(taskId, ".", 0)) , subTask = toint(split(taskId, ".", 1))
| where isnotempty(subTask)
| summarize max(task) by sessionId
| where max_task == 1
| distinct sessionId;
failedTask1
| join kind=leftantisemi openrewriteFailed on sessionId;
```

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Apply a parameterized time range with an effective end time gate to avoid partial current-day data.
  - Snippet:
    ```kusto
    // Set explicit time window and avoid partial current-day by capping at last complete day
    let startTime = datetime(2025-08-01);
    let endTime = now();
    let effectiveEnd =
        toscalar(
            database("VSCodeExt").RawEventsVSCodeExt
            | where ExtensionName == "vscjava.vscode-java-upgrade"
            | summarize by day = startofday(ServerTimestamp)
            | summarize arg_max(day, *)
            | project datetime_add("day", 1, day)
        );
    database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where ServerTimestamp between (startTime .. iff(effectiveEnd < endTime, effectiveEnd, endTime))
    ```

- Join template
  - Description: Standard alignment to internal-user dimension and outcome classification via session join.
  - Snippet:
    ```kusto
    // Align events to internal-user dimension
    let raw =
        database("VSCodeExt").RawEventsVSCodeExt
        | where ExtensionName == "vscjava.vscode-java-upgrade"
        | where ServerTimestamp between (['_startTime'] .. ['_endTime'])
        | extend sessionId = tostring(Properties["sessionid"]);
    raw
    | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
    | project-away IsInternal1 // if collision occurs
    // Outcome classification via leftouter join
    | join kind=leftouter (result) on sessionId
    | project-rename outcome = result
    ```

- De-dup pattern
  - Description: Get last event per session; use arg_max on canonical time.
  - Snippet:
    ```kusto
    // Last event per session by canonical time
    raw
    | summarize arg_max(ServerTimestamp, *) by sessionId
    ```

- Important filters
  - Description: Standard filters for valid sessions, versions, extension scope, and cohort selection.
  - Snippet:
    ```kusto
    database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where tostring(Properties["sessionid"]) != "MOCKSESSION"
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]), minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion > 0 or minorVersion >= 10
    | where isempty(['_versions']) or ExtensionVersion in (['_versions'])
    | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
    | where isempty(['_user_types']) or IsInternal in (['_user_types'])
    ```

- Important Definitions
  - Description: Reuse result classification and validation pass criteria.
  - Snippet:
    ```kusto
    // Build Fix outcome
    | extend buildResult = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")

    // OpenRewrite failure
    | extend orResult = iff(Properties["result"] == "failed", "OpenResultFailed", "")

    // CVE Validation Passed
    | extend cvePassed = isempty(tostring(Properties["cves"]))

    // Consistency Validation Passed
    | extend behaviorChangesCount = toint(Measures["behaviorchangescount"]),
             brokenFilesCount = toint(Measures["brokenfilescount"]),
             consistencyPassed = behaviorChangesCount == 0 and brokenFilesCount == 0
    ```

- ID parsing/derivation
  - Description: Normalize session ids and extract sub-fields from structured properties.
  - Snippet:
    ```kusto
    // Feature session id
    | extend sessionId = tostring(Properties["sessionid"])

    // Split task id into task/sub-task
    | extend taskId = tostring(Properties["taskid"]),
             task = toint(split(taskId, ".", 0)),
             subTask = toint(split(taskId, ".", 1))

    // Parse updated dependencies
    | extend dependencies = parse_json(tostring(Properties["updateddependencies"]))
    | mv-expand dependencies
    | project dependency = tostring(dependencies["source"]["id"]),
              source = tostring(dependencies["source"]["version"]),
              target = tostring(dependencies["target"]["version"])
    ```

- Sharded union
  - Description: If identical schemas exist across clusters/databases, union them, then normalize and summarize.
  - Snippet:
    ```kusto
    union
      cluster("<PrimaryCluster>").database("VSCodeExt").RawEventsVSCodeExt,
      cluster("<AltCluster>").database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | extend sessionId = tostring(Properties["sessionid"])
    | summarize sessions = dcount(sessionId) by EventName
    ```

## Example Queries (with explanations)

1) Upgrade Funnel (by unique user)
- Description: Computes session and user coverage across ordered upgrade steps. It builds a canonical event order, filters operations from raw, calculates total unique sessions/users, and computes percentages per step. Adapting: change time window via raw view parameters; edit eventOrder and noSessionEvents as needed.
```kusto
let eventOrder = dynamic([
    "vscjava.vscode-java-upgrade/generateplan.prepare",
    "vscjava.vscode-java-upgrade/generateplan.start",
    "vscjava.vscode-java-upgrade/generateplan.end",
    "vscjava.vscode-java-upgrade/confirmplan.prepare",
    "vscjava.vscode-java-upgrade/confirmplan.start",
    "vscjava.vscode-java-upgrade/confirmplan.end",
    "vscjava.vscode-java-upgrade/openrewrite.prepare",
    "vscjava.vscode-java-upgrade/openrewrite.start",
    "vscjava.vscode-java-upgrade/openrewrite.end",
    "vscjava.vscode-java-upgrade/buildfix.prepare",
    "vscjava.vscode-java-upgrade/buildfix.start",
    "vscjava.vscode-java-upgrade/buildfix.end",
    "vscjava.vscode-java-upgrade/validatecves.prepare",
    "vscjava.vscode-java-upgrade/validatecves.start",
    "vscjava.vscode-java-upgrade/validatecves.end",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.prepare",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end",
    "vscjava.vscode-java-upgrade/summarizechanges.start",
    "vscjava.vscode-java-upgrade/summarizechanges.prepare",
    "vscjava.vscode-java-upgrade/summarizechanges.end"
]);
let noSessionEvents = dynamic(["vscjava.vscode-java-upgrade/generateplan.start", "vscjava.vscode-java-upgrade/generateplan.prepare", "vscjava.vscode-java-upgrade/generateplan.end"]);
let operations = raw
| extend session = tostring(Properties["sessionid"])
| where EventName in (
    "vscjava.vscode-java-upgrade/validatecves.start",
    "vscjava.vscode-java-upgrade/validatecves.prepare",
    "vscjava.vscode-java-upgrade/validatecves.end",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.prepare",
    "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end",
    "vscjava.vscode-java-upgrade/summarizechanges.start",
    "vscjava.vscode-java-upgrade/summarizechanges.prepare",
    "vscjava.vscode-java-upgrade/summarizechanges.end",
    "vscjava.vscode-java-upgrade/openrewrite.start",
    "vscjava.vscode-java-upgrade/openrewrite.prepare",
    "vscjava.vscode-java-upgrade/openrewrite.end",
    "vscjava.vscode-java-upgrade/generateplan.start",
    "vscjava.vscode-java-upgrade/generateplan.prepare",
    "vscjava.vscode-java-upgrade/generateplan.end",
    "vscjava.vscode-java-upgrade/confirmplan.start",
    "vscjava.vscode-java-upgrade/confirmplan.prepare",
    "vscjava.vscode-java-upgrade/confirmplan.end",
    "vscjava.vscode-java-upgrade/buildproject.start",
    "vscjava.vscode-java-upgrade/buildproject.prepare",
    "vscjava.vscode-java-upgrade/buildproject.end",
    "vscjava.vscode-java-upgrade/buildfix.start",
    "vscjava.vscode-java-upgrade/buildfix.prepare",
    "vscjava.vscode-java-upgrade/buildfix.end"
);
let totalUser = toscalar(operations | summarize dcount(VSCodeMachineId));
let totalSession = toscalar(operations | summarize dcount(session));
operations
| summarize sessionCount = dcount(session), userCount = dcount(VSCodeMachineId) by EventName
| extend orderIndex = array_index_of(eventOrder, EventName)
| project EventName,
    sessionPercentage = iff(EventName in (noSessionEvents), 100.0, round(todouble(sessionCount) / totalSession * 100.0, 2)), 
    sessionCount,
    userPercentage = round(todouble(userCount) / totalUser * 100.0, 2), 
    userCount,
    orderIndex
| where orderIndex >= 0
| order by orderIndex asc
| project EventName, 
    sessionCount = iff(EventName in (noSessionEvents), "N/A", tostring(sessionCount)), 
    sessionPercentage = iff(EventName in (noSessionEvents), "N/A", strcat(sessionPercentage, "%")), 
    userCount, 
    userPercentage = strcat(userPercentage, "%")
```

2) Build Tool Distribution
- Description: Distribution of sessions/users by build tool selected at confirmplan.end, joined with result to compute success rate. Adapting: filter by time via raw; change grouping keys.
```kusto
raw 
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend buildTool = tostring(Properties["buildtool"])
| distinct buildTool, sessionId
| join result on sessionId
| summarize totalSession = dcount(sessionId), succeededSession = dcountif(sessionId, result  == "Succeeded"),
 totalUser = dcount(VSCodeMachineId), succeededUser = dcountif(VSCodeMachineId, result  == "Succeeded") by buildTool
| project buildTool, succeededSession, totalSession, ["succeedRate (%)"] = round(succeededSession * 1.0 / totalSession, 4) * 100 
```

3) Migration Distribution (source→target Java versions)
- Description: Distribution of migrations by source/target versions at confirmplan.end, with success rates. Adapting: adjust time window; add filtering for cohorts.
```kusto
raw 
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend sourceVersion = toint(Properties["sourcejavaversion"]), targetVersion = toint(Properties["targetjavaversion"])
| distinct sourceVersion, targetVersion, sessionId
| join result on sessionId
| summarize totalSession = dcount(sessionId), succeededSession = dcountif(sessionId, result  == "Succeeded"),
 totalUser = dcount(VSCodeMachineId), succeededUser = dcountif(VSCodeMachineId, result  == "Succeeded") by sourceVersion, targetVersion
| project sourceVersion, targetVersion, succeededSession, totalSession, ["succeedRate (%)"] = round(succeededSession * 1.0 / totalSession, 4) * 100 
```

4) Upgrade Result By Version (percent composition)
- Description: Computes percent composition of outcomes per extension version by joining per-version totals with outcome counts. Adapting: restrict versions via _versions.
```kusto
let toal = result | summarize all = dcount(sessionId) by majorVersion, minorVersion;
result
| summarize stateCount = dcount(sessionId) by result, majorVersion, minorVersion
| join kind=inner toal on majorVersion, minorVersion
| project Version = strcat(tostring(majorVersion), ".", tostring(minorVersion)),UpgradeState = result, Times = stateCount,Percentage = round(todouble(stateCount) / all * 100.0, 2)
| summarize Succeeded = sumif(Percentage, UpgradeState == "Succeeded"),
BuildFixFailed = sumif(Percentage, UpgradeState == "BuildFixFailed"),
OpenResultFailed = sumif(Percentage, UpgradeState == "OpenResultFailed"),
INCOMPLETE = sumif(Percentage, UpgradeState == "Incomplete"),
TotalSession = sum(Times)
by Version
```

5) Token Usage Per Session (LLM client calls)
- Description: Aggregates token usage per session for LLM calls, provides overall and by outcome via result. Adapting: filter callers or steps via caller; modify percentile set.
```kusto
let results = raw
| where EventName == "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend caller = tostring(Properties["caller"])
| extend completionToken = toint(Measures["completiontoken"]),prompToken = toint(Measures["prompttoken"]), tokens = toint(Measures["tokens"])
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens), toolCalls = count() by sessionId
| join result on sessionId
| summarize 
    sessions = count(),
    average = avg(tokens),
    median = percentile(tokens, 50),
    p75 = percentile(tokens, 75),
    p90 = percentile(tokens, 90),
    p95 = percentile(tokens, 95),
    maximum = max(tokens) by result;
raw
| where EventName has "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend caller = tostring(Properties["caller"])
| extend completionToken = toint(Measures["completiontoken"]),prompToken = toint(Measures["prompttoken"]), tokens = toint(Measures["tokens"])
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens), toolCalls = count() by sessionId
| summarize 
    sessions = count(),
    average = avg(tokens),
    median = percentile(tokens, 50),
    p75 = percentile(tokens, 75),
    p90 = percentile(tokens, 90),
    p95 = percentile(tokens, 95),
    maximum = max(tokens)| extend result = "Overall"
| project result, sessions, average, median, p75, p90, p95, maximum
| union results
```

6) Agent LLM Calls Per Session (Copilot Chat)
- Description: Measures Copilot chat tool-call volume for conversations that used Java Upgrade tools within sessions from raw. Adapting: adjust the tool filter; add token joins if needed.
```kusto
let javaUpgradeSessions = raw
| distinct VSCodeSessionId;
database('VSCodeExt').RawEventsVSCodeExt
| where EventName == "github.copilot-chat/panel.request"
| where VSCodeSessionId in (javaUpgradeSessions)
| extend conversationid = tostring(Properties["conversationid"]), requestid = tostring(Properties["requestid"]), tools = tostring(Properties["toolcounts"])
| summarize toolCalls = dcount(requestid), isJavaConversation = dcountif(requestid, tools has "javaupgrade") by conversationid
| where isJavaConversation > 0
| summarize 
    sessions = count(),
    average = avg(toolCalls),
    median = percentile(toolCalls, 50),
    p75 = percentile(toolCalls, 75),
    p90 = percentile(toolCalls, 90),
    p95 = percentile(toolCalls, 95),
    maximum = max(toolCalls)
```

7) Generate/Confirm Plan Result (classified errors)
- Description: Categorizes error messages into buckets for generate plan and confirm plan phases, then combines to show overall distribution. Adapting: extend classification case() as needed.
```kusto
let generatePlanErrors = raw
| where EventName has "vscjava.vscode-java-upgrade/generateplan"
| extend error = tostring(Properties["errormessage"])
| where isnotempty(error)
| extend Message = case(
    error has "Uncommitted changes" or error has " please commit, stash or discard them first" or error has "not a git repository" 
    or error has "Failed to get git status", "Git Validation Issues",
    error has "is only available for GitHub Copilot \"Business\" and \"Enterprise\" plans", "Require Business and Enterprise plans",
    error has "Spring Boot dependency not found" or error has "Invalid Spring Boot version to upgrade", "Invalid Spring Boot Target Version",
    error has "Please provide a path to an existing JDK" or error has "Maven path is required" or error has "Invalid Maven path"
    or error has "is not a valid JDK installation path" or error has "Gradle wrapper not found", "Java Runtime Issues (JDK/Maven/Gradle)",
    error has "Unsupported project type. Please choose a valid maven or gradle project", "Unsupported project type",
    "Others"
)
| where isnotempty(Message)
| summarize Count = count(), User = dcount(DevDeviceId) by Message
| order by Count desc;
let confirmErrors = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.failed" or EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend error = tostring(Properties["errormessage"])
| extend Message = case(
    isempty(error), "Plan Created/Confirmed",
    error has "Uncommitted changes" or error has " please commit, stash or discard them first" or error has "not a git repository" 
    or error has "Failed to get git status", "Git Validation Issues",
    error has "Spring Boot dependency not found" or error has "Invalid Spring Boot version to upgrade", "Invalid Spring Boot Target Version",
    error has "Please provide a path to an existing JDK" or error has "Maven path is required" or error has "Invalid Maven path"
    or error has "is not a valid JDK installation path" or error has "Gradle wrapper not found" or error has "There is no JDK information in the upgrade options."
    or error has "Failed to run command: \"mvnw" or error has "Failed to run command: \"mvn", "Java Runtime Issues (JDK/Maven/Gradle)",
    error has "Failed to convert markdown to JSON,", "Failed to transform configuration markdown",
    "Others"
)
| summarize Count = dcount(sessionId), User = dcount(DevDeviceId) by Message
| order by Count desc;
generatePlanErrors
| union confirmErrors
| summarize Count = sum(Count) by Message
| render piechart
```

8) Success Funnel
- Description: Consolidates key passed steps after plan creation to measure success path conversion. Ratio computed against total created plans. Adapting: include/exclude steps based on your KPI focus.
```kusto
let createPlan = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| summarize dcount(sessionId)
| project Stage = "Plan Created", Sessions = dcount_sessionId, order = 0;
let openrewrite = raw
| where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "succeed"
| summarize dcount(sessionId)
| project Stage = "OpenRewrite Succeeded", Sessions = dcount_sessionId, order = 1;
let buildFix = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end"and Properties["result"] == "true"
| summarize dcount(sessionId)
| project Stage = "Build Fix Succeeded", Sessions = dcount_sessionId, order = 2;
let cve = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecves.end"
| distinct sessionId, cves = tostring(Properties["cves"])
| summarize dcountif(sessionId, isempty( cves))
| project Stage = "CVE Validation Passed", Sessions = dcountif_sessionId, order = 3;
let consistency = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end"
| distinct sessionId, behaviorChangesCount = toint(Measures["behaviorchangescount"]), brokenFilesCount = toint(Measures["brokenfilescount"])
| summarize dcountif(sessionId, behaviorChangesCount ==0 and brokenFilesCount  == 0)
| project Stage = "Consistency Validation Passed", Sessions = dcountif_sessionId, order = 4;
let summarize_ended = raw
| where EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.end"
| summarize dcount(sessionId)
| project Stage = "Summarizing ended", Sessions = dcount_sessionId, order = 5;
let data = createPlan
| union openrewrite
| union buildFix
| union cve
| union consistency
| union summarize_ended;
let totalSessions = toscalar(
    createPlan
    | summarize max(Sessions)
);
data
| extend Ratio = Sessions * 100.0 / totalSessions
| order by order asc
| project Stage, Sessions, Ratio
```

9) Confirmed Plan Result classification (core view logic as query)
- Description: Builds the result classification by joining end-of-step outcomes onto confirmed plans. Adapting: extend case branches to handle more signals.
```kusto
let all = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| distinct VSCodeMachineId, startTime = ServerTimestamp, sessionId, majorVersion, minorVersion;
let openRewriteFailedResults = raw
| where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "failed"
| distinct VSCodeMachineId, sessionId, majorVersion, minorVersion
| project sessionId, orResult = "OpenResultFailed";
let buildFixResult = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end"
| extend buildResult = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")
| distinct VSCodeMachineId, sessionId, majorVersion, minorVersion, buildResult
| project sessionId, buildResult;
all
| join kind=leftouter openRewriteFailedResults on sessionId
| join kind=leftouter buildFixResult on sessionId
| extend result = case(isnotempty( buildResult), buildResult, isnotempty(orResult), orResult, "Incomplete")
| project VSCodeMachineId, startTime, sessionId, result, majorVersion, minorVersion, version = strcat(majorVersion, ".", minorVersion);
```

## Reasoning Notes (only if uncertain)
- Timezone: Not provided. Assumed UTC; avoid same-day data unless completeness is validated.
- Completeness gating: Ingestion cadence not stated. Recommended to derive last complete day across key signals (confirm and openrewrite end) to mitigate partial data.
- User keys: Both DevDeviceId and VSCodeMachineId appear. DevDeviceId is used in many user dcounts; VSCodeMachineId also appears. Adopt DevDeviceId for “user/device” counting and VSCodeMachineId as an alternate machine-level metric.
- Sessions: Two session identifiers exist—VSCodeSessionId (IDE-level) and sessionId from Properties (feature-level). Adopt sessionId for upgrade workflow funnels and outcomes; use VSCodeSessionId when intersecting with Copilot Chat events.
- Version filters: Gating on majorVersion > 0 or minorVersion >= 10 indicates intent to include GA or specific cohorts. Retain this gate unless business input changes.
- Internal users: IsInternal filter is parameterized (['_user_types']) in raw. Adopt it as a cohort gate; default behavior includes all unless specified.
- Error classification: Buckets defined via case() strings in queries; these are business-facing categories. Adopt them as-is and tune only with product guidance.
- Sharded/region data: Not evidenced; if present, use union pattern with normalization before aggregation.
- Token metrics: LLM token fields come from Measures (completiontoken, prompttoken, tokens). If missing in some events, ensure null-safe aggregation and rely on per-session summaries.

## Canonical Tables

### Table name: cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
- Priority: Normal
- What this table represents: Event-level telemetry for VS Code extensions. Each row is a fact (an event emitted by an extension/session). Zero rows for a time range typically imply no activity/events that match filters.
- Freshness expectations: Not specified in the input; unknown. Be cautious when querying “today” as late-arriving events may skew counts.
- When to use / When to avoid:
  - Use when you need event-level analysis for the “vscjava.vscode-upgrade” extension: stage funnels, error breakdowns, and token/tool usage.
  - Use to join or compute session-level metrics by parsing dynamic “Properties” and “Measures” fields (e.g., sessionid, cves, behaviorchangescount).
  - Use to filter by ExtensionName, ExtensionVersion, and ServerTimestamp for scoped time/version analyses.
  - Avoid heavy scans without a time window; always filter by ServerTimestamp and ExtensionName to control cost.
  - Avoid relying solely on built-in IsInternal for user classification unless confirmed; input queries cross-check via VSCodeInsights.fact_user_isinternal.
- Similar tables & how to choose:
  - Contains GitHub Copilot Chat events under EventName like “github.copilot-chat/...”; use these rows for agent/chat/token analysis when relevant.
  - For internal/external user flags, complement with VSCodeInsights.fact_user_isinternal (dimension enrichment).
- Common Filters:
  - Time range: where ServerTimestamp between (['_startTime'] .. ['_endTime'])
  - Extension: where ExtensionName == "vscjava.vscode-java-upgrade"
  - Session hygiene: where tostring(Properties["sessionid"]) != "MOCKSESSION"
  - Version scoping: where isempty(['_versions']) or ExtensionVersion in (['_versions'])
  - User type: where isempty(['_user_types']) or IsInternal in (['_user_types'])
  - Derived version guards: majorVersion/minorVersion extracted from ExtensionVersion
- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| EventName | string | Event identifier (e.g., vscjava.vscode-java-upgrade/... or github.copilot-chat/...). Primary filter for pipelines/stages. |
| Attributes | dynamic | Additional attributes attached to the event; rarely used in the provided queries. |
| ClientTimestamp | datetime | Client-side event creation time; may precede ServerTimestamp. |
| DataHandlingTags | string | Data handling annotations; not referenced in queries. |
| ExtensionName | string | Extension emitting the event (e.g., "vscjava.vscode-java-upgrade"). Key filter. |
| ExtensionVersion | string | Version of the extension; split to derive major/minor version. |
| GeoCity | string | Client geo city; unused in provided queries. |
| GeoCountryRegionIso | string | Client geo country ISO code; unused. |
| Measures | dynamic | Numeric metrics (e.g., tokens, counts). Access with Measures["..."] and cast toint/toreal. |
| NovaProperties | dynamic | Additional properties; unused. |
| Platform | string | Client OS/platform string; unused. |
| PlatformVersion | string | OS/platform version; unused. |
| Properties | dynamic | General string/dynamic properties (e.g., sessionid, cves, errormessage, recipes). Parse via tostring/parse_json. |
| ServerTimestamp | datetime | Ingestion/server-side event time; use for time-window filtering. |
| Tags | dynamic | Additional tag data; unused. |
| VSCodeMachineId | string | A per-installation identifier; used for dcount of unique users. |
| VSCodeSessionId | string | VS Code session identifier; used to correlate chat requests and upgrade sessions. |
| VSCodeVersion | string | VS Code client version; unused in queries. |
| WorkloadTags | string | Workload tags; unused. |
| LanguageServerVersion | string | Language server version; unused. |
| SchemaVersion | string | Event schema version; unused. |
| Method | string | Request/method info; unused directly. |
| Duration | real | Event duration; unused in provided summaries. |
| SQMMachineId | string | SQM machine ID; unused. |
| DevDeviceId | string | Device identifier used to join to user classification (internal/external) and user counts. |
| IsInternal | bool | Internal-user flag present in RawEvents; queries also join external dimension to ensure correctness. |
| ABExpAssignmentContext | string | A/B experiment assignment; unused. |
| Source | string | Source channel; unused. |
| SKU | string | Product SKU; unused. |
| Model | string | Model name (LLM/model); occasionally relevant for token analyses. |
| RequestId | string | Request identifier (e.g., for chat/LLM requests). Used in agent token usage queries. |
| ConversationId | string | Chat conversation identifier; used to compute per-conversation metrics. |
| ResponseType | string | Response type; unused. |
| ToolName | string | Tool name in agent/LLM context; used in tool usage analyses. |
| Outcome | string | Outcome string (e.g., succeed/failed); used for result classification. |
| IsEntireFile | string | Whether operation covers entire file; unused. |
| ToolCounts | string | Tool usage counts serialized; parsed by “has 'javaupgrade'” checks. |
| Isbyok | int | BYOK flag; unused. |
| TimeToFirstToken | int | Latency to first token; token performance metric. |
| TimeToComplete | int | Completion latency; unused in provided summaries. |
| TimeDelayms | int | Delay in ms; unused. |
| SurvivalRateFourgram | real | Diagnostic metric; unused. |
| TokenCount | real | Tokens per response; leveraged in agent token usage. |
| PromptTokenCount | real | Tokens for prompts; leveraged in token summaries. |
| NumRequests | int | Number of requests; unused in examples. |
| Turn | int | Conversation turn number; unused. |
| ResponseTokenCount | real | Tokens in response; used in response.success events. |
| TotalNewDiagnostics | int | Diagnostics count; unused. |
| Rounds | real | Rounds metric; unused. |
| AvgChunkSize | real | Average chunk size; unused. |
| Command | string | Command executed; unused. |
| CopilotTrackingId | string | Tracking ID for Copilot; unused directly. |
| IntentId | string | Intent identifier; unused. |
| Participant | string | Participant (user/agent); unused. |
| ToolGroupState | string | Tool group state; unused. |
| DurationMS | long | Duration in ms; alternative to Duration; unused in queries. |

- Column Explain:
  - EventName: Primary selector for pipeline steps (generateplan/confirmplan/openrewrite/buildfix/validatecves/validatecodebehaviorconsistency) and agent events (“github.copilot-chat/...” ). Drives funnels and per-stage metrics.
  - ServerTimestamp: Use for time range filtering; all dashboards scope to ['_startTime'] .. ['_endTime'].
  - ExtensionName, ExtensionVersion: Scope to the Java Upgrade extension and its versions; derive major/minor via split for guardrails like minorVersion >= 10.
  - Properties: Extract sessionId, errormessage, cves, recipes, taskid, output.message. Use tostring() before comparisons; parse_json() for nested arrays/objects (e.g., recipes, updateddependencies).
  - Measures: Numeric counters (completiontoken, prompttoken, tokens, behaviorchangescount, brokenfilescount, tokencount). Cast to int/real; summarize for averages/percentiles.
  - VSCodeMachineId: Unique user proxy for dcount across users; used for “Total Users” and per-stage user counts.
  - DevDeviceId: Join key to user classification table; also used for dcount of users in error summaries.
  - VSCodeSessionId: Session correlation across agent/chat events; used to link chat request/response data to upgrade sessions.
  - ToolCounts, RequestId, ConversationId, TokenCount/PromptTokenCount/ResponseTokenCount: Core for agent/LLM usage analytics, including per-session toolCalls and token distributions.
  - Outcome and Properties["result"]: Determine success/failure for openrewrite/buildfix and final result classification.

---

### Table name: cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal
- Priority: Normal
- What this table represents: User classification dimension keyed by DevDeviceId, indicating whether a device/user is internal. Queries join it to enrich RawEventsVSCodeExt with IsInternal for filtering and segmentation.
- Freshness expectations: Not specified in the input; unknown. Treat as slowly changing dimension but confirm recency if internal filter correctness is critical.
- When to use / When to avoid:
  - Use to filter or segment analyses by internal/external users via IsInternal after joining on DevDeviceId.
  - Use to override/validate any IsInternal flag embedded in RawEventsVSCodeExt when accuracy matters.
  - Avoid direct event analytics; this is a dimension table, not an events fact table.
  - Avoid usage without join keys (DevDeviceId) present; ensure RawEvents rows have DevDeviceId.
- Similar tables & how to choose:
  - RawEventsVSCodeExt includes an IsInternal column; choose this dimension table if the dashboard requires authoritative classification or if the embedded flag is incomplete.
- Common Filters:
  - None by itself; typically used via inner join on DevDeviceId and then filtered: where isempty(['_user_types']) or IsInternal in (['_user_types'])
- Table columns:
  - Unable to retrieve schema via tool for VSCodeInsights. The table is cross-database and not accessible from the configured product connection in this environment. If you have access to VSCodeInsights, run:
    - Kusto: cluster('ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal | getschema
  - Expected fields based on usage:
    - DevDeviceId: join key
    - IsInternal: boolean classification
  - Callout: Table not accessible in this tool context; confirm exact columns in the VSCodeInsights database before production use.

| Column | Type | Description or meaning |
|---|---|---|
| DevDeviceId | string | Join key to RawEventsVSCodeExt to propagate user classification. |
| IsInternal | bool | Boolean classification used to segment counts and filter dashboards by user type. |

- Column Explain:
  - DevDeviceId: Join key to RawEventsVSCodeExt to propagate user classification.
  - IsInternal: Used to segment counts and filter dashboards by user type.
