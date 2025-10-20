# Internal Power BI Dashboard - Funnel report and investigation - Product and Data Overview Template

## 1. Product Overview

This schema documents the Internal Power BI Dashboard focused on Funnel report and investigation. It captures cross-source event definitions, counting rules, and Kusto query building blocks that power assessment, migration, and upgrade funnels. The goal is to enable PMAgent to interpret product-specific ADX data consistently across clusters and to support automated analysis and troubleshooting for the dashboard.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
Internal Power BI Dashboard - Funnel report and investigation
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
ama4j.westus2.kusto.windows.net
- **Kusto Database**:
bi
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Internal Power BI Dashboard - Funnel report and investigation - Kusto Query Playbook

## Overview
- Internal Power BI Dashboard. This is for Funnel report and investigation
- Primary cluster/database: ama4j.westus2.kusto.windows.net / bi
- Alternate clusters/databases referenced by the product:
  - ddtelvscode.kusto.windows.net / VSCodeExt and VsCodeInsights
  - ddtelai.kusto.windows.net / Copilot

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - ServerTimestamp (RawEventsVSCodeExt; VSCodeExt)
  - timestamp (RawEventsTraces; Copilot)
- Canonical Time Column: ServerTimestamp
  - Alias other timestamp columns to ServerTimestamp via project-rename or project:
    - Example: project ServerTimestamp = timestamp
- Typical windows: last 28 days with day boundary alignment
  - let start = startofday(ago(28d));
  - let end = startofday(now());
- Effective end time:
  - Many queries exclude current day’s partial data by using (end - 1s) or by using startofday(now()) for end.
  - Recommendation: If freshness is unknown, query up to the previous full day.
- bin() usage: Not observed in provided queries; grouping is mostly by keys and stage flags.
- Timezone: Unknown. Default to UTC for cross-source alignment.

### Freshness & Completeness Gates
- Ingestion cadence: Unknown across sources.
- Pattern used:
  - End is set to the start of the current day (startofday(now())) and some slices use end - 1s to avoid partial current-day data.
- Recommended completeness gate:
  - Use the last day where all sentinel sources (VSCodeExt and Copilot) report at least minimal rows, or default to the previous full day/week.
  - Example pattern: compute per-source row counts per day, pick the most recent day where counts cross a threshold (e.g., > 100 rows per source).

### Joins & Alignment
- Frequent keys:
  - DevDeviceId (device identity across sources)
  - VSCodeSessionId (VS Code session identity)
  - sessionId (upgrade workflow session; derived from Properties["sessionid"])
  - appId (hashed app identity; derived from Properties["hashedappid"])
  - ExtensionVersion (version cohort)
- Typical join kinds:
  - inner for cohort restriction (e.g., require inclusion in the initial stage)
  - leftouter to enrich with attributes (e.g., internal/external user mapping)
  - rightouter used to preserve root rows after pre-alignment enrichment
- Post-join hygiene:
  - Use project-rename to align time columns
  - Use project-away to drop intermediate fields (e.g., EventName, Measures, Properties after deriving flags)
  - Use distinct to de-duplicate at the stage boundary

### Filters & Idioms
- Common predicates:
  - has and in() for string/collection membership, matches regex for patterns, and !has for exclusions
  - Semantically important filters:
    - ExtensionName filters:
      - "vscjava.vscode-java-upgrade" with version gates (major >= 1 AND minor >= 2), exclude "SNAPSHOT"
      - "migrate-java-to-azure" for migration flows
      - "GitHub.copilot-chat" panel requests
    - EventName filters:
      - Tool invocations: 'java/migrateassistant/tool/invoke'
      - Stage markers: start/end events
    - Status gates:
      - status == 'start' (AppCAT start), Properties["result"] != 'failed'
    - AppCAT version exclude: appcatVersion !in ('latest','experimental')
- Cohort construction:
  - Build the base cohort (e.g., users_assessment or users_migration) and then join kind=inner to keep the cohort across subsequent stages.

### Cross-cluster/DB & Sharding
- Qualification:
  - cluster('https://...').database('...').table('...')
  - RawEventsVSCodeExt: ddtelvscode.kusto.windows.net / VSCodeExt
  - fact_user_isinternal: ddtelvscode.kusto.windows.net / VsCodeInsights
  - RawEventsTraces: ddtelai.kusto.windows.net / Copilot
  - Helper functions: ama4j.westus2.kusto.windows.net / bi
- Union pattern:
  - When merging same logical events from different sources:
    - Normalize keys and time columns (alias timestamp -> ServerTimestamp)
    - union then distinct on the key tuple (e.g., DevDeviceId, ExtensionVersion, etc.)
    - Join internal/external flag after union to avoid duplication

### Table classes
- Fact/event tables:
  - VSCodeExt.RawEventsVSCodeExt (event logs with ServerTimestamp)
  - Copilot.RawEventsTraces (traces with timestamp/customDimensions)
- Snapshot/mapping:
  - VsCodeInsights.fact_user_isinternal (internal/external mapping by DevDeviceId)
- Curated/aggregated helpers (external functions in bi):
  - assessment_run_records_helper, assessment_precheck_records_helper, assessment_success_occurrence_vscode_helper, migration_records_helper, migration_records_with_java_helper, narrow_migration_records_helper_Java, build_result_records_helper, build_result_records_with_appid_helper
  - Use these to define cohorts and success flags. Treat them as fact-like views; avoid re-deriving if available.

### Important Mapping
- Internal/external user segmentation:
  - Join fact_user_isinternal by DevDeviceId
  - Derive user_source = iff(IsInternal == 1 or tobool(IsInternal/IsInternal1), 'internal', 'external')
- Stage names used in dashboards:
  - Assessment stages: "Assessment Kick off", "Precheck ran", "Confirmed as Java project", "AppCAT ran", "Report generated"
  - Migration stages (general): "Kick off Migration", "Copilot request for migration plan", "Tool invoked (after user's confirmation)", "Buildfix start", "Buildfix success", "Have Java App"
  - Upgrade stages: "Trigger Java Upgrade", "Plan generated, wait for confirm", "Plan confirmed, ready to execute", "Code remediation started", "Code remediation completed", "Build started", "Build succeeded", "CVE check started/passed", "Behavior check started/passed", "Unit tests started/passed", "Summarize started/completed"

### Additional usage notes and patterns (from Canonical Tables source)
- Time windows and day boundaries:
  - Default to startofday(ago(28d)) .. startofday(now()) to align with the dashboard’s queries.
  - For “end” boundary, some queries use (end - 1s) to avoid overlap; replicate if you see double-counting near midnight.
- Version gating for upgrade workflows:
  - Split ExtensionVersion into major/minor to branch logic (major >= 1 and minor >= 2 for newer behaviors).
  - Exclude SNAPSHOT builds to focus on marketplace releases.
- Internal vs external cohorting:
  - Join fact_user_isinternal on DevDeviceId; derive user_source via IsInternal (or IsInternal1).
  - If the flag column differs in your environment, sample a few rows to confirm the correct column name.
- Dynamic bag parsing:
  - Use parse_json for message/customDimensions when raw strings are present; cast with tostring() before comparisons.
  - Keys used in queries: invokedtoolid, appcatversion, status, callerid, devdeviceid, callerversion, callersessionid, sessionid, hashedappid, modelid, targetdeps, toolcounts, requestid, conversationid.
- Cross-source union:
  - For AppCAT and migration tool invocations, union client (VSCodeExt.RawEventsVSCodeExt) and service (Copilot.RawEventsTraces) to broaden coverage. Expect some discrepancy and potential double counting; de-duplicate by DevDeviceId/VSCodeSessionId if necessary.

## Entity & Counting Rules (Core Definitions)
- Entity model:
  - Device: DevDeviceId (primary identity across sources)
  - Session: VSCodeSessionId (session identity; used in assessment/migration), sessionId (upgrade workflow)
  - App: appId (hashedappid; upgrade workflow)
  - Version: ExtensionVersion (cohort segmentation)
- Grouping levels:
  - Device-level dcount for unique users/devices
  - Session-level dcount to capture distinct workflows within a device
  - App-level dcount for per-app conversions (upgrade)
- Counting rules:
  - Use dcountif(<entity>, <stage gate>) gated by prior stages (e.g., readyExecution == 'succeeded')
  - Use distinct to eliminate duplicate rows per entity per stage
  - For workflows: use arg_min/arg_max across stage flags to capture first/last timestamps
- Business definitions (from provided queries):
  - "Have Java App": IsJavaProject == "true" in precheck
  - "AppCAT ran": AppCAT CLI scan start events post assessment or VSCodeExt AppCAT scan success with specific exit code rules
  - "Kick off Migration": cohort from helper functions in bi
  - "Tool invoked": 'java/migrateassistant/tool/invoke' with tool in ('createMigrationPlan','appmod-run-task')
  - "Copilot request for migration plan": copilot panel requests with toolcounts containing the tool IDs above
  - "Buildfix start/success": build events from helper functions; success flagged by success
  - "Upgrade stage success": stage flags set to 'succeeded' based on specific event names and Properties outcomes

## Views (Reusable Layers)
- No reusable views are defined in the provided content.

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Parameterize analysis window and exclude partial current day when needed.
  - Snippet:
    ```kusto
    // Time window with effective end at start of today (UTC)
    let start = startofday(ago(28d));
    let end = startofday(now());
    // For sources with potential lateness, exclude the current day by subtracting 1 second
    let end_effective = end - 1s;
    ```

- Join template (internal/external mapping and cohort restriction)
  - Description: Enrich entities with internal/external labels; restrict to base cohort.
  - Snippet:
    ```kusto
    // Base cohort (example: assessment or migration cohort)
    let base = cluster('https://ama4j.westus2.kusto.windows.net/')
      .database('bi').assessment_run_records_helper(start, end)
      | distinct DevDeviceId, VSCodeSessionId, ExtensionVersion;

    // Enrichment with internal/external label
    base
    | join kind=leftouter (
        cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal
    ) on DevDeviceId
    | extend user_source = iff(tobool(IsInternal), 'internal', 'external')
    ```

- De-dup pattern
  - Description: Normalize and deduplicate events across multiple sources and stages.
  - Snippets:
    ```kusto
    // Cross-source union with normalized time and keys, then distinct
    let appcat_union =
      (cluster('https://ddtelai.kusto.windows.net/').database('Copilot').RawEventsTraces
       | where timestamp between (start .. end_effective)
       | extend dimensions = parse_json(customDimensions)
       | project ServerTimestamp = timestamp,
                DevDeviceId = tostring(dimensions.devdeviceid),
                VSCodeSessionId = operation_ParentId,
                ExtensionVersion = tostring(dimensions.callerversion))
      | union (
          cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
          | where ServerTimestamp between (start .. end_effective)
          | project ServerTimestamp, DevDeviceId, VSCodeSessionId, ExtensionVersion
        )
      | distinct DevDeviceId, VSCodeSessionId, ExtensionVersion;
    ```

    ```kusto
    // Earliest/latest per stage in a session with arg_min/arg_max
    someWorkflow
    | summarize
        planStartTime = arg_min(iff(isnotempty(planStarted), ServerTimestamp, datetime(null)), planStarted),
        planGeneratedTime = arg_max(iff(isnotempty(planGenerated), ServerTimestamp, datetime(null)), planGenerated)
      by sessionId, appId, DevDeviceId
    ```

- Important filters
  - Description: Standardized predicates for upgrade/migration funnels.
  - Snippets:
    ```kusto
    // Upgrade extension gate: marketplace versions only
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]),
             minorVersion = toint(split(ExtensionVersion, ".", 1)[0]),
             isMarketplaceVersion = iff(ExtensionVersion !has "SNAPSHOT", true, false)
    | where majorVersion >= 1 and minorVersion >= 2
    | where isMarketplaceVersion
    ```

    ```kusto
    // AppCAT: exclude unsupported versions and require start status
    | extend dimensions = parse_json(customDimensions)
    | extend appcatVersion = tostring(dimensions.appcatversion),
             status = tostring(dimensions.status),
             callerid = tostring(dimensions.callerid)
    | where appcatVersion !in ('latest', 'experimental')
    | where status == 'start'
    | where callerid has "migrate-java-to-azure"
    ```

    ```kusto
    // Tool invocation filter (migration assistant)
    | extend tool = tostring(Properties.invokedtoolid)
    | where tool in ('createMigrationPlan','appmod-run-task')
    ```

- Important Definitions
  - Description: Reuse named stage definitions as flags to drive funnel counts.
  - Snippet:
    ```kusto
    // Stage flags for Upgrade workflow derived from EventName and metrics
    | extend planStarted      = iff(EventName == "vscjava.vscode-java-upgrade/generateupgradeplanforjavaproject.start", 'succeeded', ''),
             planGenerated    = iff(EventName == "vscjava.vscode-java-upgrade/confirmupgradeplanforjavaproject.start"
                                    or EventName == "vscjava.vscode-java-upgrade/generateupgradeplanforjavaproject.end", 'succeeded', ''),
             readyExecution   = iff((EventName == "vscjava.vscode-java-upgrade/confirmupgradeplanforjavaproject.end" and (majorVersion < 1 or minorVersion < 2)) or
                                     (EventName == "vscjava.vscode-java-upgrade/setupdevelopmentenvironmentforupgrade.end" and (majorVersion >= 1 and minorVersion >= 2)), 'succeeded', ''),
             remediationStarted = iff(EventName in ("vscjava.vscode-java-upgrade/upgradejavaprojectusingopenrewrite.start",
                                                   "vscjava.vscode-java-upgrade/task.upgradeprojectusingagent.started",
                                                   "vscjava.vscode-java-upgrade/task.upgradeprojectusingairecipes.started"), 'succeeded', ''),
             remediationResult  = iff(EventName in ("vscjava.vscode-java-upgrade/upgradejavaprojectusingopenrewrite.end",
                                                   "vscjava.vscode-java-upgrade/task.upgradeprojectusingagent.completed",
                                                   "vscjava.vscode-java-upgrade/task.upgradeprojectusingairecipes.completed"),
                                      iff(Properties['result']!='failed', 'succeeded', 'failed'), ''),
             buildStarted     = iff(EventName == "vscjava.vscode-java-upgrade/buildjavaproject.start", 'succeeded', ''),
             builtResult      = iff(EventName == "vscjava.vscode-java-upgrade/buildjavaproject.end", tostring(Properties["result"]), ''),
             cveStarted       = iff(EventName == "vscjava.vscode-java-upgrade/validatecvesforjava.start", 'succeeded', ''),
             cveResult        = iff(EventName == "vscjava.vscode-java-upgrade/validatecvesforjava.end",
                                    iff((isempty(Measures["cve.high"]) and isempty(Measures["cve.critical"]) and isempty(Measures["cve.medium"])), "succeeded", "failed"), ''),
             behaviorStarted  = iff(EventName == "vscjava.vscode-java-upgrade/validatebehaviorchangesforjava.start", 'succeeded', ''),
             behaviorResult   = iff(EventName == "vscjava.vscode-java-upgrade/project.state.behaviorchanges",
                                    iff(toint(Measures["numofbehaviorchangestofix"]) == 0, "succeeded", "failed"), ''),
             testStarted      = iff(EventName == "vscjava.vscode-java-upgrade/runtestsforjava.start", 'succeeded', ''),
             testResult       = iff(EventName == "vscjava.vscode-java-upgrade/runtestsforjava.end", tostring(Properties["result"]), ''),
             summarizeStarted = iff(EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.start", 'succeeded', ''),
             summarizeResult  = iff(EventName == "vscjava.vscode-java-upgrade/summarizeupgrade.end", "succeeded", '')
    ```

- ID parsing/derivation
  - Description: Parse JSON payloads to derive keys.
  - Snippets:
    ```kusto
    // Copilot traces: parse customDimensions
    | extend dimensions = parse_json(customDimensions)
    | extend DevDeviceId = tostring(dimensions.devdeviceid),
             VSCodeSessionId = operation_ParentId,
             appcatVersion = tostring(dimensions.appcatversion),
             status = tostring(dimensions.status),
             callerid = tostring(dimensions.callerid)
    ```

    ```kusto
    // VSCodeExt events: session/app IDs
    | extend sessionId = tostring(Properties["sessionid"]),
             appId     = tostring(Properties["hashedappid"])
    | where isnotempty(sessionId) and sessionId != 'unknown'
    ```

- Sharded union
  - Description: Merge regional/sharded sources with consistent schema; normalize before union.
  - Snippet:
    ```kusto
    // Normalize and union two shards/sources
    let srcA =
      cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
      | where ServerTimestamp between (start .. end_effective)
      | project ServerTimestamp, DevDeviceId, VSCodeSessionId, ExtensionVersion, EventName, Properties, Measures;
    let srcB =
      cluster('https://ddtelai.kusto.windows.net/').database('Copilot').RawEventsTraces
      | where timestamp between (start .. end_effective)
      | extend properties = parse_json(customDimensions)
      | project ServerTimestamp = timestamp,
               DevDeviceId = tostring(properties.devdeviceid),
               VSCodeSessionId = tostring(properties.callersessionid),
               ExtensionVersion = tostring(properties.callerversion);
    srcA
    | union srcB
    | distinct DevDeviceId, VSCodeSessionId, ExtensionVersion
    ```

- Additional building blocks (from Canonical Tables source)
  - Filter for migration tool invocations (client-side):
    ```kusto
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (startofday(ago(28d)) .. startofday(now()))
    | where ExtensionName has "migrate-java-to-azure"
    | where EventName has "java/migrateassistant/tool/invoke"
    | extend invokedToolId = tostring(Properties["invokedtoolid"])
    | where invokedToolId in ("createMigrationPlan","appmod-run-task")
    ```

  - Filter for service-side tool invocations (Copilot traces):
    ```kusto
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp between (startofday(ago(28d)) .. startofday(now()))
    | where operation_Name == "java/migrateassistant/tool/invoke"
    | extend dims = parse_json(customDimensions)
    | extend invokedToolId = tostring(dims["invokedtoolid"])
    | where invokedToolId has "appmod-run-task"
    ```

  - Internal/external classification:
    ```kusto
    <your base events>
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(tobool(IsInternal) or IsInternal == 1, "internal", "external")
    ```

## Example Queries (with explanations)

1) Java Assessment Funnel (device cohort and core stages)
- Description: Builds a device cohort for Java Assessment over the last 28 days, marks precheck, Java project confirmation, AppCAT runs (from both Copilot traces and VSCodeExt UI), and report generation, then retains only devices that kicked off assessment.
```kusto
// this query is used to get the user funnel of Java Assessment, to analyze the user conversion rate in the assess process
let start = startofday(ago(28d));
let end = startofday(now());
let users_assessment = materialize(
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').assessment_run_records_helper(start, end)
    | distinct  DevDeviceId,VSCodeSessionId,ExtensionVersion, user_source,type = "Assessment Kick off (Click button or Chat)");
let users_precheck = materialize(
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').assessment_precheck_records_helper(start, end)
    | distinct  DevDeviceId,ExtensionVersion,IsJavaProject, user_source,type = "Precheck ran");
let users_javaproject = 
    users_precheck 
    | where IsJavaProject == "true"
    | distinct  DevDeviceId,ExtensionVersion, user_source,type = "Confirmed as Java project";
let users_appcat = 
    cluster('https://ddtelai.kusto.windows.net/').database('Copilot').table('RawEventsTraces') 
    | where timestamp between (start .. end)
    | where operation_Name == 'java/appcat/command'
    | extend data = parse_json(message)
    | extend command = tostring(data.message)
    | where command == 'analyze'
    | extend dimensions = parse_json(customDimensions)
    | extend appcatVersion = tostring(dimensions.appcatversion)
    | where appcatVersion !in ('latest', 'experimental')
    | extend status = tostring(dimensions.status)
    | where status == 'start'
    | extend callerid = tostring(dimensions.callerid)
    | where callerid has "migrate-java-to-azure"
    | project ServerTimestamp=timestamp, DevDeviceId=tostring(dimensions.devdeviceid),VSCodeSessionId = operation_ParentId
    | join kind=leftouter (
        users_assessment | distinct VSCodeSessionId,ExtensionVersion
    ) on VSCodeSessionId
    // the devdevice id in appcat cli may be consistent with the one in VSCodeExt
    // So the devdeviceid count may increase by the union. But the discrepancy is acceptable.
    | union (
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. end)
        | where EventName == 'vscjava.migrate-java-to-azure/java/migrateassistant/appcat/scan' and (Properties.result == 'success' or Properties.error !has "with exit code: 199" and Properties.error matches regex @"with exit code: \d+")
        | project DevDeviceId,VSCodeSessionId,ServerTimestamp,ExtensionVersion
    )
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source = iff(IsInternal == 1, 'internal', 'external')
    | distinct  DevDeviceId,ExtensionVersion, user_source,type = "AppCAT ran";
let users_report = 
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').assessment_success_occurrence_vscode_helper(start, end)
    | distinct  DevDeviceId,ExtensionVersion, user_source,type = "Report generated";
union users_assessment,users_precheck,users_javaproject,users_appcat,users_report
| join kind=inner (users_assessment | project DevDeviceId) on DevDeviceId
```

2) Java Upgrade Workflow Summary (counts per stage, segmented by internal/external)
- Description: Constructs the Upgrade workflow stages per session/app/device, enriches with internal/external, and summarizes device/session/app dcount across gates. Adapt by adjusting start/end and join filters.
```kusto
// this query is used to get the user funnel of Java Upgrade, to analyze the user conversion rate in the upgrade process
let start = startofday(ago(28d));
let end = startofday(now()));
let _isMarketplaceVersion = true;
// baseQuery root
let root = () {
    database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where ServerTimestamp  between (start .. end)
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]), minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion >=1 and minorVersion >=2
    | extend isMarketplaceVersion = iff(ExtensionVersion !has "SNAPSHOT", true, false)
    | where isempty(['_isMarketplaceVersion']) or isMarketplaceVersion == ['_isMarketplaceVersion']
    | extend sessionId = tostring(Properties["sessionid"])
    | extend appId = tostring(Properties["hashedappid"])
};
// baseQuery filtered
let filtered = () {
    root
    | where isnotempty(sessionId) and sessionId != 'unknown'
    | extend model = tostring(Properties["modelid"])
    | extend targetdeps = tostring(Properties["targetdeps"])
    | summarize arg_min(ServerTimestamp,targetdeps), arg_min(ServerTimestamp, model) by sessionId
    | project model, targetdeps, infoSessionId=sessionId
    | join kind=rightouter root on $left.infoSessionId == $right.sessionId
};
// baseQuery inSession
let inSession = () {
    filtered
    | where isnotempty(sessionId) and sessionId != 'unknown'
};
// baseQuery workflow
let workflow = () {
    inSession
    | project DevDeviceId, sessionId, appId, ServerTimestamp, ExtensionVersion, EventName, majorVersion, minorVersion, Measures, Properties
    | extend planStarted=iff(EventName=="vscjava.vscode-java-upgrade/generateupgradeplanforjavaproject.start",'succeeded','')
    | extend planGenerated=iff(EventName=="vscjava.vscode-java-upgrade/confirmupgradeplanforjavaproject.start" or EventName=="vscjava.vscode-java-upgrade/generateupgradeplanforjavaproject.end", 'succeeded','')
    | extend readyExecution=iff((EventName == "vscjava.vscode-java-upgrade/confirmupgradeplanforjavaproject.end" and (majorVersion <1 or minorVersion <2)) or
     (EventName == "vscjava.vscode-java-upgrade/setupdevelopmentenvironmentforupgrade.end" and (majorVersion >=1 and minorVersion >=2)),'succeeded', '')
    // remediation
    | extend remediationStarted=iff(EventName in("vscjava.vscode-java-upgrade/upgradejavaprojectusingopenrewrite.start", "vscjava.vscode-java-upgrade/task.upgradeprojectusingagent.started", "vscjava.vscode-java-upgrade/task.upgradeprojectusingairecipes.started"), 'succeeded', '')
    | extend remediationResult=iff(EventName in("vscjava.vscode-java-upgrade/upgradejavaprojectusingopenrewrite.end", "vscjava.vscode-java-upgrade/task.upgradeprojectusingagent.completed", "vscjava.vscode-java-upgrade/task.upgradeprojectusingairecipes.completed"), iff(Properties['result']!='failed', 'succeeded', 'failed'), '')
    // build
    | extend buildStarted=iff(EventName=="vscjava.vscode-java-upgrade/buildjavaproject.start", 'succeeded', '')
    | extend builtResult=iff(EventName=="vscjava.vscode-java-upgrade/buildjavaproject.end", tostring(Properties["result"]), '')
    // cve
    | extend cveStarted=iff(EventName=="vscjava.vscode-java-upgrade/validatecvesforjava.start", 'succeeded', '')
    | extend cveResult=iff(EventName=="vscjava.vscode-java-upgrade/validatecvesforjava.end", iff((isempty(Measures["cve.high"]) and isempty(Measures["cve.critical"]) and isempty(Measures["cve.medium"])), "succeeded", "failed"), '')
    // behavior
    | extend behaviorStarted=iff(EventName=="vscjava.vscode-java-upgrade/validatebehaviorchangesforjava.start", 'succeeded','')
    | extend behaviorResult=iff(EventName=="vscjava.vscode-java-upgrade/project.state.behaviorchanges", iff((toint(Measures["numofbehaviorchangestofix"])==0), "succeeded", "failed"), '')
    // test
    | extend testStarted=iff(EventName=="vscjava.vscode-java-upgrade/runtestsforjava.start", 'succeeded', '')
    | extend testResult=iff(EventName=="vscjava.vscode-java-upgrade/runtestsforjava.end", tostring(Properties["result"]), '') 
    // summarize
    | extend summarizeStarted=iff(EventName=="vscjava.vscode-java-upgrade/summarizeupgrade.start", 'succeeded','')
    | extend summarizeResult=iff(EventName=="vscjava.vscode-java-upgrade/summarizeupgrade.end","succeeded",'')
    | project-away EventName, majorVersion, minorVersion, Measures, Properties
    | where isnotempty(planStarted) or isnotempty(planGenerated) or isnotempty(readyExecution) or isnotempty(remediationStarted) or isnotempty(remediationResult) or isnotempty(buildStarted) or isnotempty(builtResult) or isnotempty(cveStarted) or isnotempty(cveResult) or isnotempty( behaviorStarted) or isnotempty(behaviorResult) or isnotempty( testStarted) or isnotempty(testResult) or isnotempty( summarizeStarted) or isnotempty(summarizeResult)
    | summarize 
        take_any(ExtensionVersion),
        planStartTime=arg_min(iff(isnotempty(planStarted), ServerTimestamp, datetime(null)), planStarted),
        planGeneratedTime=arg_max(iff(isnotempty(planGenerated), ServerTimestamp, datetime(null)), planGenerated),
        readyExcutionTime=arg_max(iff(isnotempty(readyExecution), ServerTimestamp, datetime(null)), readyExecution),
        remediationStartTime=arg_min(iff(isnotempty(remediationStarted), ServerTimestamp, datetime(null)), remediationStarted),
        remediationEndTime=arg_max(iff(isnotempty(remediationResult), ServerTimestamp, datetime(null)), remediationResult),
        buildStartTime=arg_min(iff(isnotempty(buildStarted), ServerTimestamp, datetime(null)), buildStarted),
        buildEndTime=arg_max(iff(isnotempty(builtResult), ServerTimestamp, datetime(null)), builtResult),
        cveStartTime=arg_min(iff(isnotempty(cveStarted), ServerTimestamp, datetime(null)), cveStarted),
        cveEndTime=arg_max(iff(isnotempty(cveResult), ServerTimestamp, datetime(null)), cveResult),
        behaviorStartTime=arg_min(iff(isnotempty(behaviorStarted), ServerTimestamp, datetime(null)), behaviorStarted),
        behaviorEndTime=arg_max(iff(isnotempty(behaviorResult), ServerTimestamp, datetime(null)), behaviorResult),
        testStartTime=arg_min(iff(isnotempty(testStarted), ServerTimestamp, datetime(null)), testStarted),
        testEndTime=arg_max(iff(isnotempty(testResult), ServerTimestamp, datetime(null)), testResult),
        summarizeStartTime=arg_min(iff(isnotempty(summarizeStarted), ServerTimestamp, datetime(null)), summarizeStarted),
        summarizeEndTime=arg_max(iff(isnotempty(summarizeResult), ServerTimestamp, datetime(null)), summarizeResult)
        by sessionId, appId, DevDeviceId
};
workflow
| join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
| summarize
    planStartedDevices=dcountif(DevDeviceId, planStarted=='succeeded'),
    planStartedSessions=dcountif(sessionId, planStarted=='succeeded'),
    planStartedApps=dcountif(appId, planStarted=='succeeded'),
    planGeneratedDevices=dcountif(DevDeviceId, planGenerated=='succeeded'),
    planGeneratedSessions=dcountif(sessionId, planGenerated=='succeeded'),
    planGeneratedApps=dcountif(appId, planGenerated=='succeeded'),
    readyExecutionDevices=dcountif(DevDeviceId, readyExecution=='succeeded'),
    readyExecutionSessions=dcountif(sessionId, readyExecution=='succeeded'),
    readyExecutionApps=dcountif(appId, readyExecution=='succeeded'),
    remediationStartedDevices=dcountif(DevDeviceId, remediationStarted=='succeeded' and readyExecution =='succeeded'),
    remediationStartedSessions=dcountif(sessionId, remediationStarted=='succeeded' and readyExecution =='succeeded'),
    remediationStartedApps=dcountif(appId, remediationStarted=='succeeded' and readyExecution =='succeeded'),
    remediationSucceededDevices=dcountif(DevDeviceId, remediationResult=='succeeded' and readyExecution =='succeeded'),
    remediationSucceededSessions=dcountif(sessionId, remediationResult=='succeeded' and readyExecution =='succeeded'),
    remediationSucceededApps=dcountif(appId, remediationResult=='succeeded' and readyExecution =='succeeded'),
    buildStartedDevices=dcountif(DevDeviceId, buildStarted=='succeeded' and readyExecution =='succeeded'),
    buildStartedSessions=dcountif(sessionId, buildStarted=='succeeded' and readyExecution =='succeeded'),
    buildStartedApps=dcountif(appId, buildStarted=='succeeded' and readyExecution =='succeeded'),
    builtSucceededDevices=dcountif(DevDeviceId, builtResult == "succeeded" and readyExecution =='succeeded'),
    builtSucceededSessions=dcountif(sessionId, builtResult == "succeeded" and readyExecution =='succeeded'),
    builtSucceededApps=dcountif(appId, builtResult == "succeeded" and readyExecution =='succeeded'),
    cveStartedDevices=dcountif(DevDeviceId, cveStarted=='succeeded' and readyExecution =='succeeded'),
    cveStartedSessions=dcountif(sessionId, cveStarted=='succeeded' and readyExecution =='succeeded'),
    cveStartedApps=dcountif(appId, cveStarted=='succeeded' and readyExecution =='succeeded'),
    cveSucceededDevices=dcountif(DevDeviceId, cveResult == "succeeded" and readyExecution =='succeeded'),
    cveSucceededSessions=dcountif(sessionId, cveResult == "succeeded" and readyExecution =='succeeded'),
    cveSucceededApps=dcountif(appId, cveResult == "succeeded" and readyExecution =='succeeded'),
    behaviorStartedDevices=dcountif(DevDeviceId, behaviorStarted=='succeeded' and readyExecution =='succeeded'),
    behaviorStartedSessions=dcountif(sessionId, behaviorStarted=='succeeded' and readyExecution =='succeeded'),
    behaviorStartedApps=dcountif(appId, behaviorStarted=='succeeded' and readyExecution =='succeeded'),
    behaviorSucceededDevices=dcountif(DevDeviceId, behaviorResult == "succeeded" and readyExecution =='succeeded'),
    behaviorSucceededSessions=dcountif(sessionId, behaviorResult == "succeeded" and readyExecution =='succeeded'),
    behaviorSucceededApps=dcountif(appId, behaviorResult == "succeeded" and readyExecution =='succeeded'),
    testStartedDevices=dcountif(DevDeviceId, testResult=='succeeded' and readyExecution =='succeeded'),
    testStartedSessions=dcountif(sessionId, testResult=='succeeded' and readyExecution =='succeeded'),
    testStartedApps=dcountif(appId, testResult=='succeeded' and readyExecution =='succeeded'),
    testSucceededDevices=dcountif(DevDeviceId, testResult == "succeeded" and readyExecution =='succeeded'),
    testSucceededSessions=dcountif(sessionId, testResult == "succeeded" and readyExecution =='succeeded'),
    testSucceededApps=dcountif(appId, testResult == "succeeded" and readyExecution =='succeeded'),
    summarizeStartedDevices=dcountif(DevDeviceId, summarizeStarted =='succeeded' and readyExecution =='succeeded'),
    summarizeStartedSessions=dcountif(sessionId, summarizeStarted =='succeeded' and readyExecution =='succeeded'),
    summarizeStartedApps=dcountif(appId, summarizeStarted =='succeeded' and readyExecution =='succeeded'),
    summarizedDevices=dcountif(DevDeviceId,summarizeResult=='succeeded' and readyExecution =='succeeded'),
    summarizedSessions=dcountif(sessionId,summarizeResult=='succeeded' and readyExecution =='succeeded'),
    summarizedApps=dcountif(appId,summarizeResult=='succeeded' and readyExecution =='succeeded') by user_source
| extend data = bag_pack(
    "Trigger Java Upgrade", bag_pack("Devices", planStartedDevices, "Apps", planStartedApps, "Sessions", planStartedSessions),
    "Plan generated, wait for confirm", bag_pack("Devices", planGeneratedDevices, "Apps", planGeneratedApps, "Sessions", planGeneratedSessions),
    "Plan confirmed, ready to execute", bag_pack("Devices", readyExecutionDevices, "Apps", readyExecutionApps, "Sessions", readyExecutionSessions),
    "Code remediation started", bag_pack("Devices", remediationStartedDevices, "Apps", remediationStartedApps, "Sessions", remediationStartedSessions),
    "Code remediation completed", bag_pack("Devices", remediationSucceededDevices, "Apps", remediationSucceededApps, "Sessions", remediationSucceededSessions),
    "Build started", bag_pack("Devices", buildStartedDevices, "Apps", buildStartedApps, "Sessions", buildStartedSessions),
    "Build succeeded", bag_pack("Devices", builtSucceededDevices, "Apps", builtSucceededApps, "Sessions", builtSucceededSessions),
    "CVE check started", bag_pack("Devices", cveStartedDevices, "Apps", cveStartedApps, "Sessions", cveStartedSessions),
    "CVE check passed", bag_pack("Devices", cveSucceededDevices, "Apps", cveSucceededApps, "Sessions", cveSucceededSessions),
    "Behavior check started", bag_pack("Devices", behaviorStartedDevices, "Apps", behaviorStartedApps, "Sessions", behaviorStartedSessions),
    "Behavior check passed", bag_pack("Devices", behaviorSucceededDevices, "Apps", behaviorSucceededApps, "Sessions", behaviorSucceededSessions),
    "Unit tests started", bag_pack("Devices", testStartedDevices, "Apps", testStartedApps, "Sessions", testStartedSessions),
    "Unit tests passed", bag_pack("Devices", testSucceededDevices, "Apps", testSucceededApps, "Sessions", testSucceededSessions),
    "Summarize started", bag_pack("Devices", summarizeStartedDevices, "Apps", summarizeStartedApps, "Sessions", summarizeStartedSessions),
    "Summarize completed", bag_pack("Devices", summarizedDevices, "Apps", summarizedApps, "Sessions", summarizedSessions)
)
| mv-expand stage_data = data
| project Stage = tostring(bag_keys(stage_data)[0]), 
          Devices = toint(stage_data[tostring(bag_keys(stage_data)[0])].Devices),user_source
```

3) Upgrade Base Filter and Pre-alignment
- Description: Filters to market versions, normalizes session fields, and preserves root rows after enrichment using rightouter join.
```kusto
let start = startofday(ago(28d));
let end = startofday(now());

let root = () {
    database("VSCodeExt").RawEventsVSCodeExt
    | where ExtensionName == "vscjava.vscode-java-upgrade"
    | where ServerTimestamp  between (start .. end)
    | extend majorVersion = toint(split(ExtensionVersion, ".", 0)[0]), minorVersion = toint(split(ExtensionVersion, ".", 1)[0])
    | where majorVersion >=1 and minorVersion >=2
    | extend isMarketplaceVersion = iff(ExtensionVersion !has "SNAPSHOT", true, false)
    | extend sessionId = tostring(Properties["sessionid"])
    | extend appId = tostring(Properties["hashedappid"])
};

let filtered = () {
    root
    | where isnotempty(sessionId) and sessionId != 'unknown'
    | extend model = tostring(Properties["modelid"])
    | extend targetdeps = tostring(Properties["targetdeps"])
    | summarize arg_min(ServerTimestamp,targetdeps), arg_min(ServerTimestamp, model) by sessionId
    | project model, targetdeps, infoSessionId=sessionId
    | join kind=rightouter root on $left.infoSessionId == $right.sessionId
};
```

4) General Migration Funnel (broad coverage, includes migrate-by-prompt and build-only)
- Description: Cohort from migration_records_helper, links Copilot requests and tool invocations, and build events; segments internal/external. Adjust the window and the Copilot/VSCodeExt filters to change coverage.
```kusto
//As of last 28 days. This funnel covers all users involved in general migration, including those using migrate-by-prompt, containerization, and build-only approaches. As a result, may not accurately represent conversions along the classical migration path.
let start = startofday(ago(28d));
let end = startofday(now());
let users_migration = materialize(
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').migration_records_helper(start, end)
    | distinct DevDeviceId,VSCodeSessionId,ExtensionVersion, user_source,type = "Kick off Migration");
let users_migration_java = cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').migration_records_with_java_helper(start,end)
    | distinct DevDeviceId,VSCodeSessionId,ExtensionVersion, user_source,type = "Have Java App";
let users_tool_invoke =
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool in ('createMigrationPlan','appmod-run-task')
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
        | project ServerTimestamp, DevDeviceId, user_source,Properties,ExtensionVersion
        | union (
            cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
            | where timestamp  between (start .. (end - 1s))
            | where timestamp >= datetime(2025-07-31)
            | where operation_Name == "java/migrateassistant/tool/invoke"
            | extend properties = parse_json(customDimensions)
            | extend invokedToolId = tostring(properties["invokedtoolid"])\
            | where invokedToolId has 'appmod-run-task'
            | extend DevDeviceId = tostring(properties.devdeviceid)
            | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
            | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
            | extend ExtensionVersion = tostring(properties.callerversion)
        )
        | distinct DevDeviceId,ExtensionVersion, user_source,type = "Tool invoked (after user's confirmation)";
let users_copilot_request = 
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. end)
    | where ExtensionName == 'GitHub.copilot-chat'
    | where EventName == "github.copilot-chat/panel.request"
    | where VSCodeSessionId in (users_migration | distinct VSCodeSessionId) or DevDeviceId in (users_migration | distinct DevDeviceId) 
    | project ServerTimestamp,EventName,VSCodeSessionId, requestId = tostring(Properties.requestid), conversationId = tostring(Properties.conversationid), DevDeviceId,Properties,toolcounts = tostring(Properties.toolcounts), Measures
    | project DevDeviceId, toolcounts,requestId, ServerTimestamp, Properties,VSCodeSessionId
    | where toolcounts has 'appmod-run-task' or toolcounts has 'createMigrationPlan'
    | join kind=leftouter (
        users_migration 
        | distinct VSCodeSessionId, ExtensionVersion
    ) on VSCodeSessionId
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
    | union (users_tool_invoke)
    | distinct DevDeviceId,ExtensionVersion, user_source,type = "Copilot request for migration plan";
let users_build = materialize(cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').build_result_records_helper(start,end));
let users_build_invoke =
    users_build
    | distinct DevDeviceId,ExtensionVersion, user_source,type = "Buildfix start";
let users_build_success =
    users_build
    | where success
    | distinct DevDeviceId,ExtensionVersion, user_source,type = "Buildfix success";
union users_migration,users_copilot_request,users_tool_invoke, users_build_invoke,users_build_success,users_migration_java
```

5) Classical Java Migration Funnel (narrow cohort aligned to plan/validation path)
- Description: Focuses strictly on Java migration using classical flow: kickoff, plan/request, tool invocations, and build success; excludes non-classical paths. Inner join to ensure users belong to kickoff cohort.
```kusto
//As of last 28 days. This funnel focuses on Java users using classical migration scenarios, which involves using a migration plan and ideally going through validation. Users who use migrate-by-prompt, containerization, or only perform validation may not follow this classical flow and are therefore excluded from this funnel analysis.
let start = startofday(ago(28d));
let end = startofday(now()));
let users_migration = 
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').narrow_migration_records_helper_Java(start, end)
    | project  DevDeviceId,VSCodeSessionId,ExtensionVersion, user_source,type = "Kick off Migration with Java";
let users_tool_invoke = 
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ExtensionName has "migrate-java-to-azure" and EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool in ('createMigrationPlan','appmod-run-task')
        | project ServerTimestamp, DevDeviceId,Properties,ExtensionVersion,VSCodeSessionId
        | union (
            cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
            | where timestamp  between (start .. (end - 1s))
            | where operation_Name == "java/migrateassistant/tool/invoke"
            | extend invokedToolId = tostring(customDimensions["invokedtoolid"])
            | where invokedToolId has 'appmod-run-task'
            | extend DevDeviceId = tostring(customDimensions.devdeviceid)
            | extend ExtensionVersion = tostring(customDimensions.callerversion), VSCodeSessionId = tostring(customDimensions.callersessionid)
        )
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
        | mv-expand type = dynamic(["Tool invoked for Java", "Copilot request for migration plan for Java"]) to typeof(string)
        | project DevDeviceId,ExtensionVersion,VSCodeSessionId, user_source,type;
let users_copilot_request =
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. end)
    | where ExtensionName == 'GitHub.copilot-chat' and EventName == "github.copilot-chat/panel.request"
    | project ServerTimestamp,EventName,VSCodeSessionId, requestId = tostring(Properties.requestid), conversationId = tostring(Properties.conversationid), DevDeviceId,Properties,toolcounts = tostring(Properties.toolcounts), Measures
    | project DevDeviceId, toolcounts,requestId, ServerTimestamp, Properties,VSCodeSessionId
    | where toolcounts has 'appmod-run-task' or toolcounts has 'createMigrationPlan'
    | join kind=leftouter (
        users_migration 
        | distinct VSCodeSessionId, ExtensionVersion
    ) on VSCodeSessionId
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
    | project DevDeviceId,ExtensionVersion,VSCodeSessionId, user_source,type="Copilot request for migration plan for Java";
let users_build = 
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').build_result_records_with_appid_helper(start,end) 
    | project DevDeviceId,ExtensionVersion,VSCodeSessionId, user_source,success;
let users_build_invoke = 
    users_build
    | project DevDeviceId, ExtensionVersion, VSCodeSessionId, user_source, type = "Buildfix start";
let users_build_success = 
    users_build
    | where success
    | project DevDeviceId, ExtensionVersion, VSCodeSessionId, user_source, type = "Buildfix success";
union users_migration,users_copilot_request,users_tool_invoke, users_build_invoke, users_build_success
| join kind=inner (users_migration | project VSCodeSessionId) on VSCodeSessionId
```

6) AppCAT Union Pattern (Copilot CLI + VSCodeExt UI)
- Description: Merges AppCAT scan events from Copilot CLI traces and VSCodeExt UI events, normalizes time and keys, filters acceptable outcomes, and enriches with internal/external. Adapt version and error rules as needed.
```kusto
let start = startofday(ago(28d));
let end = startofday(now()));

let users_assessment = cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').assessment_run_records_helper(start, end)
    | distinct VSCodeSessionId, ExtensionVersion;

let appcat_cli =
    cluster('https://ddtelai.kusto.windows.net/').database('Copilot').RawEventsTraces
    | where timestamp between (start .. end)
    | where operation_Name == 'java/appcat/command'
    | extend data = parse_json(message)
    | extend command = tostring(data.message)
    | where command == 'analyze'
    | extend dimensions = parse_json(customDimensions)
    | extend appcatVersion = tostring(dimensions.appcatversion), status = tostring(dimensions.status), callerid = tostring(dimensions.callerid)
    | where appcatVersion !in ('latest', 'experimental')
    | where status == 'start'
    | where callerid has "migrate-java-to-azure"
    | project ServerTimestamp = timestamp, DevDeviceId = tostring(dimensions.devdeviceid), VSCodeSessionId = operation_ParentId, ExtensionVersion = tostring(dimensions.callerversion);

let appcat_ui =
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. end)
    | where EventName == 'vscjava.migrate-java-to-azure/java/migrateassistant/appcat/scan'
    | where (Properties.result == 'success' or Properties.error !has "with exit code: 199" and Properties.error matches regex @"with exit code: \d+")
    | project DevDeviceId, VSCodeSessionId, ServerTimestamp, ExtensionVersion;

appcat_cli
| join kind=leftouter users_assessment on VSCodeSessionId
| union appcat_ui
| join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
| extend user_source = iff(IsInternal == 1, 'internal', 'external')
| distinct DevDeviceId, ExtensionVersion, user_source, type = "AppCAT ran"
```

7) Copilot Request Linked to Migration Cohort
- Description: Finds Copilot chat panel requests associated with migration cohort devices/sessions, filters to plan-related tools, enriches internal/external labels, and deduplicates. Adjust tool IDs or extension names as needed.
```kusto
let start = startofday(ago(28d));
let end = startofday(now()));

let users_migration =
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').migration_records_helper(start, end)
    | distinct DevDeviceId, VSCodeSessionId, ExtensionVersion;

cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
| where ServerTimestamp between (start .. end)
| where ExtensionName == 'GitHub.copilot-chat'
| where EventName == "github.copilot-chat/panel.request"
| where VSCodeSessionId in (users_migration | distinct VSCodeSessionId) or DevDeviceId in (users_migration | distinct DevDeviceId) 
| project ServerTimestamp, EventName, VSCodeSessionId, requestId = tostring(Properties.requestid), conversationId = tostring(Properties.conversationid), DevDeviceId, Properties, toolcounts = tostring(Properties.toolcounts)
| where toolcounts has 'appmod-run-task' or toolcounts has 'createMigrationPlan'
| join kind=leftouter (users_migration | distinct VSCodeSessionId, ExtensionVersion) on VSCodeSessionId
| join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
| extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
| distinct DevDeviceId, ExtensionVersion, user_source, type = "Copilot request for migration plan"
```

8) Build Result Cohort and Success
- Description: Uses curated build result helpers to mark start and success; groups by device/version. This is reusable for both general and classical funnels.
```kusto
let start = startofday(ago(28d));
let end = startofday(now()));

// Curated build records (bi)
let users_build = materialize(
    cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').build_result_records_helper(start,end)
);

let users_build_invoke =
    users_build
    | distinct DevDeviceId, ExtensionVersion, user_source, type = "Buildfix start";

let users_build_success =
    users_build
    | where success
    | distinct DevDeviceId, ExtensionVersion, user_source, type = "Buildfix success";

union users_build_invoke, users_build_success
```

## Reasoning Notes (only if uncertain)
- Canonical time column choice:
  - Observed both ServerTimestamp and timestamp; we adopt ServerTimestamp and alias others because most VSCodeExt queries use ServerTimestamp and Copilot traces are explicitly projected to ServerTimestamp.
- Primary cluster/database:
  - Helpers from ama4j/bi are central to cohort formation across all funnels; VSCodeExt and Copilot are alternates for event enrichment. We adopt ama4j.westus2/bi as primary.
- Internal/external flag naming:
  - Queries use IsInternal, IsInternal1, and tobool(IsInternal). We assume schema variations or join collisions; in practice, prefer explicit project-rename to reconcile.
- Effective end time:
  - Some sources use (end - 1s); others use (start .. end) with end at start of current day. We recommend excluding current day to avoid partial ingestion.
- Java upgrade version gating:
  - Requires major/minor thresholds and excludes "SNAPSHOT" builds; we keep these as-is from queries.
- AppCAT version and error handling:
  - Excluding ('latest','experimental') appcatVersion and treating certain errors as acceptable; we retain these filters to match intent.
- Cohort restriction strategy:
  - Inner joins on base cohort (e.g., users_migration, users_assessment) to ensure funnel correctness; leftouter joins for enrichment. This aligns with funnel definitions in the queries.
- Copilot linkage:
  - Copilot requests are tied to migration cohort via session or device membership; we keep both conditions to reduce false negatives.

- Acceptance Checklist
  - Identified timestamp columns, typical window, and UTC default; bin() usage not present.
  - Documented effective end time strategy; current day excluded where needed.
  - Produced entity model with keys and counting do/don’t (event facts vs curated helpers).
  - Called out cross-cluster union and normalization patterns.
  - Included default exclusion patterns via version gates, status filters, and appcatVersion exclusions.
  - Provided ID parsing/derivation snippets from customDimensions and Properties.
  - Example queries are copy-paste-ready with clear intent and adaptation guidance.
  - No fabricated fields/values; placeholders used only where implied by uncertainty.

- Access and Schema Caveats (from Canonical Tables source)
  - Schema retrieval failed for all referenced tables via get_table_schema due to network/auth errors. Before production use, re-run schema discovery in your environment and validate:
    - Exact column names and types for DevDeviceId, VSCodeSessionId, IsInternal.
    - Presence of dynamic bags (Properties, Measures, customDimensions) and expected keys for your timeframe.
  - Timezone is unknown; the queries assume startofday boundaries consistent with the cluster’s default timezone. If your analysis is sensitive to timezone, explicitly convert timestamps.

## Canonical Tables

Below are the canonical tables referenced by the dashboard’s queries. All tables are cross-cluster sources; use explicit cluster().database() prefixes in Kusto to avoid ambiguity.

Note: Attempts to fetch exact schemas via the adx-mcp-server get_table_schema tool failed due to network/auth issues. Column lists below are inferred from query usage and may be incomplete. Treat dynamic bags (Properties, Measures, customDimensions) as variable key/value stores that can evolve.

### Table name: cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
- Priority: Normal
- What this table represents: Event telemetry emitted by VS Code extensions on the client side. Each row is an event (fact) with a timestamp and a set of dynamic properties. Zero rows in a time window imply no client-side activity recorded for the filters used.
- Freshness expectations: Unknown. Queries consistently use a rolling 28-day window and startofday boundaries. Be cautious with current-day data; prefer complete days to avoid partial ingestion.
- When to use / When to avoid:
  - Use for client-side workflows (Java Upgrade, migration assistant invocations, Copilot panel requests) where EventName and Properties capture user actions.
  - Use to derive funnel steps based on specific EventName patterns (e.g., vscjava.vscode-java-upgrade/*).
  - Use to correlate with user identity via DevDeviceId and session scope via VSCodeSessionId.
  - Avoid using it to analyze service-side execution or appcat CLI runs; use Copilot RawEventsTraces for service-side traces.
  - Avoid relying on properties keys that are not validated in your time window (dynamic keys may be missing or renamed).
- Similar tables & how to choose:
  - cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces: service-side trace logs. Choose VSCodeExt for client extension telemetry; use RawEventsTraces for backend/service instrumentation. Union both when needing holistic coverage of a workflow spanning client and service.
- Common Filters:
  - Time: ServerTimestamp between (start .. end) where start = startofday(ago(28d)), end = startofday(now()).
  - ExtensionName filters: "vscjava.vscode-java-upgrade", "GitHub.copilot-chat", and strings containing "migrate-java-to-azure".
  - EventName patterns: "java/migrateassistant/tool/invoke", upgrade workflow steps like generate/confirm plan, remediation/build/test/summary stages.
  - ExtensionVersion: exclude SNAPSHOT builds; split major/minor to gate behavior (>= 1.2).
  - Properties keys checked: sessionid, hashedappid, modelid, targetdeps, invokedtoolid, toolcounts, requestid, conversationid, result, error.
- Table columns:
   Schema retrieval via get_table_schema failed; inferred columns from query usage:
   | Column           | Type     | Description or meaning |
   |------------------|----------|------------------------|
   | ServerTimestamp  | datetime | Event timestamp (client-side). Used as the primary time filter. |
   | ExtensionName    | string   | Extension identifier (e.g., "vscjava.vscode-java-upgrade", "GitHub.copilot-chat"). |
   | ExtensionVersion | string   | Extension version; used to compute major/minor and exclude SNAPSHOT builds. |
   | EventName        | string   | Event route/name; used to distinguish workflow steps (e.g., ".../tool/invoke"). |
   | DevDeviceId      | string   | Device-level hashed identifier; used for dcount and internal/external classification joins. |
   | VSCodeSessionId  | string   | Session identifier; used to scope funnels per session. |
   | Properties       | dynamic  | Dynamic bag of event properties; keys used include sessionid, hashedappid, modelid, targetdeps, invokedtoolid, toolcounts, requestid, conversationid, result, error. |
   | Measures         | dynamic  | Dynamic bag of numeric measures; used for CVE and behavior validations (e.g., cve.high, numofbehaviorchangestofix). |
- Column Explain:
  - ServerTimestamp: The primary time dimension; always filter on it with precise boundaries to avoid partial-day noise.
  - EventName: Drives stage detection via iff checks; ensure exact matches for start/end events in upgrade workflows.
  - ExtensionVersion: Split to major/minor to branch workflow logic; exclude SNAPSHOT to focus on marketplace builds.
  - Properties.invokedtoolid and Properties.toolcounts: Determine migration tool usage ("createMigrationPlan", "appmod-run-task").
  - DevDeviceId and VSCodeSessionId: Use for distinct counts (Devices, Sessions) and to join to internal/external classification.
  - Measures: Evaluate outcomes (e.g., CVE passed/failed) based on presence or numeric values.

### Table name: cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal
- Priority: Normal
- What this table represents: Snapshot/fact that flags whether a device is internal or external. Zero rows for a device imply no classification known; treat as external unless explicitly flagged.
- Freshness expectations: Unknown; behaves like a reference lookup. Joins in queries assume stable classification over the 28-day window.
- When to use / When to avoid:
  - Use to segment funnels into internal vs external cohorts via join on DevDeviceId.
  - Use for attribution and to filter out internal traffic when measuring external adoption.
  - Avoid using it as a time series; it’s a lookup, not an event stream.
- Similar tables & how to choose:
  - None observed in the provided content. If multiple internal flags exist (e.g., IsInternal vs IsInternal1), prefer the one present for your join path and validate with sampling.
- Common Filters:
  - Joins: join kind=leftouter ... on DevDeviceId; derive user_source = iff(tobool(IsInternal) or IsInternal == 1, 'internal', 'external').
- Table columns:
   Schema retrieval via get_table_schema failed; inferred columns from query usage:
   | Column       | Type     | Description or meaning |
   |--------------|----------|------------------------|
   | DevDeviceId  | string   | Device identifier used to join from event tables. |
   | IsInternal   | bool/int | Internal flag; seen as 1 or true in queries to mark internal. |
   | IsInternal1  | bool/int | Alternate/internal flag variant observed in some queries; use cautiously and validate which column exists. |
- Column Explain:
  - DevDeviceId: Required to join from RawEventsVSCodeExt and RawEventsTraces.
  - IsInternal / IsInternal1: Convert to bool/int consistently; use iff(tobool(IsInternal), 'internal', 'external') or check == 1.

### Table name: cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
- Priority: Normal
- What this table represents: Service-side tracing telemetry. Each row is a trace with operation name, timestamps, and dynamic custom dimensions. Zero rows imply no service instrumentation observed for the filters used.
- Freshness expectations: Unknown. Queries use last 28 days and startofday boundaries. Service traces may be near-real-time but validate your window for completeness.
- When to use / When to avoid:
  - Use for appcat CLI flows ("java/appcat/command" with command == "analyze") and service-driven tool invocations ("java/migrateassistant/tool/invoke").
  - Use to supplement client-side events when tracing needs backend context (operation_Name, customDimensions, operation_ParentId).
  - Avoid using it to infer client-only events without corresponding backend operations (may not capture purely local actions).
- Similar tables & how to choose:
  - VSCodeExt.RawEventsVSCodeExt: client-side events. Choose RawEventsTraces for backend/service coverage; union both to reduce blind spots (note potential double counting).
- Common Filters:
  - Time: timestamp between (start .. end); sometimes truncated at (end - 1s) to avoid boundary effects.
  - operation_Name: "java/appcat/command" and "java/migrateassistant/tool/invoke".
  - customDimensions filters:
    - appcatversion not in ("latest", "experimental")
    - status == "start"
    - callerid has "migrate-java-to-azure"
    - invokedtoolid has "appmod-run-task"
    - DevDeviceId = tostring(customDimensions.devdeviceid)
    - callerversion and callersessionid used for correlation
  - Join keys: operation_ParentId mapped to VSCodeSessionId for cross-correlation with client events.
- Table columns:
   Schema retrieval via get_table_schema failed; inferred columns from query usage:
   | Column             | Type     | Description or meaning |
   |--------------------|----------|------------------------|
   | timestamp          | datetime | Trace event timestamp. Primary time filter. |
   | operation_Name     | string   | Operation route/name (e.g., "java/migrateassistant/tool/invoke", "java/appcat/command"). |
   | operation_ParentId | string   | Parent operation id; used as VSCodeSessionId for joins. |
   | message            | string   | Raw message payload; parsed to extract command for appcat ("analyze"). |
   | customDimensions   | dynamic  | Dynamic bag; keys include appcatversion, status, callerid, devdeviceid, callerversion, callersessionid, invokedtoolid. |
- Column Explain:
  - timestamp: Always filter with a bounded range.
  - operation_Name: Core discriminator for which flow the trace belongs to.
  - customDimensions.appcatversion and status: Gate valid runs (exclude "latest"/"experimental"; require status == "start").
  - customDimensions.invokedtoolid: Detect "appmod-run-task" tool invocations.
  - operation_ParentId: Cross-correlate with client session when needed.
