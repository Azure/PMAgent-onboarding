# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

Draft: VS Code Java Upgrade is a Visual Studio Code extension that assists developers in upgrading Java projects. Telemetry is emitted under the ExtensionName "vscjava.vscode-java-upgrade" into the VSCodeExt.RawEventsVSCodeExt table. Analyses frequently correlate with user internal/external attributes via a cross-database join to VSCodeInsights.fact_user_isinternal on the same cluster. Time is scoped with the ServerTimestamp column and sessions are identified via Properties["sessionid"].

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
- Summary: Kusto dashboard JSON for VS Code Java Upgrade
- Primary cluster and database:
  - Cluster: https://ddtelvscode.kusto.windows.net/
  - Database: VSCodeExt
- Alternate database usage:
  - Cross-database join to VSCodeInsights.fact_user_isinternal on the same cluster for internal/external user labeling.

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - ServerTimestamp (used throughout; canonical)
  - startTime (occasionally derived from ServerTimestamp in queries)
- Canonical Time Column: ServerTimestamp
  - Alias/normalize example:
    ```kusto
    // Normalize to a canonical TimeCol for uniform processing
    | project-rename TimeCol = ServerTimestamp
    ```
- Typical windows:
  - Parameterized via ['_startTime'] .. ['_endTime'] in dashboards.
  - No fixed binning observed; add bin() as needed for timeseries (e.g., 1d).
- Timezone:
  - Not specified; assume UTC by default.

### Freshness & Completeness Gates
- Ingestion cadence: not specified.
- Current day completeness: unknown. Avoid including “today” without checks.
- Recommended effective end time:
  ```kusto
  // Use the last fully ingested day by default
  let EffectiveEnd = startofday(ago(1d));
  let StartTime = EffectiveEnd - 30d;
  RawEventsVSCodeExt
  | where ServerTimestamp between (StartTime .. EffectiveEnd)
  ```
- Multi-slice gate pattern (recommendation):
  ```kusto
  // Gate on last day with sufficient sessions across sentinel slices (e.g., versions)
  let MinSessionsPerSlice = 20;
  let LatestCompleteDay =
      database("VSCodeExt").RawEventsVSCodeExt
      | where ExtensionName == "vscjava.vscode-java-upgrade"
      | summarize sessions=dcount(tostring(Properties["sessionid"])) by day=startofday(ServerTimestamp), ExtensionVersion
      | summarize ok = countif(sessions >= MinSessionsPerSlice) by day
      | where ok > 0
      | top 1 by day desc
      | project day;
  RawEventsVSCodeExt
  | where startofday(ServerTimestamp) <= toscalar(LatestCompleteDay)
  ```

### Joins & Alignment
- Frequent keys:
  - sessionId = tostring(Properties["sessionid"]) (upgrade flow session; defined in view raw)
  - VSCodeSessionId (global VS Code session; used for Copilot Chat correlation)
  - DevDeviceId (device-level; used to join internal/external)
  - VSCodeMachineId (user-device identity used for user counting)
  - conversationid, requestid (Copilot Chat)
- Typical join kinds:
  - inner: filtering to cohorts or joining user attributes (e.g., fact_user_isinternal)
  - leftouter: attaching optional results/stage outcomes
  - leftantisemi: exclude sessions from a cohort (e.g., sessions failing for a specific reason)
- Post-join hygiene:
  - Prefer distinct before joining on sessionId to avoid multiplication.
  - Use project / project-away to keep only needed columns.
  - Use coalesce() when merging values from alternate sources.

### Filters & Idioms
- Common predicates:
  - EventName equality and has/startswith for stage grouping.
  - Parse Properties[] and Measures[]; cast to types with tostring()/toint().
- Default filters seen in “raw” view:
  - ExtensionName == "vscjava.vscode-java-upgrade"
  - tostring(Properties["sessionid"]) != "MOCKSESSION"
  - Version gating: majorVersion > 0 or minorVersion >= 10
  - Cross-db inner join to fact_user_isinternal on DevDeviceId; optional IsInternal filtering
  - Optional allowlist for ExtensionVersion
- Cohort construction:
  - Build a session or VSCodeSessionId set first, then join inner onto target facts.

### Cross-cluster/DB & Sharding
- Cross-database on same cluster:
  - Use database("<DbName>").<Table> to qualify sources (e.g., database("VSCodeInsights").fact_user_isinternal).
- Sharding/region patterns:
  - Not observed. For multi-shard same schema, union then normalize time and keys before summarization.

### Table classes
- Fact events:
  - VSCodeExt.RawEventsVSCodeExt (event-level telemetry; primary source)
- Snapshot/attribute:
  - VSCodeInsights.fact_user_isinternal (device/user internal/external attribute)
- Pre-aggregated:
  - None observed.

## Entity & Counting Rules (Core Definitions)
- Entities and keys:
  - Session (upgrade flow): sessionId (string from Properties["sessionid"])
  - VS Code Session: VSCodeSessionId (used to correlate with Copilot Chat)
  - Device/User: VSCodeMachineId, DevDeviceId (user counting often uses dcount(VSCodeMachineId); some queries use DevDeviceId)
  - Conversation/Request (Copilot Chat): conversationid, requestid
- Counting rules:
  - Sessions: dcount(sessionId) after excluding MOCKSESSION and aligning to the time window.
  - Users: dcount(VSCodeMachineId) for user-level counts; DevDeviceId also used in some metrics.
  - Stage success:
    - openrewrite: Properties["result"] == "succeed" at openrewrite.end
    - buildfix: Properties["result"] == "true" at buildfix.end
    - validatecves: CVEs string is empty at validatecves.end
    - code behavior consistency: behaviorChangesCount == 0 and brokenFilesCount == 0 at validatecodebehaviorconsistency.end
- Business/state definitions (from view “result”):
  - Succeeded: buildfix.end with result == "true"
  - BuildFixFailed: buildfix.end result != "true"
  - OpenResultFailed: openrewrite.end with result == "failed"
  - Incomplete: sessions with neither of the above results attached

## Views (Reusable Layers)

### raw
- Purpose: Base filtered dataset for VS Code Java Upgrade; normalizes sessionId and joins user internal/external attribute.
- Inputs: VSCodeExt.RawEventsVSCodeExt, VSCodeInsights.fact_user_isinternal
- Outputs: Same events with derived sessionId, majorVersion, minorVersion, IsInternal; optional version/user-type allowlists
- Query:
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
- Purpose: Session-level outcome classification (Succeeded, BuildFixFailed, OpenResultFailed, Incomplete) and version labeling.
- Inputs: raw
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
  | extend result = case(isnotempty( buildResult), buildResult, isnotempty(orResult), orResult, "Incomplete")
  | project VSCodeMachineId, startTime, sessionId, result, majorVersion, minorVersion, version = strcat(majorVersion, ".", minorVersion);
  ```

### updatedependencies
- Purpose: Extract source/target dependency versions per session from the plan-start event payload.
- Inputs: raw
- Query:
  ```kusto
  raw
  | where EventName == "vscjava.vscode-java-upgrade/javaupgrade.planstarted"
  | extend dependencies = parse_json(tostring(Properties["updateddependencies"])), session = tostring(Properties["sessionid"])
  | project dependencies, session
  | mv-expand dependencies
  | project dependency = tostring(dependencies["source"]["id"]), source=tostring(dependencies["source"]["version"]), target=tostring(dependencies["target"]["version"]), session;
  ```

### compileFailedSessions
- Purpose: Identify sessions that failed to progress past task 1 (excluding OpenRewrite failures).
- Inputs: raw
- Query:
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

### Time window template
- Description: Parameterize time window via dashboard inputs or safe defaults that avoid current day.
- Snippet:
  ```kusto
  // Use dashboard-provided range if present; else fall back to last full 30 days
  let EffectiveEnd = iff(isnull(datetime(null)), startofday(ago(1d)), startofday(ago(1d)));
  let StartTime = EffectiveEnd - 30d;
  database("VSCodeExt").RawEventsVSCodeExt
  | where ExtensionName == "vscjava.vscode-java-upgrade"
  | where ServerTimestamp between (['_startTime'] .. ['_endTime'])
    or ServerTimestamp between (StartTime .. EffectiveEnd)
  ```

### Join template (session-based)
- Description: Build a cohort of sessions, then join inner to restrict.
- Snippet:
  ```kusto
  let cohort = raw
  | where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
  | distinct sessionId;
  raw
  | join kind=inner cohort on sessionId
  | where EventName has "openrewrite"
  ```

### Join template (attribute enrichment)
- Description: Attach user internal/external attribute from VSCodeInsights.
- Snippet:
  ```kusto
  database("VSCodeExt").RawEventsVSCodeExt
  | where ExtensionName == "vscjava.vscode-java-upgrade"
  | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
  | project-away DevDeviceId1  // drop duplicate if needed
  ```

### De-dup pattern
- Description: Keep the latest event per session (helpful when multiple events per stage exist).
- Snippet:
  ```kusto
  raw
  | where EventName == "vscjava.vscode-java-upgrade/openrewrite.end"
  | summarize arg_max(ServerTimestamp, *) by sessionId
  ```

### Important filters
- Description: Standard filters to ensure clean cohorts.
- Snippet:
  ```kusto
  raw
  | where tostring(Properties["sessionid"]) != "MOCKSESSION"
  | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
           minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
  | where majorVersion > 0 or minorVersion >= 10
  | where isempty(['_versions']) or ExtensionVersion in (['_versions'])
  | where isempty(['_user_types']) or IsInternal in (['_user_types'])
  ```

### Important definitions
- Description: Normalize upgrade session outcomes consistent with the “result” view.
- Snippet:
  ```kusto
  // Attach session outcomes to any session set
  let outcomes = result // reuse the view
  | project sessionId, outcome = result;
  anyFacts
  | join kind=leftouter outcomes on sessionId
  ```

### ID parsing/derivation
- Description: Extract typed fields from Properties/Measures and split composite IDs.
- Snippet:
  ```kusto
  raw
  | extend sessionId = tostring(Properties["sessionid"])
         , taskId = tostring(Properties["taskid"])
         , task = toint(split(taskId, ".")[0])
         , subTask = toint(split(taskId, ".")[1])
         , behaviorChangesCount = toint(Measures["behaviorchangescount"])
         , brokenFilesCount = toint(Measures["brokenfilescount"])
  ```

### Sharded union (template)
- Description: For same-schema sources, union, normalize, then summarize.
- Snippet:
  ```kusto
  union withsource="src"
    database("VSCodeExt").RawEventsVSCodeExt,
    database("VSCodeExtEU").RawEventsVSCodeExt
  | where ExtensionName == "vscjava.vscode-java-upgrade"
  | project src, TimeCol = ServerTimestamp, sessionId = tostring(Properties["sessionid"]), EventName
  | summarize sessions=dcount(sessionId) by src, bin(TimeCol, 1d)
  ```

## Example Queries (with explanations)

1) Stage coverage and user/session percentages by event order
- Description: Computes ordered stage metrics across defined event names, including session/user counts and percentages. Uses a canonical event order, excludes session-based rates for stages without session context, and orders output for a funnel-like view. Adapt by adding/removing events or changing time window in the raw view.
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

2) Success rate by build tool
- Description: For sessions that confirmed a plan, attaches final “result” and summarizes session and user success rates by build tool. Adapt by filtering time in raw and changing build tool extraction if schema evolves.
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

3) Success rate by source/target Java versions
- Description: Evaluates success distribution by source/target Java version pairs. Useful for identifying problematic upgrade paths. Adapt for different stage outcomes by swapping result view.
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

4) OpenRewrite stage status breakdown (pie)
- Description: Derives per-session OpenRewrite stage status: Not Start, Not Complete/Error, or result from end event. Useful for stage drop-off analysis. Adapt event names to analyze other stages.
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
| render piechart 
```

5) BuildFix stage status breakdown (pie)
- Description: Identifies whether BuildFix stage started and completed successfully; classifies Failure vs Succeeded per end event. Adapt thresholds or add more sub-status as needed.
```kusto
let prepare = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.prepare"
| distinct sessionId;
let start = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.start"
| distinct sessionId;
let end = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end"
| distinct sessionId, result = tostring(Properties["result"]);
prepare
| join kind=leftouter start on sessionId
| join kind=leftouter end on sessionId
| extend result = case(isempty(sessionId1), "Not Start", isempty(sessionId2), "Not Complete/Error", result == "true", "Succeeded", "Failure")
| summarize dcount(sessionId) by result
| render piechart 
```

6) Error categorization across generateplan and confirmplan (combined pie)
- Description: Buckets errors into categories (Git Validation, Java runtime, etc.) and combines with plan creation success. Helps prioritize error handling. Edit categorization strings for new messages.
```kusto
let generatePlanErrors = raw
| where EventName has "vscjava.vscode-java-upgrade/generateplan"
| extend error = tostring(Properties["errormessage"])
| where isnotempty(error)
| extend Message = case(
    error has "Uncommitted changes" or error has " please commit, stash or discard them first" or error has "not a git repository" 
    or error has "Failed to get git status", "Git Validation Issues",
    error has "is only available for GitHub Copilot ""Business"" and ""Enterprise"" plans", "Require Business and Enterprise plans",
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
    or error has "Failed to run command: ""mvnw""" or error has "Failed to run command: ""mvn""", "Java Runtime Issues (JDK/Maven/Gradle)",
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

7) Token usage statistics by upgrade outcome and overall (LLM client)
- Description: Aggregates token usage (prompt/completion/total) per session and computes distribution stats overall and by final session result. Useful for cost/performance monitoring of LLM workload. Adjust time and caller if needed.
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

8) Copilot Chat: Java-upgrade conversation token totals
- Description: Correlates Java Upgrade VS Code sessions to Copilot Chat conversations, sums response token count per conversation, and computes distribution. Useful for end-to-end token impact. Adjust filters for other tools or response event names.
```kusto
let javaUpgradeSessions = raw
| distinct VSCodeSessionId;
database('VSCodeExt').RawEventsVSCodeExt
| where EventName in ("github.copilot-chat/panel.request", "github.copilot-chat/response.success")
| where VSCodeSessionId in (javaUpgradeSessions)
| where (EventName == "github.copilot-chat/panel.request" and Properties["toolcounts"] has "javaupgrade")
   or EventName == "github.copilot-chat/response.success"
| extend 
    conversationid = tostring(Properties["conversationid"]),
    requestid = tostring(Properties["requestid"]),
    tokenCount = iff(EventName == "github.copilot-chat/response.success", toint(Measures["tokencount"]), int(null))
| where isnotempty(requestid)
| summarize 
    conversationid = take_anyif(conversationid, isnotempty(conversationid)),
    totalTokens = sum(tokenCount)
    by requestid
| where isnotempty(conversationid) and totalTokens > 0
| summarize tokenCount = sum(totalTokens) by conversationid
| summarize 
    sessions = count(),
    average = avg(tokenCount),
    median = percentile(tokenCount, 50),
    p75 = percentile(tokenCount, 75),
    p90 = percentile(tokenCount, 90),
    p95 = percentile(tokenCount, 95),
    maximum = max(tokenCount)
```

## Reasoning Notes (only if uncertain)
- Timezone for ServerTimestamp is unspecified:
  - Plausible: UTC (adopted), local user timezone, cluster timezone, per-region ingestion zones, mixed sources.
- Completeness of current day is unknown:
  - Plausible: safe to exclude current day (adopted), use a freshness signal, rely on schedule, backfill lag varies.
- User identity for “user” counts:
  - Plausible: VSCodeMachineId (adopted due to multiple queries using it), DevDeviceId, authenticated account id (not present), hashed telemetry id.
- Session identity for upgrade flow:
  - Plausible: Properties["sessionid"] normalized to sessionId (adopted), VSCodeSessionId (used only for cross-feature correlation).
- Success definition:
  - Plausible: “Succeeded” when buildfix.end result == "true" (adopted from view), alternate definitions may consider early success after OpenRewrite + validations.
- CVE/consistency pass conditions:
  - Plausible: CVE pass when cves is empty string, consistency pass when counts are zero (adopted from queries).
- Internal user gating:
  - Plausible: Use fact_user_isinternal.IsInternal; default shows both (adopted). Some dashboards may default to internal during preview.
- Version filters:
  - Plausible: Exclude versions with majorVersion <= 0 and minorVersion < 10 (adopted per view), different gating for GA vs preview.
- LLM token accounting:
  - Plausible: Sum tokens per session (adopted). Alternative: cap outliers, separate prompt vs completion, per-caller grouping.

## Canonical Tables

### Table name: cluster('ddtelvscode.kusto.windows.net')/database('VSCodeExt').RawEventsVSCodeExt
- Priority: Normal
- What this table represents: Raw client telemetry for VS Code extensions. Each row is an event emitted by an extension/session. For Java Upgrade analysis, rows are filtered by ExtensionName == "vscjava.vscode-java-upgrade" and EventName prefixes like "vscjava.vscode-java-upgrade/...". Zero rows for a time window typically mean no events occurred in that scope.
- Freshness expectations: Unknown. Be cautious when querying “today” as ingestion lag may exist. Prefer bounded time windows (e.g., last 7–14 days) and validate counts vs. known totals when expanding range.
- When to use:
  - End-to-end funneling across upgrade stages (generateplan, confirmplan, openrewrite, buildfix, validatecves, validatecodebehaviorconsistency, summarize).
  - Session/user-level success rates and drop-off analysis using sessionId, VSCodeMachineId, DevDeviceId.
  - Error analysis via Properties['errormessage'] and other diagnostics (e.g., output.message).
  - Token/LLM usage metrics via Measures (e.g., tokencount, prompttoken, completiontoken).
  - Cross-feature correlation (e.g., Copilot Chat events such as github.copilot-chat/* within the same VSCodeSessionId).
- When to avoid:
  - Don’t scan broad time ranges without filtering by ExtensionName and EventName; this is a high-volume, multi-tenant event table.
  - Don’t treat dynamic columns (Properties, Measures) as stable schemas; always guard with tostring()/toint() and null checks.
  - Don’t use RawEventsVSCodeExt alone to classify internal vs. external users for governance scenarios; prefer joining the fact_user_isinternal mapping.
  - Don’t assume sessionId is always present on every event type; some events are session-less (e.g., generateplan.* in the provided logic).
- Similar tables & how to choose:
  - The same RawEventsVSCodeExt holds events for many extensions (e.g., github.copilot-chat/*). Use ExtensionName and EventName filters to isolate your feature.
  - Internal user classification exists both as a field in this table (IsInternal) and in VSCodeInsights.fact_user_isinternal. Prefer the fact table as the authoritative mapping; use the in-table IsInternal only as a fallback or for quick ad-hoc checks.
- Common Filters:
  - Time window: ServerTimestamp between (['_startTime'] .. ['_endTime']).
  - Feature isolation: ExtensionName == "vscjava.vscode-java-upgrade".
  - Event scoping: EventName in specific sets (…/confirmplan.*, …/openrewrite.*, …/buildfix.*, …/validatecves.*, …/validatecodebehaviorconsistency.*, …/summarize*).
  - Data hygiene: tostring(Properties['sessionid']) != "MOCKSESSION".
  - Version gating: majorVersion > 0 or minorVersion >= 10, ExtensionVersion in (['_versions']) when provided.
  - User type: filter after joining to fact_user_isinternal, e.g., IsInternal in (['_user_types']).
- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| EventName | string | Event identifier/name (e.g., vscjava.vscode-java-upgrade/openrewrite.end). Primary predicate for feature stage logic. |
| Attributes | dynamic | Additional structured attributes; usage varies by event. |
| ClientTimestamp | datetime | Client-side timestamp when the event was produced. |
| DataHandlingTags | string | Tags describing data handling/PII policies. |
| ExtensionName | string | Extension (feature) emitting the event (e.g., vscjava.vscode-java-upgrade). |
| ExtensionVersion | string | Extension version string (e.g., 1.10.x). Split to derive major/minor. |
| GeoCity | string | Client-reported city geo. |
| GeoCountryRegionIso | string | ISO country/region code. |
| Measures | dynamic | Numeric metrics bag (e.g., tokencount, prompttoken, completiontoken, behaviorchangescount). Parse with toint()/toreal(). |
| NovaProperties | dynamic | Additional properties envelope (not commonly used in the provided queries). |
| Platform | string | OS/platform (e.g., win32, darwin). |
| PlatformVersion | string | OS/platform version. |
| Properties | dynamic | Event payload fields (e.g., sessionid, errormessage, output.message, taskid, cves, recipes, caller, buildtool). Use tostring()/parse_json(). |
| ServerTimestamp | datetime | Ingestion/server timestamp; use for time filters. |
| Tags | dynamic | Misc tags, may include classification/labels. |
| VSCodeMachineId | string | Machine identifier; used to count unique users. |
| VSCodeSessionId | string | VS Code session identifier; adjunct to Properties['sessionid']. |
| VSCodeVersion | string | VS Code client version. |
| WorkloadTags | string | Workload classification tags. |
| LanguageServerVersion | string | Language server version (if relevant). |
| SchemaVersion | string | Telemetry schema version. |
| Method | string | Method or action identifier (contextual). |
| Duration | real | Event duration in seconds (generic). |
| SQMMachineId | string | Alternate machine id (legacy/telemetry context). |
| DevDeviceId | string | Device identifier used to join with fact_user_isinternal. |
| IsInternal | bool | Internal-user flag present in the row; prefer fact table for authoritative status. |
| ABExpAssignmentContext | string | A/B experiment assignment metadata. |
| Source | string | Event source descriptor. |
| SKU | string | SKU string (e.g., distribution/build tier). |
| Model | string | Model name (e.g., LLM model) for Copilot events. |
| RequestId | string | Request identifier for request/response correlation. |
| ConversationId | string | Conversation identifier (Copilot Chat). |
| ResponseType | string | Response type classification. |
| ToolName | string | Tool name invoked (e.g., 'javaupgrade' in Copilot context). |
| Outcome | string | Outcome status label. |
| IsEntireFile | string | Whether entire file was in scope (string-encoded). |
| ToolCounts | string | Counts of tools used (string-encoded JSON). |
| Isbyok | int | BYOK (Bring Your Own Key) indicator (0/1). |
| TimeToFirstToken | int | Latency to first token (ms). |
| TimeToComplete | int | Time to complete (ms). |
| TimeDelayms | int | Delay time (ms). |
| SurvivalRateFourgram | real | Metric related to response quality/survival rate. |
| TokenCount | real | Total tokens (often response tokens) for event. |
| PromptTokenCount | real | Prompt tokens used. |
| NumRequests | int | Number of requests (batch/count) in context. |
| Turn | int | Conversation turn index. |
| ResponseTokenCount | real | Response tokens count (specific). |
| TotalNewDiagnostics | int | Count of new diagnostics produced. |
| Rounds | real | Number of rounds/iterations (contextual). |
| AvgChunkSize | real | Average chunk size (contextual to processing). |
| Command | string | Command name (e.g., executed command in client). |
| CopilotTrackingId | string | Tracking id for Copilot pipeline correlation. |
| IntentId | string | Intent identifier for request classification. |
| Participant | string | Participant role in conversation. |
| ToolGroupState | string | Group state for tools invoked. |
| DurationMS | long | Duration in milliseconds. |
- Column Explain:
  - EventName: Core for stage filtering (prepare/start/end/failed across upgrade steps).
  - ServerTimestamp: Use for time filters and ordering.
  - Properties: Holds most contextual fields (sessionid, errormessage, taskid, cves, recipes, buildtool, caller). Always cast and null-check.
  - Measures: Numeric metrics (tokencount, prompttoken, completiontoken, behaviorchangescount, brokenfilescount) for token and validation analysis.
  - ExtensionName/ExtensionVersion: Scope to the Java Upgrade extension and version cohorting (major/minor).
  - VSCodeMachineId/DevDeviceId: User-level distinct counts and joins to user attributes (internal/external).
  - VSCodeSessionId and Properties['sessionid']: Both appear; use consistently within a query and document any session-less events.
  - RequestId/ConversationId/ToolName: Copilot Chat correlation and tool usage analyses.

---

### Table name: cluster('ddtelvscode.kusto.windows.net')/database('VSCodeInsights').fact_user_isinternal
- Priority: Normal
- What this table represents: Dimensional mapping of devices to internal-user classification. It’s used to tag RawEventsVSCodeExt rows (via DevDeviceId) as internal or external for filtering and segmentation. Zero rows for a given DevDeviceId implies unknown classification.
- Freshness expectations: Unknown. Treat as a periodically refreshed mapping; avoid assumptions for the latest day until confirmed.
- When to use:
  - Filter telemetry to internal/external cohorts in a consistent, authoritative manner.
  - Join with RawEventsVSCodeExt on DevDeviceId when applying ['_user_types'] slicers.
  - Cohort comparisons of funnels, error rates, and conversion by internal vs. external users.
- When to avoid:
  - Not an event source; don’t aggregate sessions or events from this table alone.
  - Don’t filter by IsInternal without joining your target event table; you’ll lose time scoping/context.
  - Avoid relying on in-table IsInternal in RawEvents when authoritative governance requires the fact mapping.
- Similar tables & how to choose:
  - RawEventsVSCodeExt contains an IsInternal field. Prefer fact_user_isinternal for governance/official analyses; use the RawEvents flag only when the mapping is missing or for quick exploration.
- Common Filters:
  - Join key: DevDeviceId.
  - Slicers: IsInternal in (['_user_types']). If necessary, cast to bool or normalize 0/1 semantics depending on consumer expectations.
- Table columns:

| Column | Type | Description or meaning |
|---|---|---|
| DevDeviceId | string | Device identifier to join to RawEventsVSCodeExt.DevDeviceId. |
| IsInternal | long | Internal-user flag (typically 1 for internal, 0 for external). Normalize to bool as needed. |
- Column Explain:
  - DevDeviceId: Required join key to enrich event rows with user type.
  - IsInternal: Use in filters and segmentations; consider casting (e.g., tobool(IsInternal)) for boolean semantics in dashboards.