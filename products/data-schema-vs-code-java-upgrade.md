# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

> Draft schema and query playbook for VS Code Java Upgrade. This document provides product context and a comprehensive Kusto Query Playbook to enable PMAgent to interpret and analyze VS Code Java Upgrade telemetry.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
> VS Code Java Upgrade
- **Product Nick Names**: 
> **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples: "Java Upgrade", "VSCode Java Upgrade", "Java Migration".
- **Kusto Cluster**:
> https://ddtelvscode.kusto.windows.net/
- **Kusto Database**:
> VSCodeExt
- **Access Control**:
> **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# VS Code Java Upgrade - Kusto Query Playbook

## Overview
- Product: VS Code Java Upgrade
- Summary: Kusto dashboard JSON with pages, tiles, parameters, data source, base queries, and queries for VS Code Java Upgrade.
- Cluster: https://ddtelvscode.kusto.windows.net/
- Database: VSCodeExt

## Conventions & Assumptions

### Time semantics
- Canonical Time Column: ServerTimestamp
- Observed aliases:
  - startTime = ServerTimestamp in result view
  - Prefer explicitly renaming to a common name when composing views or joins
- Typical windowing:
  - Parameterized: ServerTimestamp between (['_startTime'] .. ['_endTime'])
  - When parameters are not available, use conservative defaults like ago(7d)
- Bin usage: None observed in provided queries; introduce as needed
- Timezone: Unknown. Assume UTC by default and beware of current-day partial ingestion

Example alias pattern:
```kusto
... 
| project-rename Time = ServerTimestamp
```

### Freshness & Completeness Gates
- Ingestion cadence not specified; current day may be incomplete
- Recommended effective end time:
  - Use previous full day for daily KPIs
  - Prefer “previous complete week” for weekly aggregations
- Multi-slice completeness gate (example across key upgrade steps):
```kusto
let t_end = bin(now(), 1d) - 1d; // previous full day
let t_start = t_end - 7d;
let base = database("VSCodeExt").RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| where ServerTimestamp between (t_start .. t_end);
let sentinel_events = pack_array(
  "vscjava.vscode-java-upgrade/confirmplan.end",
  "vscjava.vscode-java-upgrade/openrewrite.end",
  "vscjava.vscode-java-upgrade/buildfix.end",
  "vscjava.vscode-java-upgrade/validatecves.end",
  "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end"
);
base
| where EventName in (sentinel_events)
| summarize slices = dcount(EventName)
| where slices >= 5 // gate: all sentinels observed
```

### Joins & Alignment
- Frequent keys:
  - DevDeviceId: user/device (used to join fact_user_isinternal)
  - VSCodeMachineId: unique device id (used for some user counts)
  - sessionId: derived from Properties["sessionid"]
  - VSCodeSessionId: VS Code session identifier (used for Copilot Chat queries)
- Typical join kinds:
  - inner: to constrain to a cohort (e.g., internal users via fact_user_isinternal)
  - leftouter: to enrich with results while keeping base rows
  - leftantisemi: to exclude matching rows (anti-join)
- Post-join hygiene:
  - Resolve name clashes with project-rename
  - Drop unused columns with project-away
  - Normalize types with tostring()/toint()

### Filters & Idioms
- Common predicates:
  - Equality and IN for events/versions
  - has for substring checks in error messages and tool indicators
- Default filters:
  - ExtensionName == "vscjava.vscode-java-upgrade"
  - Exclude mock data: tostring(Properties["sessionid"]) != "MOCKSESSION"
  - Version gating from ExtensionVersion: majorVersion > 0 or minorVersion >= 10
  - Optional parameters:
    - Versions: ExtensionVersion in (['_versions'])
    - User types: IsInternal in (['_user_types'])
- Cohort construction:
  - Build cohort first (e.g., internal users) then join kind=inner

### Cross-cluster/DB & Sharding
- Cross-database usage within same cluster:
  - database("VSCodeExt").RawEventsVSCodeExt
  - database("VSCodeInsights").fact_user_isinternal
- Qualification patterns:
```kusto
cluster("ddtelvscode.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt
```
- Sharding: Not observed. Use union with normalization if introduced.

### Table classes
- Fact/events:
  - RawEventsVSCodeExt: telemetry events for extension usage and steps
- Dimension/lookup:
  - fact_user_isinternal: maps DevDeviceId to IsInternal
- Snapshot/pre-aggregated: Not observed in provided content

### Important Mapping
- Tiles/titles imply scenario→query mappings:
  - Upgrade Funnel (by unique user)
  - Build Tool Distribution
  - Migration Distribution
  - Top Errors
  - Token Usage Per Step / Per Session
  - Success Funnel
  - Agent LLM Calls Per Session
  - VSCode Agent Token Usage Per Session
  - Confirm/OpenRewrite/BuildFix/CVE/Consistency stage KPIs and pies

## Entity & Counting Rules (Core Definitions)
- Entities:
  - User: DevDeviceId (preferred due to join to fact_user_isinternal); VSCodeMachineId also used—align and be consistent per analysis
  - Session: Properties["sessionid"] projected as sessionId; VSCodeSessionId used for chat-related queries
  - Version: ExtensionVersion split into majorVersion, minorVersion; also composite version string "major.minor"
- Grouping levels:
  - By EventName for step funnels
  - By buildTool, sourceVersion→targetVersion
  - By result status (Succeeded/Failed/Incomplete)
- Business definitions from queries:
  - Build Fix Succeeded: buildfix.end with Properties["result"] == "true"
  - Open Rewrite Succeeded/Failed: openrewrite.end with Properties["result"] in {"succeed","failed"}
  - CVE Validation Passed: validatecves.end with Properties["cves"] empty
  - Consistency Validation Passed: validatecodebehaviorconsistency.end with Measures["behaviorchangescount"] == 0 and Measures["brokenfilescount"] == 0
  - Incomplete (post-confirm): confirmplan.end with neither build fix nor open rewrite signals leading to a terminal success/failure
- Counting dos/don’ts:
  - Do use dcount(sessionId) for session KPIs
  - Do use dcount(DevDeviceId) or dcount(VSCodeMachineId) consistently for “unique users”—prefer DevDeviceId if you need IsInternal
  - Don’t mix VSCodeSessionId (agent/chat) with upgrade sessionId without clear intent
  - Don’t count “noSessionEvents” as sessions (e.g., some generateplan events are marked as noSessionEvents in funnel logic)

## Views (Reusable Layers)

- raw (base)
  - Purpose: Central filter/normalization layer with time window, version gating, internal-user join, and sessionId derivation
  - Query:
    ```kusto
    let base = database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where tostring(Properties["sessionid"]) != "MOCKSESSION"
    | where ServerTimestamp between (['_startTime'] .. ['_endTime']) // Time range filtering
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
             minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion > 0 or minorVersion >= 10
    | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId;
    base
    | where isempty(['_versions']) or ExtensionVersion in (['_versions']) // Multiple selection filtering
    // regard all users before code complete as internal users
    | where isempty(['_user_types']) or IsInternal in ( ['_user_types'])
    | extend sessionId = tostring(Properties["sessionid"])
    ```
  - Inputs: RawEventsVSCodeExt, fact_user_isinternal
  - Outputs: Filtered events with sessionId, version fields, IsInternal

- result
  - Purpose: Compute per-session terminal result across OpenRewrite and Build Fix
  - Query:
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
    | extend result = case(isnotempty(buildResult), buildResult, isnotempty(orResult), orResult, "Incomplete")
    | project VSCodeMachineId, startTime, sessionId, result, majorVersion, minorVersion, version = strcat(majorVersion, ".", minorVersion)
    ```
  - Depends on: raw

- updatedependencies
  - Purpose: Extract planned dependency upgrades per session
  - Query:
    ```kusto
    raw
    | where EventName == "vscjava.vscode-java-upgrade/javaupgrade.planstarted"
    | extend dependencies = parse_json(tostring(Properties["updateddependencies"])),
             session = tostring(Properties["sessionid"])
    | project dependencies, session
    | mv-expand dependencies
    | project dependency = tostring(dependencies["source"]["id"]),
             source = tostring(dependencies["source"]["version"]),
             target = tostring(dependencies["target"]["version"]),
             session
    ```
  - Depends on: raw

- compileFailedSessions
  - Purpose: Identify sessions failing task 1 without OpenRewrite failure
  - Query:
    ```kusto
    let openrewriteFailed = raw
    | extend outputMessage = tostring(Properties["output.message"])
    | extend sessionid = tostring(Properties["sessionid"])
    | where outputMessage has "Failed to run OpenRewrite"
    | distinct sessionId;
    let failedTask1 = raw
    | extend taskId = tostring(Properties["taskid"])
    | extend task = toint(split(taskId, ".")[0]),
             subTask = toint(split(taskId, ".")[1])
    | where isnotempty(subTask)
    | summarize max(task) by sessionId
    | where max_task == 1
    | distinct sessionId;
    failedTask1
    | join kind=leftantisemi openrewriteFailed on sessionId
    ```
  - Depends on: raw

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Apply a safe, parameterized time range; default to previous full day if freshness is uncertain
  - Snippet:
    ```kusto
    // Use dashboard-provided or fallback
    let startTime = toscalar(
        (print v = ['_startTime']) | project v | take 1
    );
    let endTime = toscalar(
        (print v = ['_endTime']) | project v | take 1
    );
    let effectiveEnd = iff(isnull(endTime), bin(now(), 1d) - 1d, endTime); // previous full day
    database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where ServerTimestamp between (startTime .. effectiveEnd)
    ```

- Join template (internal cohort and session normalization)
  - Description: Standardize user cohort via fact_user_isinternal and derive sessionId
  - Snippet:
    ```kusto
    let base = database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where ServerTimestamp between (['_startTime'] .. ['_endTime']);
    let internal = database("VSCodeInsights").fact_user_isinternal
    | project DevDeviceId, IsInternal;
    base
    | join kind=inner internal on DevDeviceId
    | extend sessionId = tostring(Properties["sessionid"])
    | project-away DevDeviceId1, IsInternal1
    ```

- De-dup patterns
  - Description: Prevent double counting across multiple events per session/user
  - Snippets:
    ```kusto
    // Distinct sessions at a given step
    raw
    | where EventName == "vscjava.vscode-java-upgrade/openrewrite.start"
    | distinct sessionId

    // Unique users by device
    raw
    | summarize uniqueUsers = dcount(DevDeviceId)

    // Per-session terminal state
    result
    | summarize sessions = dcount(sessionId) by result
    ```

- Important filters
  - Description: Core constraints for analysis consistency
  - Snippets:
    ```kusto
    // Exclude mock sessions
    | where tostring(Properties["sessionid"]) != "MOCKSESSION"

    // Version gating
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
             minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion > 0 or minorVersion >= 10

    // Parameterized version filter
    | where isempty(['_versions']) or ExtensionVersion in (['_versions'])

    // Internal cohort filter (parameterized)
    | where isempty(['_user_types']) or IsInternal in (['_user_types'])
    ```

- Important Definitions
  - Description: Business outcomes derived from event properties/measures
  - Snippets:
    ```kusto
    // OpenRewrite outcome
    | extend orOutcome = tostring(Properties["result"]) // "succeed" / "failed"

    // Build Fix outcome
    | extend bfOutcome = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")

    // CVE validation passed (no CVEs found)
    | extend cves = tostring(Properties["cves"])
    | extend cvePassed = isempty(cves)

    // Consistency validation passed
    | extend behaviorChangesCount = toint(Measures["behaviorchangescount"]),
             brokenFilesCount = toint(Measures["brokenfilescount"])
    | extend consistencyPassed = (behaviorChangesCount == 0 and brokenFilesCount == 0)
    ```

- ID parsing/derivation
  - Description: Derive structured keys from strings/JSON payloads
  - Snippets:
    ```kusto
    // Task shard parsing
    | extend taskId = tostring(Properties["taskid"])
    | extend task = toint(split(taskId, ".", 0)[0]),
             subTask = toint(split(taskId, ".", 1)[0])

    // Dependency upgrade plan
    | extend deps = parse_json(tostring(Properties["updateddependencies"]))
    | mv-expand dep = deps
    | project sourceId = tostring(dep["source"]["id"]),
             sourceVer = tostring(dep["source"]["version"]),
             targetVer = tostring(dep["target"]["version"])

    // Version split
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
             minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    ```

- Sharded union
  - Description: Not present; use when adding regional shards—normalize before summarize
  - Snippet:
    ```kusto
    union withsource=TableName
      cluster("ddtelvscode.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt,
      cluster("ddtelvscode.kusto.windows.net").database("VSCodeExtEU").RawEventsVSCodeExt
    | extend sessionId = tostring(Properties["sessionid"])
    | project-rename Time = ServerTimestamp
    | summarize dcount(sessionId) by bin(Time, 1d), TableName
    ```

## Example Queries (with explanations)

1) Upgrade Funnel (ordered event progression by user/session)
- Description: Computes unique session and user counts per key step in the upgrade flow, ordered by a predefined sequence; includes percent of total sessions/users and marks steps without sessions as N/A.
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
- Description: Distribution of sessions by build tool at confirmplan.end, highlighting success ratios; useful to understand tooling mix and conversion by tool.
```kusto
raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend buildTool = tostring(Properties["buildtool"])
| distinct buildTool, sessionId
| join result on sessionId
| summarize totalSession = dcount(sessionId),
            succeededSession = dcountif(sessionId, result == "Succeeded"),
            totalUser = dcount(VSCodeMachineId),
            succeededUser = dcountif(VSCodeMachineId, result == "Succeeded") by buildTool
| project buildTool, succeededSession, totalSession,
          ["succeedRate (%)"] = round(succeededSession * 1.0 / totalSession, 4) * 100
```

3) Success Funnel (terminal stages)
- Description: Summarizes terminal “passed/succeeded” across OpenRewrite, Build Fix, CVE, Consistency, and Summarize; ratios vs. confirmplan sessions.
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
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end" and Properties["result"] == "true"
| summarize dcount(sessionId)
| project Stage = "Build Fix Succeeded", Sessions = dcount_sessionId, order = 2;
let cve = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecves.end"
| distinct sessionId, cves = tostring(Properties["cves"])
| summarize dcountif(sessionId, isempty(cves))
| project Stage = "CVE Validation Passed", Sessions = dcountif_sessionId, order = 3;
let consistency = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end"
| distinct sessionId, behaviorChangesCount = toint(Measures["behaviorchangescount"]), brokenFilesCount = toint(Measures["brokenfilescount"])
| summarize dcountif(sessionId, behaviorChangesCount == 0 and brokenFilesCount == 0)
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
let totalSessions = toscalar(createPlan | summarize max(Sessions));
data
| extend Ratio = Sessions * 100.0 / totalSessions
| order by order asc
| project Stage, Sessions, Ratio
```

4) Token Usage Per Session (extension tools)
- Description: Computes session-level token usage metrics from llmclient.sendrequest events; provides overall and segmented by result outcome.
```kusto
let results = raw
| where EventName == "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend completionToken = toint(Measures["completiontoken"]),
         prompToken = toint(Measures["prompttoken"]),
         tokens = toint(Measures["tokens"])
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens), toolCalls = count() by sessionId
| join result on sessionId
| summarize sessions = count(),
            average = avg(tokens),
            median = percentile(tokens, 50),
            p75 = percentile(tokens, 75),
            p90 = percentile(tokens, 90),
            p95 = percentile(tokens, 95),
            maximum = max(tokens) by result;
raw
| where EventName has "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend completionToken = toint(Measures["completiontoken"]),
         prompToken = toint(Measures["prompttoken"]),
         tokens = toint(Measures["tokens"])
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens), toolCalls = count() by sessionId
| summarize sessions = count(),
            average = avg(tokens),
            median = percentile(tokens, 50),
            p75 = percentile(tokens, 75),
            p90 = percentile(tokens, 90),
            p95 = percentile(tokens, 95),
            maximum = max(tokens)
| extend result = "Overall"
| project result, sessions, average, median, p75, p90, p95, maximum
| union results
```

5) VSCode Agent Token Usage Per Session
- Description: Derives total tokens per conversation for Copilot Chat, filtered to Java Upgrade conversations; provides robust session distribution statistics.
```kusto
let javaUpgradeSessions = raw
| distinct VSCodeSessionId;
database('VSCodeExt').RawEventsVSCodeExt
| where EventName in ("github.copilot-chat/panel.request", "github.copilot-chat/response.success")
| where VSCodeSessionId in (javaUpgradeSessions)
| where (EventName == "github.copilot-chat/panel.request" and Properties["toolcounts"] has "javaupgrade")
   or EventName == "github.copilot-chat/response.success"
| extend conversationid = tostring(Properties["conversationid"]),
         requestid = tostring(Properties["requestid"]),
         tokenCount = iff(EventName == "github.copilot-chat/response.success", toint(Measures["tokencount"]), int(null))
| where isnotempty(requestid)
| summarize conversationid = take_anyif(conversationid, isnotempty(conversationid)),
            totalTokens = sum(tokenCount) by requestid
| where isnotempty(conversationid) and totalTokens > 0
| summarize tokenCount = sum(totalTokens) by conversationid
| summarize sessions = count(),
            average = avg(tokenCount),
            median = percentile(tokenCount, 50),
            p75 = percentile(tokenCount, 75),
            p90 = percentile(tokenCount, 90),
            p95 = percentile(tokenCount, 95),
            maximum = max(tokenCount)
```

6) Recipes used in OpenRewrite tool
- Description: Explodes recipe payloads on successful OpenRewrite sessions; computes per-recipe success ratio to prioritize recipe efficacy.
```kusto
let succeeded = raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
| where Properties["result"] == "succeed"
| distinct sessionId;
raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
| project sessionId, recipes = tostring(Properties["recipes"])
| extend recipeJson = parse_json(recipes)
| mv-expand recipe = recipeJson
| project sessionId,
         recipeId = tostring(recipe.id),
         recipeName = recipe.name,
         recipeDescription = recipe.description,
         recipeTarget = recipe.target,
         recipeDependencies = recipe.dependencyGroups
| join kind=leftouter succeeded on sessionId
| summarize total = dcount(sessionId), succeeded = dcount(sessionId1) by recipeId
| extend succeededRatio = succeeded * 1.0 / total
```

7) Error classification for Generate/Confirm Plan
- Description: Classifies and aggregates error messages into categories for Generate Plan and Confirm Plan steps; use to track top issues.
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
    error has "Please provide a path to an existing JDK" or error has "Maven path is required"
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
    or error has "Failed to run command: "mvnw" or error has "Failed to run command: "mvn", "Java Runtime Issues (JDK/Maven/Gradle)",
    error has "Failed to convert markdown to JSON,", "Failed to transform configuration markdown",
    "Others"
)
| summarize Count = dcount(sessionId), User = dcount(DevDeviceId) by Message
| order by Count desc;
generatePlanErrors
| union confirmErrors
| summarize Count = sum(Count) by Message
```

8) Migration Distribution (source→target Java versions)
- Description: Counts sessions and success ratio by source and target Java versions chosen at confirmplan; helps size migration cohorts.
```kusto
raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| extend sourceVersion = toint(Properties["sourcejavaversion"]),
         targetVersion = toint(Properties["targetjavaversion"])
| distinct sourceVersion, targetVersion, sessionId
| join result on sessionId
| summarize totalSession = dcount(sessionId),
            succeededSession = dcountif(sessionId, result == "Succeeded"),
            totalUser = dcount(VSCodeMachineId),
            succeededUser = dcountif(VSCodeMachineId, result == "Succeeded") by sourceVersion, targetVersion
| project sourceVersion, targetVersion, succeededSession, totalSession,
          ["succeedRate (%)"] = round(succeededSession * 1.0 / totalSession, 4) * 100
```

9) Extension Tools LLM Calls Per Session
- Description: Per-session count distribution of LLM tool calls, overall and segmented by final result; useful for cost/usage analysis.
```kusto
let results = raw
| where EventName == "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend completionToken = toint(Measures["completiontoken"]),
         prompToken = toint(Measures["prompttoken"]),
         tokens = toint(Measures["tokens"])
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens), toolCalls = count() by sessionId
| join result on sessionId
| summarize sessions = count(),
            average = avg(toolCalls),
            median = percentile(toolCalls, 50),
            p75 = percentile(toolCalls, 75),
            p90 = percentile(toolCalls, 90),
            p95 = percentile(toolCalls, 95),
            maximum = max(toolCalls) by result;
raw
| where EventName has "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend completionToken = toint(Measures["completiontoken"]),
         prompToken = toint(Measures["prompttoken"]),
         tokens = toint(Measures["tokens"])
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens), toolCalls = count() by sessionId
| summarize sessions = count(),
            average = avg(toolCalls),
            median = percentile(toolCalls, 50),
            p75 = percentile(toolCalls, 75),
            p90 = percentile(toolCalls, 90),
            p95 = percentile(toolCalls, 95),
            maximum = max(toolCalls)
| extend result = "Overall"
| project result, sessions, average, median, p75, p90, p95, maximum
| union results
```

10) OpenRewrite Result distribution (Not Start / Not Complete / Final)
- Description: Classifies sessions by OpenRewrite prepare/start/end to understand drop-offs and errors; produces a per-result distribution.
```kusto
let prepare = raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.prepare"
| distinct sessionId;
let start = raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.start"
| distinct sessionId;
let end = raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
| distinct sessionId, result = tostring(Properties["result"]);
prepare
| join kind=leftouter start on sessionId
| join kind=leftouter end on sessionId
| extend result = case(isempty(sessionId1), "Not Start",
                       isempty(sessionId2), "Not Complete/Error",
                       result)
| summarize dcount(sessionId) by result
```

## Reasoning Notes (only if uncertain)
- User identity: Both DevDeviceId and VSCodeMachineId appear for “unique users.” I adopt DevDeviceId when linking to IsInternal (cohort consistency) and VSCodeMachineId otherwise; ensure consistency per metric.
- Timezone: Not specified. I assume UTC and prefer excluding current day for stable aggregates.
- Session identity: Properties["sessionid"] is the canonical upgrade session; VSCodeSessionId is distinct (VS Code runtime session) and used for Copilot Chat. Use carefully and do not mix unless intended.
- Version gating: The rule majorVersion > 0 or minorVersion >= 10 is applied widely and likely filters pre-release/beta ranges. I keep it as a default filter for upgrade analysis.
- NoSessionEvents: Some generateplan events are flagged with no session id; funnel logic treats them with N/A. When building session KPIs, exclude those.
- Success definitions: I use exact conditions shown in queries (e.g., buildfix.end result "true", openrewrite.end result "succeed"). Do not infer alternative success indicators.
- Freshness/completeness: With unknown ingestion SLAs, I recommend previous-day effective end time and sentinel event gates across confirm/openrewrite/buildfix/CVE/consistency.
- Token usage: Measures["tokens"], ["prompttoken"], ["completiontoken"] observed only on llmclient.sendrequest and response.success (agent). I avoid mixing these without clear joins and keep source-specific summaries.
- Cross-db: All usage is within the same cluster but across VSCodeExt and VSCodeInsights. I qualify database() consistently and recommend cluster() if needed for portability.

### Acceptance Checklist
- Identified timestamp column (ServerTimestamp), typical windowing via parameters, bin usage absent, timezone marked unknown/assumed UTC.
- Documented freshness and effective end time strategy with a gate.
- Produced entity model with keys and counting rules; cautions about snapshot vs. daily fact not applicable (events only).
- Called out cross-database use; provided qualification patterns.
- Included default exclusion patterns (MOCKSESSION, version gating, IsInternal filters).
- Provided parsing/derivation snippets (JSON dependencies, taskId split, version split).
- Example queries are copy-paste-ready and describe adaptation.
- No fabricated fields or values; used exact properties/measures from input.

## Canonical Tables

### Table name: cluster(ddtelvscode.kusto.windows.net).database(VSCODEEXT).RawEventsVSCodeExt
- Priority: Normal
- What this table represents: Raw telemetry events emitted by VS Code extensions and core features for the VSCodeExt product. Each row is an event with a name, timestamp(s), and payload stored in dynamic columns (Properties, Measures, Tags, etc.). Zero rows usually mean either no events matched your filters (time range, ExtensionName, EventName) or the extension was inactive in that window.
- Freshness expectations: Unknown. Be cautious analyzing “today” until late in the day; use bounded time windows and confirm with an “order by ServerTimestamp desc | take N” sanity check.
- When to use:
  - Build funnels across upgrade steps by EventName and session identifiers (sessionId from Properties or VSCodeSessionId).
  - Token usage and LLM call metrics (Measures.* such as tokencount/prompttoken/completiontoken).
  - Error distribution via Properties["errormessage"] grouped by EventName.
  - Adoption metrics by distinct users/sessions (DevDeviceId, VSCodeMachineId, VSCodeSessionId).
  - Join to fact_user_isinternal for segmentation by user type.
- When to avoid:
  - Aggregating across mixed extensions without filtering ExtensionName; you’ll miscount.
  - Using ClientTimestamp for latency analysis without checking clock skew; prefer ServerTimestamp for consistency.
  - Assuming “IsInternal” in this table is authoritative; the dashboards join VSCodeInsights.fact_user_isinternal for consistency.
  - Counting sessions without normalizing session id source (Properties["sessionid"] vs VSCodeSessionId).
- Similar tables & how to choose:
  - Within VSCodeExt, “github.copilot-chat/…” events are recorded in this same RawEventsVSCodeExt table. Filter by EventName and ExtensionName to isolate upgrade vs. chat traffic.
  - If you need internal/external labeling, rely on cluster(ddtelvscode.kusto.windows.net).database(VSCodeInsights).fact_user_isinternal and join on DevDeviceId.
- Common Filters:
  - Time: ServerTimestamp between a specified start .. end window.
  - Extension: ExtensionName == "vscjava.vscode-java-upgrade".
  - Session hygiene: tostring(Properties["sessionid"]) != "MOCKSESSION"; isnotempty(sessionId).
  - Version: ExtensionVersion in selectable list; optionally derive majorVersion/minorVersion via split() for thresholds (e.g., minorVersion >= 10).
  - Event scoping: EventName equals/has/startswith specific upgrade steps (generateplan/confirmplan/openrewrite/buildfix/validatecves/validatecodebehaviorconsistency).
  - User type: join to fact_user_isinternal; filter by IsInternal in selectable values.

- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| EventName | string | Logical name of the event (e.g., vscjava.vscode-java-upgrade/openrewrite.end). Primary selector for scenarios. |
| Attributes | dynamic | Additional attributes bag; rarely used in the upgrade queries. |
| ClientTimestamp | datetime | Event time recorded on the client; may be skewed. |
| DataHandlingTags | string | Data handling classification tags; not typically used in queries. |
| ExtensionName | string | Extension identifier (filter to “vscjava.vscode-java-upgrade”). |
| ExtensionVersion | string | Extension version string (e.g., “1.10.0”); often split into major/minor. |
| GeoCity | string | Client geolocation city; not used in provided queries. |
| GeoCountryRegionIso | string | ISO country; not used in provided queries. |
| Measures | dynamic | Numeric metrics payload. Examples used: tokencount, prompttoken, completiontoken, behaviorchangescount, brokenfilescount. |
| NovaProperties | dynamic | Additional property bag; not used in provided queries. |
| Platform | string | Client OS/platform; not used in provided queries. |
| PlatformVersion | string | Version of the platform; not used in provided queries. |
| Properties | dynamic | Core payload bag for string fields. Examples used: sessionid, errormessage, output.message, result, cves, recipes, taskid, caller. |
| ServerTimestamp | datetime | Ingestion server-side time; preferred for time filtering and ordering. |
| Tags | dynamic | Free-form tags; not used in provided queries. |
| VSCodeMachineId | string | VS Code machine identifier; used for unique user approximations. |
| VSCodeSessionId | string | VS Code session identifier; used for session-scoped analytics and agent joins. |
| VSCodeVersion | string | VS Code app version; not used in provided queries. |
| WorkloadTags | string | Workload tags; not used in provided queries. |
| LanguageServerVersion | string | Language server version; not used in provided queries. |
| SchemaVersion | string | Payload schema version; not used in provided queries. |
| Method | string | Event method indicator; not used in provided queries. |
| Duration | real | Event duration (seconds); not used in provided queries. |
| SQMMachineId | string | SQM machine id; not used in provided queries. |
| DevDeviceId | string | Device identifier used to join to fact_user_isinternal. |
| IsInternal | bool | Internal user flag (may exist here, but dashboards derive via fact_user_isinternal). |
| ABExpAssignmentContext | string | A/B experiment context; not used in provided queries. |
| Source | string | Source string; not used in provided queries. |
| SKU | string | SKU string; not used in provided queries. |
| Model | string | Model name; often LLM model context; not used directly. |
| RequestId | string | Request id for chat/tool calls; used in agent linkage. |
| ConversationId | string | Conversation id for chat; used in token aggregation queries. |
| ResponseType | string | Response type; not used in provided queries. |
| ToolName | string | Tool name in Copilot/tooling; not used in provided queries. |
| Outcome | string | Outcome label; not used in provided queries. |
| IsEntireFile | string | Indicator for entire-file operations; not used in provided queries. |
| ToolCounts | string | Tools used per request; used to detect “javaupgrade” tool in agent requests. |
| Isbyok | int | BYOK indicator; not used in provided queries. |
| TimeToFirstToken | int | Performance metric in ms; not used in provided queries. |
| TimeToComplete | int | Performance metric in ms; not used in provided queries. |
| TimeDelayms | int | Delay metric; not used in provided queries. |
| SurvivalRateFourgram | real | Quality metric; not used in provided queries. |
| TokenCount | real | Tokens for responses; used in token analytics. |
| PromptTokenCount | real | Tokens for prompts; used in token analytics. |
| NumRequests | int | Request count metric; not used directly. |
| Turn | int | Conversation turn index; not used in provided queries. |
| ResponseTokenCount | real | Tokens in response; used in token analytics. |
| TotalNewDiagnostics | int | Diagnostics count; not used in provided queries. |
| Rounds | real | Rounds count; not used in provided queries. |
| AvgChunkSize | real | Average chunk size; not used in provided queries. |
| Command | string | Command string; not used in provided queries. |
| CopilotTrackingId | string | Copilot correlation id; not used in provided queries. |
| IntentId | string | Intent identifier; not used in provided queries. |
| Participant | string | Participant role; not used in provided queries. |
| ToolGroupState | string | Tool group state; not used in provided queries. |
| DurationMS | long | Duration in milliseconds; not used in provided queries. |

- Column Explain:
  - EventName: Primary driver for scenario scoping; use exact names for each stage (generateplan/confirmplan/openrewrite/buildfix/validatecves/validatecodebehaviorconsistency).
  - ServerTimestamp: Use for reliable time filtering and ordering; pair with between(start .. end).
  - Properties.sessionid: Canonical per-feature session id; normalize to string. Used throughout for joins and session-level summarization.
  - VSCodeSessionId: VS Code app-level session; used when linking agent chat events to upgrade activity.
  - DevDeviceId: Device identity key for dcount users and for joining to fact_user_isinternal.
  - Measures.*: Numeric counters used for token usage and validation output (tokencount/prompttoken/completiontoken, behaviorchangescount, brokenfilescount).
  - Properties.errormessage: Error text for grouping and piecharts across stages.
  - Properties.result: Stage outcome (“true”, “failed”, “succeed”); normalize to labels in case() before aggregations.
  - ToolCounts/ConversationId/RequestId: Linkage between upgrade sessions and agent chat usage for per-session tool/LLM metrics.
  - ExtensionName/ExtensionVersion: Always filter to the target extension and optionally version gates (major/minor thresholds).

---

### Table name: cluster(ddtelvscode.kusto.windows.net).database(VSCODEINSIGHTS).fact_user_isinternal
- Priority: Normal
- What this table represents: A lookup of device identities to internal/external classification. Each row maps DevDeviceId to an IsInternal indicator used to segment telemetry.
- Freshness expectations: Unknown. Treat the classification as eventually consistent; if user type toggles, analyze with a fixed time window.
- When to use:
  - Segment upgrade telemetry into internal/external cohorts in reports and dashboards.
  - Filter to a specific user type selection in parameterized views (IsInternal in ['_user_types']).
  - Ensure consistent labeling across products by centralizing the join rather than relying on inline flags.
- When to avoid:
  - Direct counting without joining to event source; this is a small mapping table, not a facts table.
  - Assuming values are booleans in all contexts; use the table’s actual type when filtering.
- Similar tables & how to choose:
  - None referenced in the source content; this is the canonical user-type mapping for VS Code insights.
- Common Filters:
  - Typically none; used via inner join on DevDeviceId, then filter IsInternal to the selected cohort.

- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| DevDeviceId | string | Device identifier; join key to RawEventsVSCodeExt.DevDeviceId. |
| IsInternal | long | Internal classification indicator used for cohort filtering (e.g., internal vs external). Example values observed in queries: used in set membership filters. |

- Column Explain:
  - DevDeviceId: Mandatory key to join with RawEventsVSCodeExt. Use inner join to ensure only classified users are included.
  - IsInternal: Use to filter cohorts. In dashboards, it is passed through selection parameters (['_user_types']). Confirm actual values (e.g., 0/1) when building reports.
