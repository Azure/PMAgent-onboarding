# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

VS Code Java Upgrade is a Visual Studio Code extension (extension ID: vscjava.vscode-java-upgrade) that assists developers in upgrading Java projects, validating dependencies, running OpenRewrite transformations, and ensuring code consistency and security (CVE checks). This schema and playbook define the canonical telemetry views, counting rules, and reusable queries used by PMAgent to analyze adoption, funnels, outcomes, and LLM tool usage related to the Java Upgrade experience in VS Code.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
VS Code Java Upgrade (VS Code extension: vscjava.vscode-java-upgrade)
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples might include: "VSCode Java Upgrade", "Java Upgrade Tool", "Java Upgrade Extension", "vscjava upgrade". Please confirm the canonical nicknames used by PMs/DEs.
- **Kusto Cluster**:
https://ddtelvscode.kusto.windows.net/
- **Kusto Database**:
VSCodeExt
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# VS Code Java Upgrade - Kusto Query Playbook

## Overview
- VS Code Java Upgrade dashboard with multiple KQL queries and tiles.
- Cluster: https://ddtelvscode.kusto.windows.net/
- Database: VSCodeExt

## Conventions & Assumptions

### Time semantics
- Observed timestamp column: ServerTimestamp (from RawEventsVSCodeExt).
- Canonical Time Column: ServerTimestamp. When a query needs a normalized time alias, use project-rename:
  - project-rename TimeCol = ServerTimestamp
- Typical time windows: dashboard parameters ['_startTime'] .. ['_endTime']. If running ad hoc, prefer a conservative window (e.g., ago(7d) or ago(30d)).
- bin() usage: not observed in provided queries; most queries summarize counts/percentiles directly without binning.
- Timezone: unknown; treat timestamps as UTC unless the data source documents otherwise.

### Freshness & Completeness Gates
- Ingestion cadence: unknown. Current-day data may be incomplete.
- Recommendation:
  - Use previous full day as effective end time for daily metrics.
  - For weekly/monthly views, consider gating on the latest complete period.
- Multi-slice completeness gate pattern (generic):
  - Determine effectiveEnd as the minimum last-seen time across sentinel slices (e.g., regions/shards).
  - Only analyze data up to effectiveEnd to avoid partial counts.

### Joins & Alignment
- Frequent keys:
  - sessionId: tostring(Properties["sessionid"]) in extension events.
  - VSCodeSessionId: dashboard-level session key for VS Code.
  - VSCodeMachineId and DevDeviceId: device/user identifiers used in dcount.
  - conversationid and requestid: agent/chat events.
- Typical join kinds:
  - inner: to add user attributes (IsInternal) from fact_user_isinternal on DevDeviceId.
  - leftouter: to stitch stage outcomes (prepare/start/end) and derive status.
  - leftantisemi: to exclude cohorts (e.g., sessions that didn’t fail a specific way).
- Post-join hygiene:
  - Use project-rename to align overlapping columns.
  - Drop intermediate columns with project-away.
  - Use coalesce() when multiple sources may carry the same concept.

### Filters & Idioms
- Common predicates:
  - Equality: EventName == "…"
  - String containment: has, startswith
  - Emptiness checks: isnotempty(), isempty()
  - Multi-select gates: where isempty(['_versions']) or ExtensionVersion in (['_versions'])
- Default/standard filters:
  - ExtensionName == "vscjava.vscode-java-upgrade"
  - Properties["sessionid"] != "MOCKSESSION"
  - Version gate: majorVersion > 0 or minorVersion >= 10 (from parsing ExtensionVersion)
  - User-type gate: IsInternal in (['_user_types']) when provided
- Cohort construction:
  - Build allowlists first (e.g., sessions that reached a stage) using distinct, then join kind=inner to filter.

### Cross-cluster/DB & Sharding
- Cross-database qualification (same cluster):
  - database("VSCodeExt").RawEventsVSCodeExt
  - database("VSCodeInsights").fact_user_isinternal
- cluster() qualification is not used in provided queries; all examples operate within the same cluster.
- Sharding/region unions are not observed; if needed, follow union → normalize keys/time → summarize.

### Table classes
- Fact/events: RawEventsVSCodeExt (event-level telemetry with ServerTimestamp).
- Dimension/lookup: fact_user_isinternal (flags DevDeviceId with IsInternal).
- No pre-aggregated or snapshot tables observed in provided set.

## Entity & Counting Rules (Core Definitions)
- Entities and keys:
  - Session: sessionId (extension session, from Properties["sessionid"]); VSCodeSessionId (VS Code host session).
  - User/device: DevDeviceId and VSCodeMachineId (both used for dcount).
  - Conversation/request: conversationid and requestid (chat/agent telemetry).
- Counting rules and cautions:
  - Sessions: use dcount(sessionId) for extension session metrics. Some events lack sessionId (see noSessionEvents).
  - Users: use dcount(DevDeviceId) or dcount(VSCodeMachineId); be consistent per metric.
  - For events that explicitly have no sessionId (e.g., generateplan.*), mark session metrics as N/A or compute user-only metrics.
- Business definitions from queries:
  - Upgrade outcomes (result view logic):
    - Succeeded: buildfix.end with Properties["result"] == "true"
    - OpenResultFailed: openrewrite.end with Properties["result"] == "failed"
    - Incomplete: otherwise (no build/open outcome)
  - Stage-specific “success”:
    - OpenRewrite succeeded: openrewrite.end and Properties["result"] == "succeed"
    - BuildFix succeeded: buildfix.end and Properties["result"] == "true"
    - CVE Validation passed: validatecves.end where cves is empty
    - Consistency Validation passed: validatecodebehaviorconsistency.end with behaviorChangesCount == 0 and brokenFilesCount == 0

## Views (Reusable Layers)

- View: raw
  - Purpose: Canonical filtered event stream for the vscjava.vscode-java-upgrade extension; applies time range, version gating, and user-type gate, and joins internal user flag.
  - Inputs: RawEventsVSCodeExt (VSCodeExt DB), fact_user_isinternal (VSCodeInsights DB)
  - Outputs: normalized stream with sessionId (string), majorVersion/minorVersion, IsInternal available.
  - Full query:
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

- View: result
  - Purpose: Derive per-session final upgrade status by stitching confirmplan/end, openrewrite/end, and buildfix/end outcomes.
  - Inputs: raw view
  - Outputs: VSCodeMachineId, startTime, sessionId, result, major/minor version, version string.
  - Full query:
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

- View: updatedependencies
  - Purpose: Extract updated dependency source/target pairs from javaupgrade.planstarted events.
  - Inputs: raw view
  - Outputs: dependency id, source version, target version, session.
  - Full query:
```kusto
raw
| where EventName == "vscjava.vscode-java-upgrade/javaupgrade.planstarted"
| extend dependencies = parse_json(tostring(Properties["updateddependencies"])), session = tostring(Properties["sessionid"]) 
| project dependencies, session
| mv-expand dependencies
| project dependency = tostring(dependencies["source"]["id"]), source=tostring(dependencies["source"]["version"]), target=tostring(dependencies["target"]["version"]), session;
```

- View: compileFailedSessions
  - Purpose: Identify sessions that failed at task 1 but did not have OpenRewrite run failures.
  - Inputs: raw view
  - Outputs: sessionId cohort.
  - Full query:
```kusto
let openrewriteFailed = raw
| extend outputMessage = tostring(Properties["output.message"]) 
| extend sessionid = tostring(Properties["sessionid"]) 
| where outputMessage has "Failed to run OpenRewrite"
| distinct sessionId;
let failedTask1 = raw
| extend taskId = tostring(Properties["taskid"]) 
| extend task = toint(split(taskId, ".")[0]) , subTask = toint(split(taskId, ".")[1])
| where isnotempty(subTask)
| summarize max(task) by sessionId
| where max_task == 1
| distinct sessionId;
failedTask1
| join kind=leftantisemi openrewriteFailed on sessionId;
```

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Apply a safe time filter with dashboard parameters or conservative defaults; set an effective end time to avoid partial current-day data.
  - Snippet:
```kusto
// Use dashboard-provided window when available
let StartTime = ['_startTime'];
let EndTimeParam = ['_endTime'];
// Effective end time: previous day at midnight UTC (if freshness is unknown)
let EffectiveEnd = datetime_add("day", -1, startofday(now()));
let EndTime = iff(isempty(EndTimeParam), EffectiveEnd, EndTimeParam);

database("VSCodeExt").RawEventsVSCodeExt
| where ServerTimestamp between (StartTime .. EndTime)
```

- Join template
  - Description: Add internal/external user flag and/or stitch stage outcomes by sessionId. Resolve duplicate columns after join.
  - Snippet:
```kusto
// Add user cohort (internal/external) and keep aligned keys
let base = database("VSCodeExt").RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| extend sessionId = tostring(Properties["sessionid"])
| join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
| project-away DevDeviceId1; // drop duplicated key if present

// Stitch outcomes (leftouter) and coalesce status
let buildFix = base
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end"
| extend buildFixStatus = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")
| project sessionId, buildFixStatus;

let openRewrite = base
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
| extend orStatus = iff(Properties["result"] == "succeed", "OpenRewriteSucceeded", "OpenResultFailed")
| project sessionId, orStatus;

base
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| project sessionId, VSCodeMachineId, ServerTimestamp
| join kind=leftouter openRewrite on sessionId
| join kind=leftouter buildFix on sessionId
| extend finalStatus = coalesce(buildFixStatus, orStatus, "Incomplete")
```

- De-dup pattern
  - Description: Use distinct or summarize dcount for unique sessions/users; dedup session-level events before joins.
  - Snippets:
```kusto
// Unique sessions for a stage
raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.start"
| distinct sessionId

// Unique counts
raw
| summarize sessions = dcount(sessionId), users = dcount(DevDeviceId)

// Dedup then join (avoid duplicate rows)
let prep = raw | where EventName == "vscjava.vscode-java-upgrade/openrewrite.prepare" | distinct sessionId;
let end  = raw | where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"    | distinct sessionId;
prep | join kind=leftouter end on sessionId
```

- Important filters
  - Description: Standard extension filters, invalid session removal, version gating, and internal user cohort gates.
  - Snippets:
```kusto
// Canonical extension filter
| where ExtensionName == "vscjava.vscode-java-upgrade"

// Remove mock sessions
| where tostring(Properties["sessionid"]) != "MOCKSESSION"

// Version gate (parsed from ExtensionVersion)
| extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]), minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
| where majorVersion > 0 or minorVersion >= 10

// User cohort gate (dashboard multi-select)
| where isempty(['_user_types']) or IsInternal in (['_user_types'])

// Multi-version selection
| where isempty(['_versions']) or ExtensionVersion in (['_versions'])

// Emptiness checks for valid sessions
| where isnotempty(sessionId)
```

- Important Definitions
  - Description: Upgrade outcome classification as used by dashboards and tiles.
  - Snippets:
```kusto
// BuildFix success/failure
| extend buildFixStatus = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")

// OpenRewrite success/failure
| extend orStatus = iff(Properties["result"] == "succeed", "OpenRewriteSucceeded", "OpenResultFailed")

// CVE pass
| extend cves = tostring(Properties["cves"])
| extend cvePassed = iff(isempty(cves), "CVE Validation Passed", "CVE Found")

// Consistency pass
| extend behaviorChangesCount = toint(Measures["behaviorchangescount"])
| extend brokenFilesCount     = toint(Measures["brokenfilescount"])
| extend consistencyPassed = iff((isempty(behaviorChangesCount) or behaviorChangesCount == 0) 
                              and (isempty(brokenFilesCount) or brokenFilesCount == 0),
                              "Consistency Validation Passed", "Code Consistency Issue Found")
```

- ID parsing/derivation
  - Description: Parse IDs and versions from Properties, and extract task/subtask granularity.
  - Snippets:
```kusto
// Session and event props
| extend sessionId = tostring(Properties["sessionid"])
| extend caller    = tostring(Properties["caller"])

// Parse ExtensionVersion into major/minor
| extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
         minorVersion = toint(split(ExtensionVersion, ".", 1)[0])

// Extract task/subtask
| extend taskId  = tostring(Properties["taskid"])
| extend task    = toint(split(taskId, ".", 0)),
         subTask = toint(split(taskId, ".", 1))

// Parse JSON dependency payload
| extend depsJson = parse_json(tostring(Properties["updateddependencies"]))
| mv-expand dep = depsJson
| extend depId     = tostring(dep["source"]["id"]),
         depSource = tostring(dep["source"]["version"]),
         depTarget = tostring(dep["target"]["version"])
```

- Sharded union (template)
  - Description: If future data comes from multiple same-schema shards (e.g., regional DBs), normalize and union.
  - Snippet:
```kusto
// Template: union shards, normalize keys/time, then summarize
union withsource="Shard" 
    (cluster("...").database("VSCodeExt_US").RawEventsVSCodeExt),
    (cluster("...").database("VSCodeExt_EU").RawEventsVSCodeExt)
| where ExtensionName == "vscjava.vscode-java-upgrade"
| project-rename TimeCol = ServerTimestamp
| extend sessionId = tostring(Properties["sessionid"])
| summarize sessions = dcount(sessionId) by Shard, bin(TimeCol, 1d)
```

## Example Queries (with explanations)

1) Upgrade Funnel (by unique user)
- Description: Computes per-event unique user and session counts and percentages across the ordered upgrade stages. Treats events without sessionId as session N/A. Adapt by changing event lists or window via the raw view.
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
let totalUser   = toscalar(operations | summarize dcount(VSCodeMachineId));
let totalSession= toscalar(operations | summarize dcount(session));
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
    sessionCount       = iff(EventName in (noSessionEvents), "N/A", tostring(sessionCount)), 
    sessionPercentage  = iff(EventName in (noSessionEvents), "N/A", strcat(sessionPercentage, "%")), 
    userCount, 
    userPercentage     = strcat(userPercentage, "%")
```

2) Build Tool Distribution
- Description: For confirmplan.end, groups by build tool and computes success rates using the result view. Adapt by adding time filters on raw or filtering cohort by ExtensionVersion.
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

3) Migration Distribution
- Description: For confirmplan.end, summarizes outcomes across source/target Java versions. Adapt by filtering specific version ranges or minor versions.
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

4) Open Rewrite Result
- Description: Classifies sessions across prepare/start/end stages, deriving Not Start/Not Complete/Error vs final end result. Adapt by adding user filters (IsInternal) or restricting time range via raw.
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
| extend result = case(isempty(sessionId1), "Not Start", isempty(sessionId2), "Not Complete/Error", result)
| summarize dcount(sessionId) by result
```

5) Token Usage Per Session
- Description: Aggregates LLM token usage per session and breaks out percentiles by upgrade result. Adapt by replacing caller or focusing on a subset of sessions (e.g., succeeded only).
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

6) Create/Confirm Plan Result (categorized error messages)
- Description: Classifies errors into buckets for generateplan and confirmplan events, unioning both and summarizing for pie. Adapt by refining error patterns or adding additional buckets.
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
    or error has "Failed to run command: \"mvnw" or error has "Failed to run command: \"mvn", "Java Runtime Issues (JDK/Maven/Gradle)",
    error has "Failed to convert markdown to JSON,", "Failed to transform configuration markdown",
    "Others"
)
| summarize Count = dcount(sessionId), User = dcount(DevDeviceId) by Message
| order by Count desc;
generatePlanErrors
| union confirmErrors
| summarize Count = sum(Count) by Message
```

7) Agent LLM Calls Per Session (VS Code agent)
- Description: Filters agent calls to conversations that used the Java upgrade tool; computes session-level distribution of toolCalls. Adapt by changing toolcounts filter or including additional agent events.
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

8) Success Funnel
- Description: Builds a funnel of succeeded passes across OpenRewrite, Build Fix, CVE, Consistency, and Summarizing stages relative to Plan Created baseline. Adapt by including started stages or modifying the baseline definition.
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

## Reasoning Notes (only if uncertain)
- Timezone: Not specified; UTC assumed. If source logs in local time, shift windows accordingly.
- User identifier: DevDeviceId vs VSCodeMachineId both appear; when counting “users,” choose one consistently. The dashboard mixes both; DevDeviceId appears more frequently as the join key for fact_user_isinternal.
- Session identity: sessionId (from Properties["sessionid"]) is the extension workflow session; VSCodeSessionId is broader (host session). Use the correct one per metric.
- Version gate: majorVersion > 0 or minorVersion >= 10 is used to exclude early versions; keep this gate unless analyzing pre-release/early versions.
- Events with missing sessionId: generateplan.* are flagged via noSessionEvents; treat session metrics as N/A for these stages.
- Success semantics: “Succeeded” in result is derived from buildfix.end Properties["result"] == "true". Some stages define success independently (e.g., OpenRewrite “succeed”)—ensure alignment when combining funnels.
- Freshness gates: Ingestion delay is unknown; prefer previous full day for reporting to avoid partial counts.

## Canonical Tables

### Table name: cluster('https://ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
- Priority: Normal
- What this table represents: Raw telemetry events emitted by VS Code extensions and related experiences. Each row is an event with core identifiers (machine/session), timestamps, and dynamic payloads (Properties, Measures). Zero rows typically imply no events matched your filters/time range rather than deletion.
- Freshness expectations: Unknown. Queries commonly use ServerTimestamp between a time window provided by the dashboard (['_startTime'] .. ['_endTime']). Be cautious with current-day data; if ingestion is delayed, counts may be incomplete.
- When to use / When to avoid:
  - Use:
    - To measure adoption and session funnels for the VS Code Java Upgrade extension (EventName filters like vscjava.vscode-java-upgrade/*).
    - To compute success rates and breakdowns by build tools, versions, recipes, and per-step results using Properties and Measures.
    - To analyze error categories via Properties["errormessage"] for generateplan, confirmplan, openrewrite, etc.
    - To quantify LLM tool usage and tokens (Measures["prompttoken"], Measures["completiontoken"], Measures["tokencount"]).
    - To correlate VS Code agent chat sessions with Java upgrade sessions using VSCodeSessionId/ConversationId/RequestId.
  - Avoid:
    - As a cleaned/aggregated source for user classification; instead join to VSCodeInsights.fact_user_isinternal.
    - Using ClientTimestamp alone for time filters; prefer ServerTimestamp for consistent ingestion-based windows.
    - Relying on Properties keys that may not exist across all EventName variants; check with isnotempty() or use tostring() safely.
- Similar tables & how to choose:
  - VSCodeInsights.fact_user_isinternal: Use to segment users (internal vs external). Join on DevDeviceId.
- Common Filters:
  - Time: ServerTimestamp between (['_startTime'] .. ['_endTime']).
  - Extension: ExtensionName == "vscjava.vscode-java-upgrade".
  - Version: ExtensionVersion in (['_versions']) or derive major/minor via split().
  - Session hygiene: tostring(Properties["sessionid"]) != "MOCKSESSION".
  - User type: IsInternal in (['_user_types']) after joining fact_user_isinternal.

- Table columns:

| Column               | Type     | Description or meaning |
|----------------------|----------|------------------------|
| EventName            | string   | Event identifier; examples include "vscjava.vscode-java-upgrade/confirmplan.end", "vscjava.vscode-java-upgrade/openrewrite.start". Primary filter for scenarios. |
| Attributes           | dynamic  | Additional attributes payload; rarely used in provided queries. |
| ClientTimestamp      | datetime | Local client-side event time. Use cautiously; ingestion can lag or differ from server time. |
| DataHandlingTags     | string   | Tags indicating data handling classifications. |
| ExtensionName        | string   | VS Code extension ID; commonly "vscjava.vscode-java-upgrade". |
| ExtensionVersion     | string   | Extension version string; split to derive major/minor (e.g., "1.10.0"). |
| GeoCity              | string   | Geo city of the client. |
| GeoCountryRegionIso  | string   | ISO country/region of the client. |
| Measures             | dynamic  | Numeric metrics; examples: "prompttoken", "completiontoken", "tokencount", "behaviorchangescount", "brokenFilescount". |
| NovaProperties       | dynamic  | Additional properties; not used in the provided queries. |
| Platform             | string   | OS platform (Windows, macOS, Linux). |
| PlatformVersion      | string   | OS version string. |
| Properties           | dynamic  | Key-value event properties; heavily used: "sessionid", "result", "errormessage", "recipes", "taskid", "caller", "conversationid", "requestid", "toolcounts". |
| ServerTimestamp      | datetime | Server-side ingestion time; preferred for time window filters. |
| Tags                 | dynamic  | Additional tag metadata. |
| VSCodeMachineId      | string   | Machine identifier; used for user-level distinct counts. |
| VSCodeSessionId      | string   | VS Code session identifier; used to link agent chat requests and Java upgrade flows. |
| VSCodeVersion        | string   | VS Code version string. |
| WorkloadTags         | string   | Workload classification tags. |
| LanguageServerVersion| string   | Language server version; not used in the provided queries. |
| SchemaVersion        | string   | Telemetry schema version. |
| Method               | string   | Method or action name; may describe operation subtype. |
| Duration             | real     | Duration metric (seconds or similar); not explicitly used. |
| SQMMachineId         | string   | Alternate machine identifier for SQM telemetry. |
| DevDeviceId          | string   | Device identifier used to join to user classification (fact_user_isinternal). |
| IsInternal           | bool     | Internal user flag available when joined/derived. Used to filter user types. |
| ABExpAssignmentContext| string   | A/B experiment assignment info. |
| Source               | string   | Source string; context of event origin. |
| SKU                  | string   | SKU or plan name; can be relevant for Copilot entitlement checks. |
| Model                | string   | Model used (e.g., LLM model); used in Copilot scenarios. |
| RequestId            | string   | Request identifier for agent messages; link across request/response events. |
| ConversationId       | string   | Conversation (chat) ID. |
| ResponseType         | string   | Type of response (success/error/etc.). |
| ToolName             | string   | Name of tool invoked (e.g., openrewrite). |
| Outcome              | string   | Outcome label; may mirror Properties["result"]. |
| IsEntireFile         | string   | Flag describing scope of operation. |
| ToolCounts           | string   | Serialized counts of tool usage (e.g., Properties["toolcounts"]). |
| Isbyok               | int      | BYOK (bring-your-own-key) indicator. |
| TimeToFirstToken     | int      | Latency to first token for LLM responses (ms). |
| TimeToComplete       | int      | Total completion time (ms). |
| TimeDelayms          | int      | Additional delay metric (ms). |
| SurvivalRateFourgram | real     | Quality metric for suggestions; not used in provided queries. |
| TokenCount           | real     | Total token count per event. |
| PromptTokenCount     | real     | Prompt token count. |
| NumRequests          | int      | Number of requests; can aggregate per session. |
| Turn                 | int      | Chat turn number. |
| ResponseTokenCount   | real     | Response token count. |
| TotalNewDiagnostics  | int      | Diagnostics count; not used in provided queries. |
| Rounds               | real     | Rounds metric; not used in provided queries. |
| AvgChunkSize         | real     | Average chunk size metric; not used in provided queries. |
| Command              | string   | Command invoked (e.g., "mvn", "gradle"); used in error categorization. |
| CopilotTrackingId    | string   | Tracking ID for Copilot. |
| IntentId             | string   | Intent identifier. |
| Participant          | string   | Participant role in chat/tool use. |
| ToolGroupState       | string   | The group state for tools; not used in the provided queries. |
| DurationMS           | long     | Duration in milliseconds (alternate field). |

- Column Explain:
  - EventName: Primary event selector for all scenario-specific analyses (generateplan/confirmplan/openrewrite/buildfix/validatecves/validatecodebehaviorconsistency etc.).
  - ServerTimestamp: Use for consistent time filtering with (['_startTime'] .. ['_endTime']).
  - Properties["sessionid"]: Session ID for flow tracking; convert via tostring(Properties["sessionid"]) and guard against empty/"MOCKSESSION".
  - Properties["result"]: Outcome flags for openrewrite/buildfix steps; used to compute success/failure/incomplete scenarios.
  - Properties["errormessage"]: Text used for error categorization; use has/contains to map to classes (Git Validation Issues, Invalid Spring Boot Target Version, Java Runtime Issues, etc.).
  - Measures["prompttoken"], Measures["completiontoken"], Measures["tokencount"]: Token metrics for LLM usage per request; aggregate for session-level stats and step-percentiles.
  - VSCodeMachineId / DevDeviceId: Identity scopes—user deduping and joining to user classification table.
  - VSCodeSessionId / ConversationId / RequestId: Linking VSCode agent chat requests/responses to Java upgrade sessions.
  - ExtensionName / ExtensionVersion: Scope to the Java Upgrade extension and derive version cohorts (major/minor).

---

### Table name: cluster('https://ddtelvscode.kusto.windows.net').database('VSCodeInsights').fact_user_isinternal
- Priority: Normal
- What this table represents: A user classification mapping used to segment telemetry into internal vs external users. Queries join this table on DevDeviceId and filter on IsInternal to respect dashboard user-type controls.
- Freshness expectations: Unknown. If classification changes, results can vary across time windows; use consistent ranges when comparing cohorts.
- When to use / When to avoid:
  - Use:
    - To segment funnel and usage metrics by user type (internal/external).
    - To exclude mock or pre-release sessions by filtering IsInternal appropriately.
    - To align adoption metrics with organizational segmentation.
  - Avoid:
    - As a standalone source of usage (it does not contain events); always join from RawEventsVSCodeExt.
    - Assuming this is complete for identity beyond DevDeviceId; check your identity resolution if mismatches occur.
- Similar tables & how to choose:
  - None referenced. Use this table when user-type segmentation is required.
- Common Filters:
  - IsInternal in (['_user_types']) to apply dashboard user-type selection.
  - Join key: DevDeviceId (from RawEventsVSCodeExt).

- Table columns:
  - Note: Could not retrieve schema using get_table_schema. The table appears in database('VSCodeInsights'), which may not be accessible in the current product context or may require additional permissions. The following fields are inferred from query usage:
  
| Column     | Type  | Description or meaning |
|------------|-------|------------------------|
| DevDeviceId| string| Device/user identifier; join key from RawEventsVSCodeExt.DevDeviceId. |
| IsInternal | bool  | Internal user flag used for segmentation (e.g., true/false). |

- Column Explain:
  - DevDeviceId: Use as the join key from RawEventsVSCodeExt to bring in user classification.
  - IsInternal: Apply dashboard filters (['_user_types']) to include/exclude internal vs external cohorts.

- Accessibility note:
  - Schema retrieval failed via get_table_schema. Verify:
    - Database name: VSCodeInsights.
    - Permissions to access cross-database resources from the VSCodeExt context.
    - Correct table name spelling and existence in the VSCodeInsights database.
  - If cross-database access is restricted, consider materializing a view/function in VSCodeExt that proxies the needed fields.