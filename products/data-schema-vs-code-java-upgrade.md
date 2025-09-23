# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

VS Code Java Upgrade is a Visual Studio Code extension feature that assists developers in upgrading Java projects, including plan generation, OpenRewrite application, build fixes, CVE validation, behavior consistency checks, and summarization. This onboarding schema provides PMAgent with the product context, data sources, and reusable Kusto views/snippets to enable accurate analysis and conversations about usage, funnels, errors, and token consumption.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
  - Name: VS Code Java Upgrade
  - Description: Kusto dashboard for VS Code Java Upgrade events, funnels, errors, tool usage, and token consumption across multiple steps.
- Product Nick Names:
  - [TODO]Data_Engineer: Provide nicknames such as "Java Upgrade", "VSCode Java Upgrade", "JavaUpg" if applicable.
- Kusto Cluster:
  - https://ddtelvscode.kusto.windows.net/
- Kusto Database:
  - VSCodeExt
- Access Control:
  - [TODO] Data Engineer: If this product’s data has high confidentiality concerns, specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# VS Code Java Upgrade - Kusto Query Playbook

## Overview
- Product: VS Code Java Upgrade
- Summary: Kusto dashboard for VS Code Java Upgrade events, funnels, errors, tool usage, and token consumption across multiple steps.
- Cluster: https://ddtelvscode.kusto.windows.net/
- Database: VSCodeExt

## Conventions & Assumptions

- Time semantics
  - Observed timestamp column: ServerTimestamp (from RawEventsVSCodeExt). Some queries alias startTime = ServerTimestamp.
  - Canonical Time Column: ServerTimestamp
    - To standardize, alias with: project-rename TimeCol = ServerTimestamp, then continue using TimeCol.
  - Typical windows: Provided by dashboard parameters ['_startTime'] and ['_endTime'].
  - Binning: Most queries are stage counts and distributions without binning; add bin(TimeCol, 1d) for time series.
  - Timezone: Not specified; assume UTC by default. Be cautious with “today” due to unknown ingestion lag.

- Freshness & Completeness Gates
  - Ingestion cadence: Unknown.
  - Current day completeness: Unknown; prefer an effective end time that excludes “today” unless validated.
  - Recommended pattern:
    - Use EndTime = min(datetime(['_endTime']), now(-1d)) for conservative analysis.
    - For multi-slice completeness (e.g., across ExtensionVersion or user cohorts), pick the latest day where all required slices have nonzero data.

- Joins & Alignment
  - Frequent keys:
    - sessionId = tostring(Properties["sessionid"]) for session-level joins across events.
    - DevDeviceId to join with database("VSCodeInsights").fact_user_isinternal (IsInternal flag).
    - VSCodeMachineId and VSCodeSessionId appear in event-level counts; choose consistently per metric.
    - ExtensionVersion with parsed majorVersion and minorVersion.
  - Typical join kinds:
    - inner: to add user attributes (fact_user_isinternal) to raw.
    - leftouter: to stitch stage outcomes (e.g., adding build result to sessions).
    - leftantisemi: to exclude sessions matched by a condition (e.g., error-based filter-outs).
  - Post-join hygiene:
    - Resolve duplicates via project-rename or coalesce().
    - Drop unused columns: project-away.

- Filters & Idioms
  - Scope to the extension: where ExtensionName == "vscjava.vscode-java-upgrade".
  - Exclude mock/test sessions: tostring(Properties["sessionid"]) != "MOCKSESSION".
  - Version gating: extend major/minor from ExtensionVersion; where majorVersion > 0 or minorVersion >= 10.
  - Parameterized filters:
    - where isempty(['_versions']) or ExtensionVersion in (['_versions'])
    - where isempty(['_user_types']) or IsInternal in (['_user_types'])
  - Predicates: has for substring, startswith, in for cohorts.

- Cross-cluster/DB & Sharding
  - Qualification patterns:
    - database("VSCodeExt").RawEventsVSCodeExt
    - database("VSCodeInsights").fact_user_isinternal
    - Use cluster("<URI>").database("<DB>").<Table> when querying across clusters (not explicitly shown but compatible).
  - Sharding:
    - No explicit shard tables observed. If sharding emerges (e.g., regional replicas), use union → normalize keys/time → summarize.

- Table classes
  - Fact (events): RawEventsVSCodeExt (event stream with ServerTimestamp, event name, measures, properties).
  - Dimension/Snapshot: fact_user_isinternal (IsInternal flag keyed by DevDeviceId).
  - Pre-aggregated: Not observed.

## Entity & Counting Rules (Core Definitions)

- Entity model
  - Session: sessionId = tostring(Properties["sessionid"]); used for stage funnels and outcomes.
  - Device/User:
    - DevDeviceId used for user-join (IsInternal) and often for distinct user counts.
    - VSCodeMachineId also appears in some user counts; pick one definition and stick to it for comparability. Prefer DevDeviceId when you need IsInternal attribution; otherwise be consistent.
  - Versioning:
    - ExtensionVersion parsed to majorVersion, minorVersion for segmentation and gating.

- Business definitions
  - Upgrade outcome (from view: result):
    - Succeeded: buildfix.end with Properties["result"] == "true".
    - BuildFixFailed: buildfix.end present with non-"true" result (or inferred failure).
    - OpenResultFailed: openrewrite.end with Properties["result"] == "failed".
    - Incomplete: no downstream success/failure evidence after confirmplan.end.
  - Stage-specific pass criteria used across queries:
    - OpenRewrite succeeded: openrewrite.end and Properties["result"] == "succeed".
    - Build Fix succeeded: buildfix.end and Properties["result"] == "true".
    - CVE Validation passed: validatecves.end with empty cves list.
    - Behavior Consistency passed: validatecodebehaviorconsistency.end with behaviorChangesCount == 0 and brokenFilesCount == 0.

## Views (Reusable Layers)

### raw
- Purpose: Base dataset from RawEventsVSCodeExt scoped to the Java Upgrade extension, cleansed sessionId, version gates, user type, and time window; joins IsInternal.
- Inputs: VSCodeExt.RawEventsVSCodeExt (fact), VSCodeInsights.fact_user_isinternal (dimension).
- Outputs: Enriched event rows with sessionId, major/minor version, IsInternal.
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
- Purpose: Compute per-session upgrade outcome classification and attach version info. Widely used for funnels, success rates, and LLM usage slice by outcome.
- Inputs: raw (events).
- Outputs: VSCodeMachineId, startTime, sessionId, result, major/minor version, version string.
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
- Purpose: Extract dependency upgrade plan items from JSON payload at plan start.
- Inputs: raw.
- Outputs: per-dependency source/target versions and dependency id by session.
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
- Purpose: Identify sessions that failed early (task 1) but not due to OpenRewrite failure, for targeted troubleshooting.
- Inputs: raw.
- Outputs: sessionId cohort.
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
- Description: Standardize time filtering with safe effective end time to avoid partial data.
- Snippet:
```kusto
// Parameters expected from dashboard
let ParamStartTime = datetime(['_startTime']);
let ParamEndTime   = datetime(['_endTime']);
// Conservative effective end time to avoid today's partial data
let EffectiveEndTime = min_of(ParamEndTime, now(-1d));
<SourceTable>
| where ServerTimestamp between (ParamStartTime .. EffectiveEndTime)
// If you must include today, remove EffectiveEndTime and use ParamEndTime directly
```

### Join template (user attributes and session stitching)
- Description: Enrich events with IsInternal and normalize sessionId for joins.
- Snippet:
```kusto
let Raw = database("VSCodeExt").RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| extend sessionId = tostring(Properties["sessionid"]);
let Users = database("VSCodeInsights").fact_user_isinternal;
Raw
| join kind=inner Users on DevDeviceId
| project-rename TimeCol = ServerTimestamp
| project-away DevDeviceId1, // drop join dup if appears
               // drop other unneeded columns...
```

### De-dup pattern
- Description: Pick the latest event per session or clean duplicates.
- Snippet:
```kusto
// Latest event per session
Raw
| summarize arg_max(ServerTimestamp, *) by sessionId
// Or collapse to one row per session per EventName
Raw
| summarize arg_max(ServerTimestamp, *) by sessionId, EventName
```

### Important filters
- Description: Scope to Java Upgrade, exclude mock sessions, and apply parameter cohorts.
- Snippet:
```kusto
RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| where tostring(Properties["sessionid"]) != "MOCKSESSION"
| extend sessionId = tostring(Properties["sessionid"])
| extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
         minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
| where majorVersion > 0 or minorVersion >= 10
| where isempty(['_versions']) or ExtensionVersion in (['_versions'])
| join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
| where isempty(['_user_types']) or IsInternal in (['_user_types'])
```

### Important Definitions (upgrade funnel outcomes)
- Description: Normalize funnel outcomes for consistent aggregations.
- Snippet:
```kusto
let Confirmed = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| distinct sessionId;
let OpenRewriteFailed = raw
| where EventName == "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "failed"
| distinct sessionId;
let BuildFix = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end"
| extend buildResult = iff(Properties["result"] == "true", "Succeeded", "BuildFixFailed")
| project sessionId, buildResult;
Confirmed
| join kind=leftouter OpenRewriteFailed on sessionId
| join kind=leftouter BuildFix on sessionId
| extend UpgradeResult = case(isnotempty(buildResult), buildResult,
                             isnotempty(sessionId1), "OpenResultFailed",
                             "Incomplete")
```

### ID parsing/derivation
- Description: Extract version components and parse compound task ids; expand JSON arrays.
- Snippets:
```kusto
// Version parsing
Raw
| extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
         minorVersion = toint(split(ExtensionVersion, ".", 1)[0])

// Task id parsing "1.2"
Raw
| extend taskId = tostring(Properties["taskid"])
| extend task = toint(split(taskId, ".")[0]), subTask = toint(split(taskId, ".")[1])

// Expand dependencies
Raw
| extend deps = parse_json(tostring(Properties["updateddependencies"]))
| mv-expand dep = deps
| project dependency = tostring(dep["source"]["id"]),
          source     = tostring(dep["source"]["version"]),
          target     = tostring(dep["target"]["version"])
```

### Sharded union (template)
- Description: Merge same-schema sources (e.g., different DBs/clusters), normalize time/session ids, then summarize.
- Snippet:
```kusto
let A = cluster("<ClusterA>").database("VSCodeExt").RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| project-rename TimeCol = ServerTimestamp
| extend sessionId = tostring(Properties["sessionid"]);
let B = cluster("<ClusterB>").database("VSCodeExt").RawEventsVSCodeExt
| where ExtensionName == "vscjava.vscode-java-upgrade"
| project-rename TimeCol = ServerTimestamp
| extend sessionId = tostring(Properties["sessionid"]);
union isfuzzy=true A, B
| summarize Sessions = dcount(sessionId) by bin(TimeCol, 1d)
```

## Example Queries (with explanations)

### 1) Stage coverage and user/session percentages across the funnel
- Description: Produces an ordered list of key events with session and user coverage, normalizing stages, handling pre-session events as 100% for session coverage. Adapt: update eventOrder/noSessionEvents for new stages; adjust time via raw view params.
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

### 2) Success rate by build tool
- Description: Computes session/user counts and success rates grouped by buildTool captured at confirmplan.end. Adapt: change the grouping column; adjust time via raw view.
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

### 3) Success rate by source→target Java versions
- Description: Uses sourcejavaversion and targetjavaversion from confirmplan.end to group success. Adapt: adjust dimension or aggregate to users (VSCodeMachineId) if preferred.
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

### 4) Error taxonomy across plan generation and confirmation
- Description: Categorizes common error messages into buckets across generateplan* and confirmplan.* flows and renders a pie. Adapt: expand case() with new patterns or break out by EventName.
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
    isempty(error), "Plan Created",
    error has "Uncommitted changes" or error has " please commit, stash or discard them first" or error has "not a git repository" 
    or error has "Failed to get git status", "Git Validation Issues",
    error has "Spring Boot dependency not found" or error has "Invalid Spring Boot version to upgrade", "Invalid Spring Boot Target Version",
    error has "Please provide a path to an existing JDK" or error has "Maven path is required" or error has "Invalid Maven path"
    or error has "is not a valid JDK installation path" or error has "Gradle wrapper not found" or error has "There is no JDK information in the upgrade options."
    or error has "Failed to run command: \"mvnw\"" or error has "Failed to run command: \"mvn\"", "Java Runtime Issues (JDK/Maven/Gradle)",
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

### 5) Outcome funnel (confirmed plan → summarizing end) with ratios
- Description: Funnel view that progresses through key success milestones. Ratio is Sessions / total confirmed plans. Adapt: toggle intermediate stages by uncommenting unions; change aggregation to users if needed.
```kusto
let createPlan = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| summarize dcount(sessionId)
| project Stage = "Plan Confirmed/Created", Sessions = dcount_sessionId, order = 0;
let openrewrite = raw
| where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "succeed"
| summarize dcount(sessionId)
| project Stage = "OpenRewrite Succeeded", Sessions = dcount_sessionId, order = 1;
let buildFix_started = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.start"
| summarize dcount(sessionId)
| project Stage = "Build Fix Started", Sessions = dcount_sessionId, order = 3;
let cve_started = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecves.start"
| distinct sessionId, cves = tostring(Properties["cves"])
| summarize dcount(sessionId)
| project Stage = "CVE Validation Started/Build project Succeeded", Sessions = dcount_sessionId, order = 5;
let consistency_started = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start"
| summarize dcount(sessionId)
| project Stage = "Consistency Validation Started", Sessions = dcount_sessionId, order = 7;
let summarize_started = raw
| where EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.start"
| summarize dcount(sessionId)
| project Stage = "Summarizing started", Sessions = dcount_sessionId, order = 9;
let summarize_ended = raw
| where EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.end"
| summarize dcount(sessionId)
| project Stage = "Summarizing ended", Sessions = dcount_sessionId, order = 10;
let data = createPlan
| union openrewrite
| union buildFix_started
| union cve_started
| union consistency_started
| union summarize_started
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

### 6) LLM token usage distribution by outcome and overall
- Description: Aggregates LLM request tokens per session and produces descriptive statistics split by upgrade result, plus overall. Adapt: replace tokens with prompToken/completionToken; filter by caller if needed.
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

### 7) Cross-feature Copilot chat: Java-upgrade conversations and token usage
- Description: For sessions that used Java Upgrade, find related GitHub Copilot Chat conversations with Java Upgrade tool, then compute tool call density and token totals. Adapt: use other tools in toolcounts; include additional event pairs.
```kusto
// Tool call density per conversation
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

// Token totals per conversation
let javaUpgradeSessions2 = raw
| distinct VSCodeSessionId;
database('VSCodeExt').RawEventsVSCodeExt
| where EventName in ("github.copilot-chat/panel.request", "github.copilot-chat/response.success")
| where VSCodeSessionId in (javaUpgradeSessions2)
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

### 8) OpenRewrite stage completion classification
- Description: Classifies sessions into Not Start, Not Complete/Error, or final result from openrewrite.end. Useful for stage health. Adapt: reuse for other stages by changing EventName and results.
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

### 9) Version-level outcome distribution
- Description: Computes percentage of upgrade outcomes by version (major.minor). Adapt: filter to selected versions or group by major only.
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

## Reasoning Notes (only if uncertain)

- Timezone is not stated; Kusto defaults to UTC. We assume UTC to avoid ambiguity.
- Freshness/ingestion lag is unknown; we recommend excluding the current day (use now(-1d)) unless validated by a completeness gate.
- “User” identity differs across queries (DevDeviceId vs VSCodeMachineId vs VSCodeSessionId). We adopt DevDeviceId when joining user attributes (IsInternal) and recommend consistent use within a report; VSCodeMachineId is acceptable if you standardize on it.
- Upgrade result semantics are inferred from the result view logic (buildfix.end + openrewrite.end). If other failure modes exist (e.g., buildproject.*), incorporate them similarly.
- CVE and consistency pass/fail criteria originate from their respective end events’ fields; ensure those measures are populated consistently before relying on them for strict pass/fail gating.
- Cross-cluster usage is not shown; if you need to query across clusters, qualify with cluster("<URI>").database("<DB>").Table and consider union patterns.
- “Before code complete” comment in the raw view suggests special handling of IsInternal for early periods; specific dates/rules are not provided—treat as unknown and document any assumptions in analyses.

## Canonical Tables

### Table name: RawEventsVSCodeExt
- Priority: High
- What this table represents:
  - Fact/event log table for VS Code extensions. Each row is a single telemetry event emitted by an extension.
  - For VS Code Java Upgrade, events are identified by ExtensionName == "vscjava.vscode-java-upgrade" and specific EventName values (e.g., generateplan.*, confirmplan.*, openrewrite.*, buildfix.*, validatecves.*, validatecodebehaviorconsistency.*, summarize*).
  - Zero rows after filtering typically implies no activity in the selected time window or filters (not deletion).
- Freshness expectations:
  - Ingestion/refresh delay: unknown. Be cautious with current-day data; prefer ending the time window a few hours in the past if you see gaps.
  - Use explicit time window filters on ServerTimestamp.
- When to use / When to avoid:
  - Use when building funnels and stage conversion (prepare/start/end) for Java upgrade phases (generate plan → confirm plan → openrewrite → buildfix → validations → summarize).
  - Use to compute session success/failure by inspecting Properties["result"] on specific end events (e.g., buildfix.end, openrewrite.end).
  - Use to analyze errors by parsing Properties["errormessage"] across stages.
  - Use to measure tool and token consumption for LLM-related events (EventName contains ".../llmclient.sendrequest", Measures carries token counts).
  - Avoid querying without restricting ExtensionName; you will mix events across many extensions.
  - Avoid relying on Properties keys without null checks (e.g., isempty(), isnotempty()) and toint() guards; Properties is dynamic.
  - Avoid counting “MOCKSESSION” values; explicitly filter them out.
- Similar tables & how to choose:
  - Same table also stores other extension events (e.g., "github.copilot-chat/*"). Choose via EventName and ExtensionName filters.
  - For user-type enrichment (internal vs external), join with fact_user_isinternal on DevDeviceId (cross-database).
- Common Filters:
  - Time: ServerTimestamp between (['_startTime'] .. ['_endTime'])
  - Extension: ExtensionName == "vscjava.vscode-java-upgrade"
  - Session hygiene: tostring(Properties["sessionid"]) != "MOCKSESSION"
  - Versioning: derive majorVersion/minorVersion from ExtensionVersion; commonly filter where majorVersion > 0 or minorVersion >= 10 and/or ExtensionVersion in (['_versions'])
  - User type: after joining user dimension, filter IsInternal in (['_user_types'])
  - Event subsets: EventName in (...) per stage; or EventName has ".../llmclient.sendrequest" for token usage
- Table columns:
  - Live schema lookup (run in ADX):
    - <cluster("ddtelvscode.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt> | getschema
  - Columns used by this product’s queries (inferred from usage):

  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | ServerTimestamp   | datetime | Event server-side timestamp; use for time filtering. |
  | EventName         | string   | Event identifier (e.g., vscjava.vscode-java-upgrade/generateplan.start, .../openrewrite.end). |
  | ExtensionName     | string   | Extension event source; filter equals "vscjava.vscode-java-upgrade". |
  | ExtensionVersion  | string   | Extension semantic version; used to derive major/minor. |
  | VSCodeMachineId   | string   | Pseudonymous machine identifier; used for user/device unique counts. |
  | VSCodeSessionId   | string   | VS Code session identifier; used to scope related events. |
  | DevDeviceId       | string   | Device identifier; join key to fact_user_isinternal. |
  | Properties        | dynamic  | Event properties bag. Keys used: sessionid, result, output.message, taskid, buildtool, sourcejavaversion, targetjavaversion, errormessage, recipes, cves, caller, toolcounts, conversationid, requestid, updateddependencies. |
  | Measures          | dynamic  | Numeric measurements bag. Keys used: completiontoken, prompttoken, tokens, behaviorchangescount, brokenfilescount, tokencount. |
- Column Explain:
  - ServerTimestamp: Always apply time filters against this column to bound data volume and align comparisons.
  - EventName: Select specific stage events. Common sets: generateplan.*, confirmplan.*, openrewrite.*, buildfix.*, validatecves.*, validatecodebehaviorconsistency.*, summarize*. For LLM metrics, use ".../llmclient.sendrequest".
  - ExtensionName: Restrict to "vscjava.vscode-java-upgrade" to avoid cross-extension contamination.
  - ExtensionVersion: Derive major/minor with split(); filter by version lists (['_versions']) or thresholds (major > 0 or minor >= 10).
  - VSCodeMachineId: Use for unique user/device counts; pairs with session metrics for conversion rates.
  - VSCodeSessionId: Used to relate conversation/tooling events; often deduped in funnels.
  - DevDeviceId: Join key to fact_user_isinternal to segment internal/external users.
  - Properties.sessionid: Primary session identifier used by the feature; convert via tostring(Properties["sessionid"]) and store as sessionId in views.
  - Properties.result: Outcome classification on end events (e.g., "true"/"failed"/"succeed"); drives final session result.
  - Properties.errormessage: Free-text error grouping; use has/contains and case() mapping to categorize.
  - Properties.taskid: Encodes task/subtask; split(".", 0/1) for task/subtask analysis.
  - Properties.recipes / Properties.cves: JSON payloads; parse_json then mv-expand to analyze content and success ratios.
  - Properties.caller/toolcounts/conversationid/requestid: Copilot tool usage correlations across conversations and requests.
  - Measures.*: Numeric metrics; cast via toint() before aggregation. Used for token counts and behavior/broken-files counters.

### Table name: cluster("ddtelvscode.kusto.windows.net").database("VSCodeInsights").fact_user_isinternal
- Priority: Normal
- What this table represents:
  - Dimension mapping of devices/users to internal status. Used to segment traffic into internal vs. external cohorts.
  - Zero rows for a given DevDeviceId implies unknown device (treat as not joined).
- Freshness expectations:
  - Refresh cadence unknown; treat as a slowly changing dimension. Avoid strict same-day assumptions for new devices.
- When to use / When to avoid:
  - Use to join with RawEventsVSCodeExt on DevDeviceId to add IsInternal.
  - Use to filter user cohorts (['_user_types']) in dashboards.
  - Avoid counting events directly from this table; it’s a dimension, not event facts.
  - Avoid time filtering here; apply time windows on the fact table before the join.
- Similar tables & how to choose:
  - None specified. If other user/type dimensions exist, prefer the one referenced by existing views for consistency.
- Common Filters:
  - Cohort filter after join: IsInternal in (['_user_types'])
  - No native time filtering (dimension).
- Table columns:
  - Live schema lookup (run in ADX):
    - <cluster("ddtelvscode.kusto.windows.net").database("VSCodeInsights").fact_user_isinternal> | getschema
  - Columns used by this product’s queries (inferred from usage):

  | Column      | Type  | Description or meaning |
  |-------------|-------|------------------------|
  | DevDeviceId | string| Join key to RawEventsVSCodeExt.DevDeviceId. |
  | IsInternal  | bool  | True for internal users/devices; used for cohort filtering. |
- Column Explain:
  - DevDeviceId: Primary key used to enrich raw events; ensure join kind=inner in views to limit to known devices.
  - IsInternal: Cohort flag. Dashboards use a parameter (['_user_types']) to include subsets (e.g., internal-only, external-only).