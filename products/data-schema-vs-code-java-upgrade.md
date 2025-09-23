# VS Code Java Upgrade - Product and Data Overview Template

## 1. Product Overview

Draft: VS Code Java Upgrade is a Visual Studio Code extension that assists developers in upgrading Java projects. It provides a guided upgrade workflow (plan, confirm, OpenRewrite, build fix, validations, summarize) and emits telemetry for each stage. This schema enables PMAgent to analyze user adoption, funnel conversion, success rates, errors, and LLM usage associated with Java upgrade workflows in VS Code.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
  VS Code Java Upgrade
- Product Nick Names: 
  **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- Kusto Cluster:
  https://ddtelvscode.kusto.windows.net/
- Kusto Database:
  VSCodeExt
- Access Control:
  **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# VS Code Java Upgrade — Kusto Query Playbook

## Overview
- Product: VS Code Java Upgrade
- Summary: Kusto dashboard JSON titled 'VS Code Java Upgrade' with pages, tiles, base queries, parameters, and queries for the VS Code Java Upgrade extension.
- Cluster: https://ddtelvscode.kusto.windows.net/
- Primary database: VSCodeExt
- Alternate database(s): VSCodeInsights (used for user internal/external classification)

## Conventions & Assumptions

### Time semantics
- Timestamp columns observed:
  - VSCodeExt.RawEventsVSCodeExt: ServerTimestamp (used in all time filters), ClientTimestamp (client-side time; not used in provided queries)
- Canonical Time Column: alias all time filters to TimeCol
  - Example:
    ```kusto
    ... | project-rename TimeCol = ServerTimestamp
    ```
- Typical windows: parameter-driven ['_startTime'] .. ['_endTime']. If choosing defaults without parameters, prefer last 7 days and expand gradually.
- bin() usage: not standard in provided queries. If needed, prefer bin(TimeCol, 1d) for daily rollups.
- Timezone: unknown. Assume UTC unless you have domain-specific requirements.
- Current-day caution: Treat current day/hour as potentially incomplete.

### Freshness & Completeness Gates
- Ingestion cadence: unknown. Ingestion delay not specified.
- Practical guidance:
  - Avoid “today” in dashboards requiring stable numbers; prefer now(-24h) as effective end.
  - Use a multi-slice gate to select the last fully ingested day across core stages:
    ```kusto
    let coreStages = dynamic([
      "vscjava.vscode-java-upgrade/confirmplan.end",
      "vscjava.vscode-java-upgrade/openrewrite.end",
      "vscjava.vscode-java-upgrade/buildfix.end"
    ]);
    database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | summarize stageSeen = dcountif(EventName, EventName in (coreStages)) by day = startofday(ServerTimestamp)
    | where stageSeen >= 3  // all sentinel stages reported that day
    | top 1 by day desc
    ```
  - Use previous full week/month when uncertainty is high.

### Joins & Alignment
- Frequent keys:
  - DevDeviceId (join to VSCodeInsights.fact_user_isinternal for IsInternal)
  - sessionId = tostring(Properties["sessionid"]) (upgrade session)
  - VSCodeMachineId (user/device distinct counting)
  - VSCodeSessionId (VS Code runtime session; used to link Copilot Chat)
- Typical join kinds:
  - inner (to restrict to mapped devices when classifying users)
  - leftouter (to enrich with optional result states across steps)
  - leftantisemi (to exclude subsets)
- Post-join hygiene:
  - Resolve duplicates and normalize names:
    ```kusto
    ... | project-rename TimeCol = ServerTimestamp
        | project-away EventName1, IsInternal1
    ```
  - Use coalesce() where needed to combine alternative sources:
    ```kusto
    | extend IsInternalEffective = coalesce(tolong(IsInternal), tolong(IsInternal_from_fact))
    ```

### Filters & Idioms
- Product scoping:
  - ExtensionName == "vscjava.vscode-java-upgrade"
  - Exclude test data: tostring(Properties["sessionid"]) != "MOCKSESSION"
- Version gating:
  - majorVersion > 0 or minorVersion >= 10; optionally restrict to a version allowlist
    ```kusto
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
             minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion > 0 or minorVersion >= 10
    | where isempty(['_versions']) or ExtensionVersion in (['_versions'])
    ```
- User type:
  - After joining VSCodeInsights.fact_user_isinternal on DevDeviceId, filter IsInternal in (['_user_types'])
- Text search:
  - has for substring, startswith for prefix, exact equality for specific events
- Cohorts:
  - Build allowlists/denylists first, then inner join to facts for stable segmentation.

### Cross-cluster/DB & Sharding
- Qualify sources:
  - database("VSCodeExt").RawEventsVSCodeExt
  - database("VSCodeInsights").fact_user_isinternal
  - If cross-cluster is needed: cluster("ddtelvscode.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt
- Sharding:
  - Not indicated in provided inputs. If merging same-schema shards, normalize keys/time and then summarize:
    ```kusto
    union isfuzzy=true
      cluster("<clusterA>").database("VSCodeExt").RawEventsVSCodeExt,
      cluster("<clusterB>").database("VSCodeExt").RawEventsVSCodeExt
    | project-rename TimeCol = ServerTimestamp
    | summarize dcount(sessionId) by bin(TimeCol, 1d)
    ```

### Table classes
- Fact (event stream): VSCodeExt.RawEventsVSCodeExt — use for event-level analysis, funnels, token usage, errors.
- Snapshot (mapping): VSCodeInsights.fact_user_isinternal — use to classify internal/external users; do not count events from it.

## Entity & Counting Rules (Core Definitions)
- Entity model and keys
  - Upgrade session: sessionId = tostring(Properties["sessionid"])
  - User/device: VSCodeMachineId (for dcount users), DevDeviceId (authoritative join key for IsInternal)
  - VS Code session: VSCodeSessionId (for linking Copilot Chat telemetry)
  - Version: ExtensionVersion; derive majorVersion, minorVersion for cohorts
  - Stages by EventName prefixes: generateplan, confirmplan, openrewrite, buildfix, validatecves, validatecodebehaviorconsistency, summarizeupgrade
- Counting rules
  - Unique users: dcount(VSCodeMachineId) or dcount(DevDeviceId) depending on consistency needs
  - Unique sessions: dcount(sessionId) after sessionId derivation/normalization
  - Stage success:
    - openrewrite.end: Properties["result"] == "succeed"
    - buildfix.end: Properties["result"] == "true" => Succeeded; else BuildFixFailed
    - validatecves.end: treat empty Properties["cves"] as “passed”
    - validatecodebehaviorconsistency.end: behaviorChangesCount == 0 and brokenFilesCount == 0 as “passed”
  - Composite result per session (from the result view):
    - Succeeded if buildfix.end result == "true"
    - Else OpenResultFailed if openrewrite.end result == "failed"
    - Else Incomplete
- Do/Don’t
  - Do filter by ExtensionName and exclude MOCKSESSION before joins/aggregations.
  - Do join VSCodeInsights.fact_user_isinternal on DevDeviceId for user segmentation.
  - Don’t use current hour/day without checking completeness.
  - Don’t rely on RawEvents.IsInternal when dashboards require consistency with fact_user_isinternal.

## Canonical Tables
### Table name: cluster("ddtelvscode.kusto.windows.net").database("VSCodeExt").RawEventsVSCodeExt
- Priority: Normal
- What this table represents:
  - Raw telemetry events emitted by VS Code extensions (fact/event stream). Each row is a single event with timestamp, event name, extension identity/version, device/session identifiers, and property/measure bags.
  - Zero rows for a timeframe typically means no events matched your filters (not deletion).
- Freshness expectations:
  - Unknown. Ingestion delay is not specified. When querying “today” or the last few hours, validate with a small window first and be cautious interpreting partial data.
- When to use / When to avoid:
  - Use when analyzing:
    - Event flows and stage completion for the “vscjava.vscode-java-upgrade” extension (e.g., generateplan, confirmplan, openrewrite, buildfix, validate*).
    - Session-level outcomes by deriving sessionId from Properties["sessionid"] and joining intermediate results.
    - Error diagnostics via Properties["errormessage"] or Properties["output.message"].
    - Token/LLM usage metrics via Measures (e.g., completiontoken, prompttoken, tokens) and chat fields (ConversationId/RequestId/ToolCounts).
    - Version-based cohorts by parsing ExtensionVersion into major/minor.
  - Avoid:
    - Using this table alone to determine “internal vs. external” user classification; prefer joining to VSCodeInsights.fact_user_isinternal on DevDeviceId.
    - Long, unbounded time ranges; keep tight ServerTimestamp windows and scale up gradually.
- Similar tables & how to choose:
  - VSCodeExt.RawEventsVSCodeExt is the authoritative event stream for VS Code extensions; the “IsInternal” column also exists here, but the product’s queries use VSCodeInsights.fact_user_isinternal for authoritative classification. Prefer the fact table for consistency.
- Common Filters:
  - Time: ServerTimestamp between dynamic ['_startTime'] .. ['_endTime'].
  - Product scoping: ExtensionName == "vscjava.vscode-java-upgrade".
  - Test data removal: tostring(Properties["sessionid"]) != "MOCKSESSION".
  - Version: derive majorVersion = toint(split(ExtensionVersion, ".", 0)[0]) and minorVersion = toint(split(ExtensionVersion, ".", 1)[0]); filter majorVersion > 0 or minorVersion >= 10; optionally ExtensionVersion in (['_versions']).
  - User type: after joining to fact_user_isinternal, filter by IsInternal in (['_user_types']).
  - EventName subsets for stages: ".../generateplan.*", ".../confirmplan.*", ".../openrewrite.*", ".../buildfix.*", ".../validatecves.*", ".../validatecodebehaviorconsistency.*", ".../summarizeupgrade.*".
- Table columns:

| Column               | Type     | Description or meaning |
|----------------------|----------|------------------------|
| EventName            | string   | Telemetry event name; filtered heavily (e.g., vscjava.vscode-java-upgrade/confirmplan.end, openrewrite.end, buildfix.start). |
| Attributes           | dynamic  | Misc attributes bag (rarely referenced by product queries). |
| ClientTimestamp      | datetime | Event time at client. |
| DataHandlingTags     | string   | Data handling classification tags. |
| ExtensionName        | string   | Extension identifier (e.g., vscjava.vscode-java-upgrade). Primary filter for scope. |
| ExtensionVersion     | string   | Extension version (e.g., "1.10.0"); split to derive major/minor. |
| GeoCity              | string   | City geo info. |
| GeoCountryRegionIso  | string   | Country/region (ISO). |
| Measures             | dynamic  | Numeric metrics bag. Keys used include: completiontoken, prompttoken, tokens, behaviorchangescount, brokenfilescount, tokencount. Cast with toint()/toreal(). |
| NovaProperties       | dynamic  | Additional properties bag (unused in provided queries). |
| Platform             | string   | OS platform (e.g., win32, darwin, linux). |
| PlatformVersion      | string   | OS version/build. |
| Properties           | dynamic  | Stringly/dynamic properties bag. Keys used include: sessionid, result, errormessage, recipes, output.message, taskid, cves, caller, buildtool, sourcejavaversion, targetjavaversion, conversationid, requestid, toolcounts. Extract with tostring()/parse_json(). |
| ServerTimestamp      | datetime | Ingestion/server timestamp; primary time filter column. |
| Tags                 | dynamic  | Tags bag (rarely referenced). |
| VSCodeMachineId      | string   | Machine (user) identifier; used for dcount user metrics. |
| VSCodeSessionId      | string   | VS Code session identifier; used to correlate chat events and Java upgrade sessions. |
| VSCodeVersion        | string   | VS Code app version. |
| WorkloadTags         | string   | Workload tags classification (unused). |
| LanguageServerVersion| string   | Language Server version (e.g., Java LS). |
| SchemaVersion        | string   | Telemetry schema version. |
| Method               | string   | Additional method info (unused). |
| Duration             | real     | Event duration metric (seconds or ms depending on producer; unused directly). |
| SQMMachineId         | string   | Additional telemetry machine id. |
| DevDeviceId          | string   | Device identifier used to join VSCodeInsights.fact_user_isinternal. |
| IsInternal           | bool     | Internal flag in this stream. Product logic still joins to the fact table for authoritative classification. |
| ABExpAssignmentContext| string  | A/B experiment assignment context. |
| Source               | string   | Event source (unused). |
| SKU                  | string   | SKU string (unused). |
| Model                | string   | Model name (e.g., LLM model; unused by provided queries). |
| RequestId            | string   | Request identifier (used in chat linkage). |
| ConversationId       | string   | Conversation identifier (used in chat linkage). |
| ResponseType         | string   | Response type (chat). |
| ToolName             | string   | Tool name invoked (chat). |
| Outcome              | string   | Outcome string (chat). |
| IsEntireFile         | string   | Entire-file flag (chat; string-encoded). |
| ToolCounts           | string   | Tool usage summary string (e.g., contains "javaupgrade"). |
| Isbyok               | int      | BYOK indicator (unused). |
| TimeToFirstToken     | int      | Latency to first token (ms) in chat scenarios. |
| TimeToComplete       | int      | Completion latency (ms) in chat scenarios. |
| TimeDelayms          | int      | Delay metric (ms). |
| SurvivalRateFourgram | real     | Diagnostic metric (unused). |
| TokenCount           | real     | Total tokens (alternative to Measures["tokens"]). |
| PromptTokenCount     | real     | Prompt tokens (alternative to Measures["prompttoken"]). |
| NumRequests          | int      | Number of requests aggregated. |
| Turn                 | int      | Conversation turn index. |
| ResponseTokenCount   | real     | Completion tokens (alternative to Measures["completiontoken"]). |
| TotalNewDiagnostics  | int      | Diagnostic count metric. |
| Rounds               | real     | Conversation rounds metric. |
| AvgChunkSize         | real     | Average chunk size metric. |
| Command              | string   | Command name (chat/tooling). |
| CopilotTrackingId    | string   | Tracking id for Copilot telemetry. |
| IntentId             | string   | Intent identifier. |
| Participant          | string   | Conversation participant label. |
| ToolGroupState       | string   | Tool group state string. |
| DurationMS           | long     | Duration in milliseconds (parallel to Duration). |
- Column Explain:
  - EventName: Primary driver for stage analysis (generateplan/confirmplan/openrewrite/buildfix/validate*/summarize*). Use exact matches or has/startswith patterns.
  - ServerTimestamp: Use for time filtering (between ['_startTime'] .. ['_endTime']). Default to a conservative window (e.g., 7 days) and expand as needed.
  - ExtensionName: Always filter to "vscjava.vscode-java-upgrade" for this product’s analytics.
  - ExtensionVersion: Split to major/minor for gating cohorts; product uses major > 0 or minor >= 10; optionally filter to ['_versions'].
  - Properties (dynamic):
    - sessionid: Derive sessionId = tostring(Properties["sessionid"]) for session-level joins and distinct counts.
    - result: For openrewrite/buildfix outcomes; e.g., "succeed", "failed", "true"/"false".
    - errormessage/output.message: For error categorization and top errors.
    - cves, behaviorchangescount, brokenfilescount: For validation outcomes.
    - buildtool, sourcejavaversion, targetjavaversion: For cohort breakdowns.
    - caller, recipes, taskid: For LLM usage and pipeline task analysis.
    - conversationid, requestid, toolcounts: For linking Copilot Chat requests and identifying "javaupgrade" tool usage.
  - Measures (dynamic): Extract numeric metrics (completiontoken, prompttoken, tokens, behaviorchangescount, brokenfilescount, tokencount) with toint/toDouble; used for token percentiles and outcomes.
  - DevDeviceId: Join key to VSCodeInsights.fact_user_isinternal for user-type filtering.
  - VSCodeMachineId / VSCodeSessionId: Use for distinct user/session counts; VSCodeSessionId is used to link with Copilot Chat events.
  - TokenCount/PromptTokenCount/ResponseTokenCount: Alternative explicit columns to Measures bag for token metrics.
  - IsInternal: Present in this table but product queries rely on the fact table; if both exist, prefer the fact table’s value for consistency.

---

### Table name: cluster("ddtelvscode.kusto.windows.net").database("VSCodeInsights").fact_user_isinternal
- Priority: Normal
- What this table represents:
  - Snapshot-like mapping from DevDeviceId to IsInternal classification used to tag events/users as internal or external.
  - Zero rows after join typically indicates no matching devices for the filtered event set or missing mapping.
- Freshness expectations:
  - Unknown. Treat classifications as near-static but confirm recency if your scenario depends on very recent device changes.
- When to use / When to avoid:
  - Use:
    - To classify users as internal/external by joining RawEventsVSCodeExt on DevDeviceId.
    - To filter dashboards by user type (IsInternal in (['_user_types'])).
    - To ensure consistent internal/external segmentation across analyses.
  - Avoid:
    - Counting events directly from this table (it has no event timestamps).
    - Using RawEventsVSCodeExt.IsInternal as the sole source when consistency with dashboards is required; prefer this fact table.
- Similar tables & how to choose:
  - RawEventsVSCodeExt also contains an IsInternal column, but product logic uses fact_user_isinternal for authoritative classification. Prefer fact_user_isinternal in joins; fall back to the event stream’s IsInternal only if the fact table isn’t available.
- Common Filters:
  - Typically used via inner join to event tables:
    - ... | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
  - Post-join filters: IsInternal in (['_user_types']).
- Table columns:

| Column     | Type  | Description or meaning |
|------------|-------|------------------------|
| DevDeviceId| string| Device identifier; join key to event streams (RawEventsVSCodeExt.DevDeviceId). |
| IsInternal | long  | Internal classification flag (likely 0/1). Used to segment internal vs external users. |
- Column Explain:
  - DevDeviceId: Always join key from events to this fact table; ensure it’s present in your event subset before joining.
  - IsInternal: Use in downstream filters (IsInternal in (['_user_types'])). Treat as authoritative classification for dashboards.

Notes and best practices:
- Timezone and refresh delay are unspecified. Use cautious time windows (e.g., last 7 days) and avoid including the current hour/day when precision matters.
- Dynamic fields extraction:
  - Always cast dynamic fields: sessionId = tostring(Properties["sessionid"]), tokens = toint(Measures["tokens"]).
  - For JSON arrays in Properties (e.g., recipes, updateddependencies), use parse_json(...) then mv-expand.
- Scaling queries:
  - Start with tight filters (specific EventName, limited time window) and small aggregates. Expand union and percentile operations gradually to control cost and latency.

## Views (Reusable Layers)
- View: raw
  - Purpose: Authoritative, parameterized base scope for all queries of VS Code Java Upgrade events, including time range, version gating, internal/external join and filter, and sessionId derivation.
  - Inputs: VSCodeExt.RawEventsVSCodeExt + join VSCodeInsights.fact_user_isinternal on DevDeviceId.
  - Outputs: Event rows scoped to the product with sessionId, major/minor versions, IsInternal segment, ready for further filtering.
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
  - Dependents: All queries referencing raw.

- View: result
  - Purpose: Per-session outcome classification across stages using openrewrite and buildfix results.
  - Inputs: raw view
  - Outputs: One row per session with result in {"Succeeded","BuildFixFailed","OpenResultFailed","Incomplete"} and version metadata.
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
  - Dependents: Success rates, version cross-tabs, token usage by outcome.

- View: updatedependencies
  - Purpose: Parse updated dependency list from planstarted event for per-dependency analysis.
  - Inputs: raw view
  - Outputs: One row per dependency with source/target versions and session.
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
  - Purpose: Identify sessions with early task failures excluding explicit OpenRewrite failures.
  - Inputs: raw view
  - Outputs: sessionId set for sessions failing at task 1 without OpenRewrite failure message.
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
  - Dependents: Diagnostic deep-dives into early pipeline failures.

## Query Building Blocks (Copy-paste snippets)

- Time window template (with effective end time)
  ```kusto
  let _lagHours = 6; // adjust as needed if ingestion delay is suspected
  let _endTime = now(-1h * _lagHours);
  let _startTime = _endTime - 7d;
  let _versions = dynamic([]);       // e.g., ["1.10.0","1.11.0"]; empty => all
  let _user_types = dynamic([]);     // e.g., [0,1]; empty => all
  let base = database("VSCodeExt").RawEventsVSCodeExt
  | where ExtensionName == "vscjava.vscode-java-upgrade"
  | where tostring(Properties["sessionid"]) != "MOCKSESSION"
  | where ServerTimestamp between (_startTime .. _endTime)
  | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
           minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
  | where majorVersion > 0 or minorVersion >= 10
  | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
  | where isempty(_versions) or ExtensionVersion in (_versions)
  | where isempty(_user_types) or IsInternal in (_user_types)
  | extend sessionId = tostring(Properties["sessionid"]);
  ```

- Join template (authoritative internal/external classification)
  ```kusto
  ... // your scoped events
  | join kind=inner (database("VSCodeInsights").fact_user_isinternal) on DevDeviceId
  | project-away IsInternal1
  ```

- De-duplication patterns
  - Keep latest per key by time:
    ```kusto
    ... | summarize arg_max(ServerTimestamp, *) by sessionId
    ```
  - Unique set:
    ```kusto
    ... | distinct sessionId
    ```

- Important filters (default exclusions/gates)
  ```kusto
  // Scope to product and exclude test sessions
  | where ExtensionName == "vscjava.vscode-java-upgrade"
  | where tostring(Properties["sessionid"]) != "MOCKSESSION"
  // Version gating
  | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
           minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
  | where majorVersion > 0 or minorVersion >= 10
  ```

- ID parsing and derivation
  ```kusto
  // sessionId
  | extend sessionId = tostring(Properties["sessionid"])
  // task and subTask from hierarchical taskid like "1.2"
  | extend taskId = tostring(Properties["taskid"]),
           task = toint(split(taskId, ".")[0]),
           subTask = toint(split(taskId, ".")[1])
  // version cohort
  | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
           minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
  ```

- Error extraction and categorization
  ```kusto
  | extend error = tostring(Properties["errormessage"])
  | where isnotempty(error)
  | extend Category = case(
      error has "Uncommitted changes" or error has "not a git repository", "Git Validation Issues",
      error has "Business\" and \"Enterprise\" plans", "Require Business and Enterprise plans",
      error has "dependency not found" or error has "Invalid Spring Boot version", "Invalid Spring Boot Target Version",
      error has "Please provide a path to an existing JDK" or error has "Maven path is required"
        or error has "not a valid JDK installation path" or error has "Gradle wrapper not found", "Java Runtime Issues (JDK/Maven/Gradle)",
      error has "Unsupported project type", "Unsupported project type",
      "Others"
    )
  ```

- Sharded union (template)
  ```kusto
  union isfuzzy=true
    cluster("<cluster>").database("VSCodeExt").RawEventsVSCodeExt
  | where ExtensionName == "vscjava.vscode-java-upgrade"
  | project-rename TimeCol = ServerTimestamp
  | summarize sessions = dcount(tostring(Properties["sessionid"])) by bin(TimeCol, 1d)
  ```

## Example Queries (with explanations)

1) Stage coverage and conversion by event across users and sessions
- Description: Computes session and user coverage for each event in the canonical pipeline order, handling events without sessionId. Uses raw, derives totals, and outputs percentages. Adapt time by setting ['_startTime']/['_endTime']; expand the eventOrder array if new stages are added.
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

2) Success rate by build tool at confirm plan
- Description: Joins session-level result classification to build tools, computing session/user success rates. Adjust time and version cohorts via raw view parameters.
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

3) Success rate by source and target Java versions
- Description: Derives source/target Java versions from Properties and computes success rates per version pair. Use to identify upgrade paths with low/high success.
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

4) Top error messages across sessions for error events
- Description: Extracts error messages where eventtype == "error", reporting top messages by distinct VSCodeSessionId. Tune top N and add stage filters if needed.
```kusto
raw
| extend eventType = tostring(Properties["eventtype"])
| where eventType == "error"
| extend errorMessage = tostring(Properties["errormessage"])
| where isnotempty(errorMessage)
| summarize dcount(VSCodeSessionId) by errorMessage 
| top 50 by dcount_VSCodeSessionId
```

5) Funnel: session counts and ratios across key stages
- Description: Builds a stage-to-stage funnel with counts and ratios relative to confirmed plan sessions. Toggle commented lines to include intermediate “started” stages. Useful for end-to-end conversion.
```kusto
let createPlan = raw
| where EventName == "vscjava.vscode-java-upgrade/confirmplan.end"
| summarize dcount(sessionId)
| project Stage = "Plan Confirmed/Created", Sessions = dcount_sessionId, order = 0;
let openrewrite_started = raw
| where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.start"
| summarize dcount(sessionId)
| project Stage = "OpenRewrite Started", Sessions = dcount_sessionId, order = 1;
let openrewrite = raw
| where EventName ==  "vscjava.vscode-java-upgrade/openrewrite.end" and Properties["result"] == "succeed"
| summarize dcount(sessionId)
| project Stage = "OpenRewrite Succeeded", Sessions = dcount_sessionId, order = 2;
let buildFix_started = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.start"
| summarize dcount(sessionId)
| project Stage = "Build Fix Started", Sessions = dcount_sessionId, order = 3;
let buildFix = raw
| where EventName == "vscjava.vscode-java-upgrade/buildfix.end"and Properties["result"] == "true"
| summarize dcount(sessionId)
| project Stage = "Build Fix Succeeded", Sessions = dcount_sessionId, order = 4;
let cve_started = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecves.start"
| distinct sessionId, cves = tostring(Properties["cves"])
| summarize dcount(sessionId)
| project Stage = "CVE Validation Started/Build project Succeeded", Sessions = dcount_sessionId, order = 5;
let cve = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecves.end"
| distinct sessionId, cves = tostring(Properties["cves"])
| summarize dcountif(sessionId, isempty( cves))
| project Stage = "CVE Validation Passed", Sessions = dcountif_sessionId, order = 6;
let consistency_started = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.start"
| summarize dcount(sessionId)
| project Stage = "Consistency Validation Started", Sessions = dcount_sessionId, order = 7;
let consistency = raw
| where EventName == "vscjava.vscode-java-upgrade/validatecodebehaviorconsistency.end"
| distinct sessionId, behaviorChangesCount = toint(Measures["behaviorchangescount"]), brokenFilesCount = toint(Measures["brokenfilescount"])
| summarize dcountif(sessionId, behaviorChangesCount ==0 and brokenFilesCount  == 0)
| project Stage = "Consistency Validation Passed", Sessions = dcountif_sessionId, order = 8;
let summarize_started = raw
| where EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.start"
| summarize dcount(sessionId)
| project Stage = "Summarizing started", Sessions = dcount_sessionId, order = 9;
let summarize_ended = raw
| where EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.end"
| summarize dcount(sessionId)
| project Stage = "Summarizing ended", Sessions = dcount_sessionId, order = 10;
let data = createPlan
// | union openrewrite_started
| union openrewrite
| union buildFix_started
// | union buildFix
| union cve_started
// | union cve
| union consistency_started
// | union consistency
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

6) LLM token percentiles by caller
- Description: Aggregates LLM request tokens per session and reports percentiles by caller. Use this to detect heavy token users or regressions.
```kusto
raw
| where EventName has "vscjava.vscode-java-upgrade/llmclient.sendrequest"
| extend caller = tostring(Properties["caller"])
| extend completionToken = toint(Measures["completiontoken"]),prompToken = toint(Measures["prompttoken"]), tokens = toint(Measures["tokens"])
| summarize completionToken = sum(completionToken), prompToken = sum(prompToken), tokens = sum(tokens) by sessionId, caller
| summarize percentiles(tokens, 50, 75, 90, 95), max(tokens) by caller
```

7) Copilot Chat toolCalls for Java upgrade conversations
- Description: Links VS Code sessions from Java upgrade to Copilot chat panel requests, counts toolCalls per conversation where javaupgrade tool appears, and summarizes distribution. Helpful for understanding chat-tool engagement.
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

8) OpenRewrite recipe success ratio
- Description: Among openrewrite.end events, compares succeeded sessions to total per recipeId to compute succeededRatio. Useful to spot recipes with lower success.
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
| project 
    sessionId,
    recipeId = tostring(recipe.id),
    recipeName = recipe.name,
    recipeDescription = recipe.description,
    recipeTarget = recipe.target,
    recipeDependencies = recipe.dependencyGroups
| join kind=leftouter succeeded on sessionId
| summarize total = dcount(sessionId), succeeded = dcount(sessionId1) by recipeId
| extend succeededRatio = succeeded * 1.0 / total
```

## Reasoning Notes (only if uncertain)
- Timezone: Not specified. We assume UTC for ServerTimestamp filters because Kusto stores datetimes in UTC unless otherwise noted.
- Ingestion delay: Unknown. We recommend an effective end time offset (e.g., 6 hours) or using the last full day gate for stability.
- IsInternal type: The event stream shows IsInternal as bool; the mapping table shows IsInternal as long (0/1). We standardize on the mapping table and treat values as numeric flags for filters.
- User identity for counting: Both DevDeviceId and VSCodeMachineId exist. Use VSCodeMachineId for user dcounts in stage/query metrics; use DevDeviceId when you need consistent segmentation with IsInternal.
- Session identity: sessionId is derived from Properties["sessionid"]; some generateplan events might lack sessionId (handled in queries via noSessionEvents). We keep those events in coverage but exclude from session-based percentages where appropriate.
- Success definitions: Derived from provided queries—buildfix.end "true" => Succeeded; openrewrite.end "failed" => OpenResultFailed; absence of these indicates Incomplete. We adopt these because they are explicitly encoded in the result view.
- Validation pass logic: CVE pass defined as empty cves; consistency pass as behaviorChangesCount == 0 and brokenFilesCount == 0. Adopted per queries; alternative interpretations should be validated with owners.
- Current-day inclusion: Numbers may fluctuate; prefer previous full day for published KPIs.