# Application Modernization for Java and .NET - Product and Data Overview Template

## 1. Product Overview

Application Modernization for Java and .NET provides tools and telemetry to help developers assess, plan, and execute modernization or migration activities for Java and .NET projects. This schema enables PMAgent to interpret the product’s cross-source telemetry (VSCode extension, VS platform, and MCP/Copilot service) and the product’s pre-aggregated BI/Consolidation layers to answer product questions, build summaries, and generate queries reliably.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
  Application Modernization for Java and .NET
- Product Nick Names: 
  **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- Kusto Cluster:
  appmod.westus2.kusto.windows.net
- Kusto Database:
  Consolidation
- Access Control:
  **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Application Modernization for Java and .NET - Kusto Query Playbook

## Overview
- Product: Application Modernization for Java and .NET
- Summary: The dashboard of Application Modernization is the top level metrics for the product built on aggregated telemetries. The aggregated telemetries come from raw telemetries by pre-defined Kusto functions.
- Primary cluster and database:
  - Cluster: appmod.westus2.kusto.windows.net
  - Database: Consolidation
- Alternate data sources frequently referenced:
  - ddtelai.kusto.windows.net / Copilot
  - ddtelvscode.kusto.windows.net / VSCodeExt, VSCode, VsCodeInsights
  - ddtelvsraw.kusto.windows.net / VS
  - ddtelinsights.kusto.windows.net / DDTelInsights
  - ama4j.westus2.kusto.windows.net / bi, consolidation

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - timestamp (Copilot.RawEventsTraces)
  - ServerTimestamp (VSCodeExt.RawEventsVSCodeExt)
  - ServerUploadTimestamp (VSCode.RawEventsVSCode)
  - Date (pre-aggregations and rolling aggregations, e.g., bi tables and Consolidation views)
- Canonical Time Column: Date
  - For event tables, normalize to Date via daily bins:
    - From timestamp: project Date = bin(timestamp, 1d)
    - From ServerTimestamp: project Date = bin(ServerTimestamp, 1d)
    - From ServerUploadTimestamp: project Date = bin(ServerUploadTimestamp, 1d)
  - For pre-aggregated tables that already have Date, use it as-is.
- Typical windows and resolutions:
  - 28-day rolling window is standard (ago(28d) or startofday(ago(28d))).
  - Daily binning (bin(..., 1d)) is ubiquitous.
- Timezone:
  - Not specified; assume UTC.
- Effective end time:
  - Many queries use startofday(now()) as the exclusive end to avoid incomplete current-day data.

### Freshness & Completeness Gates
- Ingestion cadence and shard completeness are unknown.
- Conservative default patterns:
  - Use let end = startofday(now()); and restrict to Date >= startofday(ago(28d)).
  - When rolling up multi-source facts, prefer last fully ingested day by excluding the current day.
- Multi-slice completeness gate (recommended pattern):
  - Find the latest day where all key slices (e.g., required sources/clusters) have non-zero counts, then set effective_end to that day. Use arg_max() on per-slice heartbeat/count signals to select the last complete day.

### Joins & Alignment
- Frequent keys:
  - DevDeviceId (developer device identifier)
  - user_source (derived: internal/external)
  - AppId (aka hashedappid; module id)
  - projectId (aka hashed_project_id)
  - VSCodeSessionId (session boundary)
  - correlationId (operation correlation)
  - operation_Id (Copilot operation linkage)
  - requestId, conversationId (Copilot Chat event linkage)
- Typical join kinds:
  - leftouter when enriching events (e.g., join to fact_user_isinternal).
  - inner to ensure presence of paired records (e.g., project_size joins on operation_Id).
- Post-join hygiene:
  - Use project-away to drop duplicate columns (e.g., DevDeviceId1).
  - Use coalesce() to handle missing counters (e.g., BuildPassedCount = coalesce(BuildPassedCount, 0)).

### Filters & Idioms
- Product and extension filters:
  - ExtensionName has "migrate-java-to-azure"
  - EventName !has 'migrate-java-to-azure/info' to exclude activation-only events
  - EventName has 'java/migrateassistant/...’ for scoped operations
  - Properties.id == 'vscjava.migrate-java-to-azure'
  - Properties.reason exclusions: !in ('onStartupFinished'), !has 'pom.xml', !has 'onLanguage:java'
- Operation filters (Copilot side):
  - operation_Name startswith 'java/migrateassistant'
  - Specific tools: invokedtoolid == 'createMigrationPlan' or has 'appmod-run-task'
  - Build/test/CVE outputs: operation_Name == "java/migrateassistant/buildFix/output", "testFix/output", "cveFix/output"
- CLI vs VSCode disambiguation:
  - callerId == 'appcat' → AppCAT CLI
  - callerId has "vscjava.migrate-java-to-azure" → VSCode extension
- Version filter:
  - appcatVersion != 'latest' used to exclude legacy or unintended events.
- Migration vs upgrade:
  - migrateaction == 'migrate' and migrateby != "upgrade"
- Internal/external derivation:
  - VSCode: join VsCodeInsights.fact_user_isinternal by DevDeviceId then iff(tobool(IsInternal), 'internal', 'external')
  - Copilot: derive from tobool(customDimensions.internal) or parsed message.

### Cross-cluster/DB & Sharding
- Qualification:
  - Use cluster('<cluster>').database('<db>').<table or function> for each source.
- Union normalization:
  - Pattern: union same logical signals across clusters (Copilot + VSCodeExt + VSCode), normalize keys and time, then summarize.
  - Order matters: union → normalize columns (keys, user_source, Date) → dedup (if needed) → summarize.

### Table classes
- Fact (events):
  - Copilot.RawEventsTraces (ddtelai/Copilot)
  - VSCodeExt.RawEventsVSCodeExt (ddtelvscode/VSCodeExt)
  - VSCode.RawEventsVSCode (ddtelvscode/VSCode)
- Snapshot/enrichment:
  - VsCodeInsights.fact_user_isinternal (ddtelvscode/VsCodeInsights)
- Pre-aggregated:
  - bi tables: mau_total, unique_app_count_28d_* , users_count_28d_* , sessions_count_28d_* (ama4j/bi)
  - consolidation tables: users_code_remediation_consolidated_java_upgrade_java_migrate, sessions_code_remediation_consolidated_java_upgrade_java_migrate (ama4j/consolidation)
- Rolling aggregation function layer (Consolidation):
  - Get28DayRollingAggregation over RollingAggregation; supplies per-day counts for specific Name metrics, with Language and ModernizationType filters.

### Important Mapping
- Tiles/pages to sources:
  - "java_migrate_mau_total" → ama4j/bi/mau_total
  - "java_migrate_meu_total" → appmod/Consolidation.Get28DayRollingAggregation('Users_MEU')
  - "java_migrate_unique_app_28d_total" → ama4j/bi/unique_app_count_28d_total
  - "java_migrate_unique_app_28d_assessed" → ama4j/bi/unique_app_count_28d_assessed
  - "java_migrate_unique_app_28d_migration" → ama4j/bi/unique_app_count_28d_migration
  - "java_migrate_unique_app_28d_assessreport" → ama4j/bi/unique_app_count_28d_assessreport
  - "java_migrate_users_count_28d_assess" → ama4j/bi/users_count_28d_assess
  - "java_migrate_users_count_28d_assessreport" → ama4j/bi/users_count_28d_assessreport
  - "java_migrate_users_count_28d_migrationplan" → ama4j/bi/users_count_28d_migrationplan
  - "java_migrate_users_count_28d_buildfix" → ama4j/bi/users_count_28d_buildfix
  - "java_migrate_sessions_count_28d_assess" → ama4j/bi/sessions_count_28d_assess
  - "java_migrate_sessions_count_28d_codeRemediation" → ama4j/bi/sessions_count_28d_codeRemediation
  - "java_migrate_sessions_count_28d_buildfix" → ama4j/bi/sessions_count_28d_buildfix
  - "java_migrate_sessions_count_28d_assessreport" → ama4j/bi/sessions_count_28d_assessreport
  - "java_consolidated_mau_total" → appmod/Consolidation.Get28DayRollingAggregation('Java','migrate/upgrade','Users_MAU')
  - "java_consolidated_meu_total" → appmod/Consolidation.Get28DayRollingAggregation('Java','migrate/upgrade','Users_MEU')
  - "java_consolidated_users_count_28d_buildfix" → appmod/Consolidation.Get28DayRollingAggregation('Java','migrate/upgrade','Apps_BuildStarted')
  - "java_consolidated_users_count_28d_coderemediation" → ama4j/consolidation/users_code_remediation_consolidated_java_upgrade_java_migrate
  - "java_consolidated_sessions_count_28d_coderemediation" → ama4j/consolidation/sessions_code_remediation_consolidated_java_upgrade_java_migrate
  - ".NET tiles" map to multiple Consolidation.Get28DayRollingAggregation names (Apps_* and Users_*) with language="C#", modernizationType="migrate"
  - Adoption tiles:
    - "java_migrate_users_count_28d_adoption" → ama4j/bi/users_count_28d_adoption
    - "java_consolidated_users_count_28d_adoption" → appmod/Consolidation.Get28DayRollingAggregation('Java','migrate/upgrade','Users_Adoption')
  - Module/project tiles:
    - "java_migrate_avg_users_per_module" → ama4j/bi/avg_users_per_app_helper
    - "java_migrate_project_size_on_project" → ama4j/bi/project_size_new_helper
    - "java_migrate_project_size_on_session" → ama4j/bi/project_size_helper
    - "java_migrate_module_per_project" → ama4j/bi/modules_per_project_helper
    - "java_consolidated_module_per_project" → ama4j/bi/modules_per_project_helper union ama4j/consolidation/modules_per_project_java_upgrade_helper
    - "java_consolidated_project_size_on_project" → ama4j/bi/project_size_new_helper

### Choosing Between Similar Tables
- Raw events by source:
  - Use RawEventsVSCodeExt for VSCode extension activity (“migrate-java-to-azure”).
  - Use RawEventsVSCode for VSCode platform activation events.
  - Use RawEventsTraces for MCP/Copilot-side events (java/migrateassistant/*, java/appcat/*).
  - Use RawEventsVSBlessed for Visual Studio (non-VSCode) events with Product == "appmod".
- Aggregate trend vs detail:
  - Use bi/consolidation tables for daily 28d trend metrics; they’re fast and stable.
  - Use raw/event helper views for detailed correlation (e.g., correlationId, session-level outcomes).

### Common Filtering Patterns
- Time windows:
  - Raw streams: timestamp or ServerTimestamp between (start .. (end - 1s)).
  - Aggregates: Date >= startofday(ago(28d)).
- Identity and segmentation:
  - Join fact_user_isinternal on DevDeviceId to compute user_source.
  - For MCP, user_source may come from customDimensions.internal or message.internal.
- Scenario discriminators:
  - operation_Name (MCP): java/appcat/project, .../report, .../buildFix/output/build, .../testFix/output/test, .../cveFix/output, .../tool/invoke/task/run
  - VSCode extension: EventName and Properties.command/invokedtoolid
  - Activation (VSCode): EventName == "monacoworkbench/activateplugin", Properties.id/reason

### Freshness Notes and Cautions
- Raw event tables (VSCodeExt/VSCode/Copilot) are typically near-real-time; exact ingestion latency unknown.
- Aggregation tables under bi/consolidation are expected to refresh daily; do not assume current-day completeness.

If you need exact schemas for the bi/consolidation/VS/Insights clusters listed above, request access and rerun get_table_schema to validate column names and types.

## Entity & Counting Rules (Core Definitions)
- Entity model:
  - Developer (DevDeviceId) → Module/App (AppId/hashedappid) → Project (projectId/hashed_project_id).
  - Session alignment via VSCodeSessionId; operation linkage via correlationId and operation_Id.
- Standard groupings:
  - By Date and user_source for most KPI time series.
  - By AppId for unique app/module counts; by projectId for module-per-project analysis.
- Business definitions observed:
  - MAU: distinct DevDeviceId per day from VSCode extension activation and MCP telemetry.
  - MEU: DevDeviceId engaging on ≥2 distinct days in the window (summarize dcount(Date) per DevDeviceId; threshold ≥ 2).
  - Adoption users: union of users with key success signals (assessment report generated, build fix succeeded, code proposal accepted or partially accepted, unit tests passed, CVE fix passed, consistency check passed).
  - Build/Test/CVE success rates: ratio of passed over started events for specific metrics names within RollingAggregation.
- Counting Do/Don’t:
  - Do normalize to Date bins before distinct counts.
  - Do union CLI + VSCode + MCP and dedup (by correlationId or request/session keys).
  - Don’t count activation-only events when measuring engagement (exclude .../info).
  - Don’t mix upgrade and migration for migration-specific KPIs (filter migrateby != "upgrade").

## Views (Reusable Layers)

- Get28DayRollingAggregation
  - Purpose: Reusable layer over RollingAggregation to fetch 28-day rolling counts for a named metric, filtered by language and modernization type; returns per-day counts per user source.
  - Query:
```kusto
Get28DayRollingAggregation(language:string, modernizationType:string, name:string)
{
RollingAggregation
| where Language == language and ModernizationType == modernizationType and Name == name and LookBackWindow == "28d"
| summarize arg_max(DataIngestTimestamp, Count) by UserSource, startofday(Date)
| project Date, UserSource, Count;
}
```

- avg_users_per_app_helper
  - Purpose: Compute average and max developers per unique AppId across VSCode and CLI sources.
  - Query:
```kusto
avg_users_per_app_helper(start:datetime, end:datetime)
{
    union unique_app_vscode_records_helper(start,end), unique_app_cli_records_helper(start,end)
    | summarize DistinctDevelopers = dcount(DevDeviceId) by AppId
    | summarize AvgDevelopersPerApp = avg(DistinctDevelopers), MaxDevelopersPerApp = max(DistinctDevelopers)
}
```

- project_size_new_helper
  - Purpose: Derive project size category for distinct project_id using AppCAT project events and link to hashed project id via operation_Id.
  - Query:
```kusto
project_size_new_helper(start:datetime, end:datetime)
{
    cluster('ddtelai').database('Copilot').RawEventsTraces
    | where timestamp between (start .. end)
    | where operation_Name == 'java/appcat/project'
    | extend val = tolong(customDimensions.project_scale)
    | extend callerId = tostring(customDimensions.callerid)
    | where callerId has "vscjava.migrate-java-to-azure" or callerId == "appcat"
    | where isnotempty( val)
    | project val, operation_Id
    | join kind=inner  (
        cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. end)
        | where operation_Name == 'java/appcat/project'
        | extend val = tolong(customDimensions.project_scale),  project_id = tostring(customDimensions.hashed_project_id)
        | where isnotempty( project_id)
        | project project_id,operation_Id,val, timestamp
    ) on operation_Id
    | project-away operation_Id1
    | extend ProjectSize = case (
            val > 100000,
            "Extra Large (>100K lines)",
            val > 15000 and val <= 100000,
            "Large (15K-100K lines)",
            val > 5000 and val <= 15000,
            "Medium (5K-15K lines)",
            val > 200 and val <= 5000,
            "Small (200-5K lines)",
            val <=200,
            "Tiny (<=200 lines)",
            "unknown"
        )
    | distinct ProjectSize, project_id
}
```

- project_size_helper
  - Purpose: Summarize project counts by size buckets from AppCAT project telemetry.
  - Query:
```kusto
project_size_helper(start:datetime, end:datetime)
{
    cluster('ddtelai').database('Copilot').RawEventsTraces
    | where timestamp between (start .. end)
    | where operation_Name == 'java/appcat/project'
    | extend dimensions = parse_json(customDimensions)
    | extend val = tolong(dimensions.project_scale)
    | where isnotempty( val)
    | extend ProjectSize = case (
        val > 100000,
        "Extra Large (>100K lines)",
        val > 15000 and val <= 100000,
        "Large (15K-100K lines)",
        val > 5000 and val <= 15000,
        "Medium (5K-15K lines)",
        val > 200 and val <= 5000,
        "Small (200-5K lines)",
        val <=200,
        "Tiny (<=200 lines)",
        "unknown"
    )
    | summarize ["Project count"]=count() by ProjectSize
}
```

- modules_per_project_helper
  - Purpose: Compute module count per project by unifying Copilot and VSCode event sources; outputs per user_source and a total rollup.
  - Query:
```kusto
modules_per_project_helper(start:datetime, end:datetime)
{
    let modulesInfo = materialize (
        cluster('https://ddtelai.kusto.windows.net/').database('Copilot').table('RawEventsTraces') 
        | where operation_Name has "java/migrateassistant" or operation_Name has "java/appcat"
        | where timestamp between (start .. end)
        | extend projectId = tostring(customDimensions.hashedprojectid), moduleId = tostring(customDimensions.hashedappid)
        | where isnotempty(projectId) and isnotempty(moduleId)
        | project DevDeviceId = tostring(customDimensions.devdeviceid), moduleId,projectId
        | union (
            cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
            | where ServerTimestamp between (start .. (end - 1s))
            | where ServerTimestamp >= datetime(2025-08-10)
            | where ExtensionName has "migrate-java-to-azure"
            | where EventName has "java/migrateassistant/projectsize"
            | extend projectId = tostring(Properties.hashedprojectid), moduleId = tostring(Properties.hashedappid), correlationId = tostring(Properties['correlationid'])
            | where isnotempty(projectId) and isnotempty(moduleId)
            | project DevDeviceId, moduleId,projectId
        )
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | project-away  DevDeviceId1
    );
    modulesInfo    
    | summarize  ModuleCount = dcount(moduleId) by projectId,user_source
    | union (
        modulesInfo
        | summarize  ModuleCount = dcount(moduleId) by projectId
        | extend user_source = "total"
    )
}
```

- adoption_user_helper
  - Purpose: Union of success signals to identify adoption users within a window.
  - Query:
```kusto
adoption_user_helper(start:datetime, end:datetime)
{
    // assessment report generated
    let assessmentReportUsers = assessment_success_occurrence_cli_vscode_helper(start,end);
    // build fix succussed
    let buildfixSuccessUsers = buildfix_output_records_helper(start,end) | where success;
    // code proposal not rejected: we can only find the conversation whose code proposal not rejected
    let codeAcceptUsers = code_accept_records_helper(start, end) | where outcome != 'rejected';
    // UT passed
    let utPassedUsers = utfix_records_helper(start,end) | where success;
    // cve check passed
    let cvefixPassedUsers = cvefix_records_helper(start,end) | where success;
    //consistency check passed
    let consistencyPassedUsers = consistencycheck_records_helper(start,end) | where success;
    union assessmentReportUsers, buildfixSuccessUsers,codeAcceptUsers,utPassedUsers,cvefixPassedUsers,consistencyPassedUsers
    | project DevDeviceId,user_source
}
```

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Use a 28-day window with an effective end at the start of today to avoid current-day incompleteness. Normalize events to daily Date bins.
  - Snippet:
```kusto
// 28-day window with safe effective end
let start = startofday(ago(28d));
let end = startofday(now());

// Normalize to canonical Date
source
| where TimestampColumn between (start .. (end - 1s))
| project Date = bin(TimestampColumn, 1d), ...
```

- Join template: derive internal/external and align keys
  - Description: Enrich events with internal/external labels and align by session/correlation keys when needed.
  - Snippet:
```kusto
// Enrich with internal/external
events
| join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
| extend user_source = iff(tobool(IsInternal) /* or IsInternal1 */, 'internal', 'external')
| project-away IsInternal, IsInternal1

// Align two event streams on session or operation keys
left
| join kind=leftouter right on VSCodeSessionId // or on correlationId / operation_Id
| project-away VSCodeSessionId1, correlationId1, operation_Id1
```

- De-dup patterns
  - Description: Avoid double counting by collapsing on correlationId or by excluding sessions already represented; select final events via arg_max.
  - Snippets:
```kusto
// Collapse events by correlationId to the latest
events
| where isnotempty(correlationId)
| summarize arg_max(timestamp, *) by correlationId
| union (events | where isempty(correlationId))

// Exclude sessions from secondary streams when primary exists
let primary = ... | distinct VSCodeSessionId;
secondary
| where VSCodeSessionId !in (primary)
```

- Important filters
  - Description: Standardized exclusions and scoping filters for this product.
  - Snippets:
```kusto
// VSCode extension scope
| where ExtensionName has "migrate-java-to-azure"
| where EventName !has 'migrate-java-to-azure/info'

// Copilot tools scope
| where operation_Name startswith 'java/migrateassistant'

// CLI vs VSCode disambiguation
| extend callerId = tostring(customDimensions.callerid)
| where callerId == 'appcat' or callerId has "vscjava.migrate-java-to-azure"

// Exclude upgrade-only flows for migration KPIs
| extend migrateby = tostring(Properties.migrateby)
| where migrateby != "upgrade"

// Exclude unintended legacy version
| extend appcatVersion = tostring(dimensions.appcatversion) // or customDimensions.appcatversion
| where appcatVersion != 'latest'
```

- Important Definitions
  - Description: Derived from queries in this corpus; adopt these when measuring KPIs.
  - Snippets:
```kusto
// MEU: engaged on 2+ distinct days
per_user_days
| summarize dcount(Date) by DevDeviceId, user_source
| where dcount_Date >= 2

// MAU: distinct users per day from engagement events (exclude activation-only)
engagement_events
| project DevDeviceId, Date = bin(Timestamp, 1d), user_source
| distinct DevDeviceId, Date, user_source

// Build success rate (28-day rolling)
let started = Get28DayRollingAggregation(language='Java', modernizationType='migrate', name='Apps_BuildStarted')
              | project Date, UserSource, Started = Count;
let passed  = Get28DayRollingAggregation(language='Java', modernizationType='migrate', name='Apps_BuildPassed')
              | project Date, UserSource, Passed = Count;
started
| join kind=leftouter passed on Date, UserSource
| extend Passed = coalesce(Passed, 0)
| extend SuccessRate = iff(Started == 0, 0.0, todouble(Passed) / todouble(Started))
```

- ID parsing/derivation
  - Description: Extract AppId/projectId and other keys from Properties/customDimensions.
  - Snippets:
```kusto
// VSCode Ext Properties
| extend p = parse_json(Properties)
| extend AppId = tostring(p['hashedappid'])
| extend projectId = tostring(p['hashedprojectid'])
| extend requestId = tostring(p['requestid'])
| extend conversationId = tostring(p['conversationid'])

// Copilot customDimensions
| extend dimensions = parse_json(customDimensions)
| extend AppId = tostring(dimensions.hashedappid)
| extend projectId = tostring(dimensions.hashedprojectid)
| extend DevDeviceId = tostring(dimensions.devdeviceid)
| extend correlationId = tostring(dimensions.correlationid)
```

- Sharded union
  - Description: Merge same-logic signals across Copilot and VSCode shards; normalize and summarize.
  - Snippet:
```kusto
let start = startofday(ago(28d));
let end = startofday(now());

(
  cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
  | where ServerTimestamp between (start .. (end - 1s))
  | where ExtensionName has "migrate-java-to-azure"
  | project DevDeviceId, Date = bin(ServerTimestamp, 1d), AppId = tostring(Properties['hashedappid'])
  | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
  | extend user_source = iff(tobool(IsInternal1), 'internal', 'external')
)
| union (
  cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
  | where timestamp between (start .. (end - 1s))
  | where operation_Name startswith 'java/migrateassistant'
  | extend dimensions = parse_json(customDimensions)
  | project DevDeviceId = tostring(dimensions.devdeviceid),
            Date = bin(timestamp, 1d),
            AppId = tostring(dimensions.hashedappid),
            user_source = iff(tobool(dimensions.internal), 'internal', 'external')
)
| summarize Users = dcount(DevDeviceId) by Date, user_source
```

## Example Queries (with explanations)

1) Java MEU (28-day rolling, Consolidation function)
- Description: Fetches 28-day rolling Monthly Engaged Users for Java migrate, aggregated by user source and day. Adapt by changing Name ('Users_MEU' → 'Users_MAU'/'Users_Adoption'), language, or modernizationType. Use Date >= startofday(ago(28d)) to restrict window.
```kusto
cluster("appmod.westus2.kusto.windows.net").database("Consolidation").Get28DayRollingAggregation('Java', 'migrate', 'Users_MEU')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))
```

2) Build Success Rate (rolling aggregation join)
- Description: Computes per-day build success rate by joining BuildStarted and BuildPassed rolling counts; handles missing counts with coalesce and outputs percentage. Adapt by changing language/modernizationType and metric names.
```kusto
GetBuildSuccessRate(language:string, modernizationType:string)
{
    let buildStartedOverTime = materialize(
    Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Apps_BuildStarted")
    | project Date, UserSource, BuildStartedCount = Count
);
    let buildPassedOverTime = materialize(
        Get28DayRollingAggregation(language=language, modernizationType=modernizationType, name="Apps_BuildPassed")
        | project Date, UserSource, BuildPassedCount = Count
    );
    buildStartedOverTime
    | join kind=leftouter buildPassedOverTime on Date, UserSource
    | extend BuildPassedCount = coalesce(BuildPassedCount, 0)
    | extend SuccessRate = case(
        BuildStartedCount == 0, 0.0,
        todouble(BuildPassedCount) / todouble(BuildStartedCount)
    )
    | extend SuccessRatePercent = round(SuccessRate * 100, 2)
    | project 
        Date,
        language,
        modernizationType,
        UserSource,
        BuildStartedCount,
        BuildPassedCount,
        SuccessRate,
        SuccessRatePercent
}
```

3) MAU for VSCode extension with MCP union
- Description: Computes daily distinct users for the "migrate-java-to-azure" extension across VSCode Ext, VSCode activation, and MCP telemetry. Excludes activation-only info events; derives user_source via internal fact join. Adapt by window and add/remove sources.
```kusto
mau_vscode_users_helper(start:datetime, end:datetime)
{
    cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
    | where ServerTimestamp between (start .. (end - 1s))
    | where ServerTimestamp >= datetime(2025-05-20)
    | where ExtensionName has "migrate-java-to-azure"
    | where EventName !has 'migrate-java-to-azure/info'
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
    | project DevDeviceId, user_source, Date=bin(ServerTimestamp, 1d)
    | union (
    cluster('ddtelvscode.kusto.windows.net').database('VSCode').table('RawEventsVSCode')
    | where ServerUploadTimestamp between (startofday(start) .. startofday(end) -1s)
    | where EventName == "monacoworkbench/activateplugin"
    | where Properties.id == 'vscjava.migrate-java-to-azure'
    | where Properties.reason !in ('onStartupFinished') and Properties.reason !has 'pom.xml' and Properties.reason !has 'onLanguage:java'
    | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
    | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
    | project DevDeviceId, user_source, Date=bin(ServerUploadTimestamp, 1d)
    )
    | union (
    cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
    | where timestamp between (start .. (end - 1s))
    | where timestamp >= datetime(2025-07-31)
    | where operation_Name startswith 'java/migrateassistant'
    | extend dimensions = parse_json(customDimensions)
    | extend user_source = iff(tobool(dimensions.internal), 'internal', 'external')
    | extend DevDeviceId = tostring(dimensions.devdeviceid)
    | project DevDeviceId, user_source, Date=bin(timestamp, 1d)
    )
    | distinct DevDeviceId,user_source,Date;
}
```

4) Migration records with session/correlation hygiene
- Description: Identifies migration actions (excluding upgrade), aligns with Java project info via correlationId, and avoids double counting by excluding sessions that already have command events. Adapt by filters and tool sources.
```kusto
migration_records_with_appid_helper(start:datetime, end:datetime)
{
    let java_project_info =
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-08-10)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "java/migrateassistant/projectsize"
        | extend AppId = tostring(Properties['hashedappid']), correlationId = tostring(Properties['correlationid'])
        | distinct DevDeviceId,AppId,correlationId;
    let command_event = 
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has "java/migrateassistant/command"
        | where tostring(Properties.command) in ('migrate.java.formula.run', 'java.migrateassistant.handleMigrate')
        | extend migrateaction=tostring(Properties.migrateaction), migrateby = tostring(Properties.migrateby)
        | where migrateaction == 'migrate' and migrateby != "upgrade"
        | project source = iff(isempty(tostring(Properties.source)), 'unknown', tostring(Properties.source)),
                 ServerTimestamp,VSCodeSessionId, DevDeviceId,Properties, ExtensionVersion, correlationId = tostring(Properties['correlationid'])
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | extend  isJava = iff(parse_version(ExtensionVersion) >= parse_version("1.3.0"), DevDeviceId in (java_project_info | project DevDeviceId), true)
        | where isJava == true
        | join kind=leftouter (java_project_info) on correlationId
        | project source, ServerTimestamp,VSCodeSessionId, DevDeviceId, user_source,AppId,Properties,ExtensionVersion;
    let command_event_sessionIds =
        command_event 
        | distinct VSCodeSessionId;
    let agent_sole_event =
        cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | where EventName has 'java/migrateassistant/tool/invoke'
        | extend tool=tostring(Properties.invokedtoolid)
        | where tool has 'createMigrationPlan'
        | extend AppId = tostring(Properties['hashedappid'])
        | project Properties, ServerTimestamp,VSCodeSessionId, DevDeviceId,AppId
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | where VSCodeSessionId !in (command_event_sessionIds)
        | project source="copilotChat", ServerTimestamp,VSCodeSessionId, DevDeviceId, user_source,AppId,Properties;
    let mcp_sole_event =
        cluster('ddtelai.kusto.windows.net').database('Copilot').RawEventsTraces
        | where timestamp  between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-31)
        | where operation_Name == "java/migrateassistant/task/run"
        | extend DevDeviceId = tostring(customDimensions.devdeviceid)
        | project customDimensions, ServerTimestamp=timestamp, DevDeviceId, callersessionid=tostring(customDimensions.callersessionid),operation_ParentId, AppId = tostring(customDimensions.hashedappid)
        | extend VSCodeSessionId = iff(isnotempty(callersessionid), callersessionid, operation_ParentId)
        | where VSCodeSessionId !in (command_event_sessionIds) 
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal), 'internal', 'external')
        | project source="copilotChat", ServerTimestamp,VSCodeSessionId, DevDeviceId,AppId, user_source,Properties=customDimensions;
    union command_event, agent_sole_event, mcp_sole_event
}
```

5) Modules per project (with total rollup)
- Description: Merges module IDs from Copilot and VSCode sources, classifies internal/external, then summarizes module counts per project and provides a total rollup. Adapt by time window and sources; extend to regional shards if needed.
```kusto
let start= startofday(ago(28d));
let end = startofday(now());
cluster("ama4j.westus2.kusto.windows.net").database("bi").modules_per_project_helper(start,end)
| extend ModuleCount = strcat(tostring(ModuleCount)," modules")
```

6) Unique app records (VSCode + MCP + AppCAT-in-VSCode)
- Description: Collects AppId across three sources for "migrate-java-to-azure", normalizes Date and user_source, and yields a unified set for unique app counting. Adapt by adding filters or additional tools.
```kusto
unique_app_vscode_records_helper(start:datetime, end:datetime)
{
    let migrationAppIds = cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt').RawEventsVSCodeExt
        | where ServerTimestamp between (start .. (end - 1s))
        | where ServerTimestamp >= datetime(2025-05-20)
        | where ExtensionName has "migrate-java-to-azure"
        | extend p = parse_json(Properties)
        | extend AppId = tostring(p['hashedappid'])
        | where isnotempty(AppId)
        | join kind=leftouter cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights').fact_user_isinternal on DevDeviceId
        | extend user_source  = iff(tobool(IsInternal1), 'internal', 'external')
        | project Date=bin(ServerTimestamp,1d), AppId, user_source,DevDeviceId;
    let MCPmigrationAppIds = cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-07-31)
        | where operation_Name startswith 'java/migrateassistant'
        | extend dimensions = parse_json(customDimensions)
        | extend AppId = tostring(dimensions.hashedappid)
        | where isnotempty(AppId)
        | extend user_source = iff(tobool(dimensions.internal), 'internal', 'external')
        | project Date=bin(timestamp,1d), AppId, user_source,DevDeviceId=tostring(customDimensions.devdeviceid);
    let appcatInVScodeAppIds = cluster('ddtelai').database('Copilot').RawEventsTraces
        | where timestamp between (start .. (end - 1s))
        | where timestamp >= datetime(2025-05-20)
        | where operation_Name == 'java/appcat/project'
        | extend dimensions = parse_json(customDimensions)
        | extend callerId = tostring(dimensions.callerid)
        | where callerId has "vscjava.migrate-java-to-azure"
        | extend AppId = tostring(dimensions.project_identity)
        | where isnotempty(AppId)
        | extend data = parse_json(message)
        | extend user_source=iff(tobool(data.internal), 'internal', 'external')
        | project Date=bin(timestamp,1d), AppId,user_source,DevDeviceId=tostring(customDimensions.devdeviceid);
    union migrationAppIds,MCPmigrationAppIds, appcatInVScodeAppIds
}
```

7) Adoption user union
- Description: Builds a cohort of adoption users based on success outcomes across assessment, build fix, code accept, unit test, CVE fix, and consistency check. Adapt by adding further success criteria.
```kusto
let start= startofday(ago(28d));
let end = startofday(now());
cluster("ama4j.westus2.kusto.windows.net").database("bi").adoption_user_helper(start,end)
```

8) Project size distribution from session events
- Description: Summarizes appcat project size categories from project events; useful for understanding codebase scale distribution. Adapt by window and bucket thresholds if definitions change.
```kusto
let start= startofday(datetime(2025-08-21));
let end = startofday(now());
cluster("ama4j.westus2.kusto.windows.net").database("bi").project_size_helper(start,end)
```

## Reasoning Notes (only if uncertain)
- Timezone: Not stated; we assume UTC as default for bin() and startofday.
- MEU definition: Based on dcount(Date) >= 2 (explicit in queries); we adopt this exact threshold.
- Adoption definition: Union of multiple success outcomes (explicit via helper); we adopt as-is without adding implicit criteria.
- CLI vs VSCode vs MCP disambiguation: Based on callerId and specific tool invocation names; we adopt these filters as they appear consistently.
- Excluding current day: The use of startofday(now()) and (end - 1s) suggests avoiding current-day partial ingestion; we adopt this conservatively across examples.
- Dedup via correlationId and session gating: We adopt arg_max by correlationId and VSCodeSessionId !in (...) patterns to avoid double counting mixed sources.
- Project size buckets: The explicit numeric thresholds are used as-is; we assume they remain stable unless product updates redefine them.
- “latest” version exclusion: We interpret appcatVersion != 'latest' as excluding placeholder/non-specific version entries; we preserve this filter.

## Canonical Tables

This playbook summarizes the canonical tables referenced by the Application Modernization for Java and .NET product (primary: cluster appmod.westus2.kusto.windows.net, database Consolidation), including their purpose, common filters, and column schemas. Where cross-cluster schemas could not be retrieved, we explicitly call that out and provide conservative, inference-based guidance drawn from how the queries use those tables.

Note: For tables where get_table_schema succeeded, the column lists are exact. For others, schema access was denied; columns are inferred from query usage and should be verified.

---

### Table: RawEventsTraces — cluster('ddtelai.kusto.windows.net').database('Copilot')
- Priority: Normal
- What this table represents: Event-level telemetry (fact/logs) from MCP/Copilot-side operations (e.g., java/migrateassistant/*, java/appcat/*). Zero rows simply means no events matched the filters/time window; it does not imply deletion.
- Freshness expectations: Typically near-real-time ingestion for traces; exact delay unknown. Be cautious with same-day analysis before late-day backfills.
- When to use / When to avoid:
  - Use for: MCP-side events for assessment, migration, build/test/cve fix outputs, MCP tool invocations, and deriving user_source/internal via dimensions.
  - Use for: Joining with VSCode events by correlation/session (callersessionid, operation_ParentId) to build end-to-end flows.
  - Avoid for: Aggregated 28d metrics (prefer bi/consolidation aggregate tables or appmod Consolidation functions).
  - Avoid for: VSCode agent-side activation/events (prefer RawEventsVSCode or RawEventsVSCodeExt).
- Similar tables & how to choose:
  - RawEventsVSCodeExt: VSCode extension agent-side events. Choose when the source is “migrate-java-to-azure” extension.
  - RawEventsVSCode: VSCode platform pipeline events (e.g., activation).
  - Choose RawEventsTraces for MCP/Copilot telemetry with operation_Name like java/migrateassistant/* or java/appcat/*.
- Common Filters:
  - Time: timestamp between (start .. end)
  - Event: operation_Name has/== 'java/migrateassistant/*' or 'java/appcat/*'
  - Dimensions: customDimensions fields: devdeviceid, callerid, internal flags, hashedappid, hashedprojectid, correlationid, callersessionid, appcatversion, status/result fields
  - Internal/external: compute user_source via message/internal or customDimensions.internal
- Table columns:
  
  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | timestamp            | datetime | Event time; primary time filter. |
  | severityLevel        | string   | Trace severity; often unused for product metrics. |
  | message              | string   | Raw payload; often JSON; includes “internal” for some events. |
  | operation_Name       | string   | Event operation name (e.g., java/migrateassistant/buildFix/output). |
  | operation_Id         | string   | Operation correlation id (used in joins like assessment project/report pairs). |
  | operation_ParentId   | string   | Parent operation/session id; alternative to callersessionid for joins. |
  | customDimensions     | dynamic  | JSON bag with properties like devdeviceid, internal, callersessionid, correlationid, hashedappid, hashedprojectid, appcatversion, result, etc. |
  | customMeasurements   | dynamic  | Numeric metrics bag; rarely used here. |
  | RecordId             | string   | Internal record id. |
  | DataHandlingTags     | string   | Data handling classification. |
  | NovaProperties       | dynamic  | Additional metadata. |
  | client_CountryOrRegion | string | Geo hint. |
  | IsInternal           | bool     | Internal flag at table level (may also be provided in message/customDimensions). |
- Column Explain:
  - timestamp: Required for time window filtering and daily binning.
  - operation_Name: The primary discriminator of scenario (assessment/report/migration/build/test/cve).
  - customDimensions: Source for DevDeviceId, callersessionid, correlationid, hashedappid/projectid, appcatversion, result. Central to all joins and user/app attribution.
  - operation_Id / operation_ParentId: Used to correlate related events (e.g., project and report).
  - message: Alternate source for internal flag when using appcat CLI.

---

### Table: RawEventsVSCodeExt — cluster('ddtelvscode.kusto.windows.net').database('VSCodeExt')
- Priority: Normal
- What this table represents: VSCode extension (agent) telemetry for “migrate-java-to-azure”—fact/logs emitted from the extension. Zero rows ⇒ no matching events/time.
- Freshness expectations: Near-real-time ingestion for extension streams; exact delay unknown.
- When to use / When to avoid:
  - Use for: Extension event flows (command, tool invoke, buildfix output), Properties.* like hashedappid/hashedprojectid, correlationid, VSCodeSessionId, and extension version gating.
  - Use for: Deriving user_source via joining VsCodeInsights.fact_user_isinternal on DevDeviceId.
  - Avoid for: MCP-only events (use RawEventsTraces).
  - Avoid for: Platform activation events handled by RawEventsVSCode.
- Similar tables & how to choose:
  - RawEventsVSCode: Contains platform-level events like monacoworkbench/activateplugin; use when tracing activation reasons.
  - RawEventsTraces: MCP telemetry when tool operations run on Copilot service.
- Common Filters:
  - Time: ServerTimestamp between (start .. (end - 1s))
  - ExtensionName has "migrate-java-to-azure"
  - EventName has java/migrateassistant/*; specific commands/tools
  - Join with fact_user_isinternal on DevDeviceId to compute user_source
- Table columns:
  
  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | EventName            | string   | Event name (e.g., java/migrateassistant/command). |
  | Attributes           | dynamic  | Additional attributes. |
  | ClientTimestamp      | datetime | Client-side event time. |
  | DataHandlingTags     | string   | Data handling. |
  | ExtensionName        | string   | Extension identifier; filter to migrate-java-to-azure. |
  | ExtensionVersion     | string   | Extension version; used for gating (e.g., >= 1.3.0). |
  | GeoCity              | string   | Geo hint. |
  | GeoCountryRegionIso  | string   | Geo ISO. |
  | Measures             | dynamic  | Numeric measures. |
  | NovaProperties       | dynamic  | Additional metadata. |
  | Platform             | string   | VSCode platform. |
  | PlatformVersion      | string   | Platform version. |
  | Properties           | dynamic  | JSON bag with fields like command, invokedtoolid, hashedappid, hashedprojectid, correlationid, source, result, etc. |
  | ServerTimestamp      | datetime | Ingestion pipeline time used for server-side windowing. |
  | Tags                 | dynamic  | Tags. |
  | VSCodeMachineId      | string   | Machine id. |
  | VSCodeSessionId      | string   | Session id; used to correlate events. |
  | VSCodeVersion        | string   | VSCode version. |
  | WorkloadTags         | string   | Workload tags. |
  | LanguageServerVersion| string   | Language server version. |
  | SchemaVersion        | string   | Schema version. |
  | Method               | string   | Method. |
  | Duration             | real     | Duration. |
  | SQMMachineId         | string   | SQM id. |
  | DevDeviceId          | string   | Device id; primary join key to fact_user_isinternal. |
  | IsInternal           | bool     | Internal flag at table level (not always used). |
  | ABExpAssignmentContext | string | A/B context. |
  | Source               | string   | Event source; sometimes present. |
  | SKU                  | string   | SKU. |
  | Model                | string   | Model. |
  | RequestId            | string   | Request id. |
  | ConversationId       | string   | Conversation id (Copilot chat). |
  | ResponseType         | string   | Response type. |
  | ToolName             | string   | Tool name. |
  | Outcome              | string   | Outcome (accept/reject/etc.). |
  | IsEntireFile         | string   | Whole-file indicator (string). |
  | ToolCounts           | string   | Tool counts. |
  | Isbyok               | int      | BYOK flag. |
  | TimeToFirstToken     | int      | Latency. |
  | TimeToComplete       | int      | Latency. |
  | TimeDelayms          | int      | Delay. |
  | SurvivalRateFourgram | real     | Metric. |
  | TokenCount           | real     | Tokens. |
  | PromptTokenCount     | real     | Prompt tokens. |
  | NumRequests          | int      | Number of requests. |
  | Turn                 | int      | Conversation turn. |
  | ResponseTokenCount   | real     | Response tokens. |
  | TotalNewDiagnostics  | int      | Diagnostics. |
  | Rounds               | real     | Rounds. |
  | AvgChunkSize         | real     | Average chunk size. |
  | Command              | string   | Command text. |
  | CopilotTrackingId    | string   | Tracking id. |
  | IntentId             | string   | Intent id. |
  | Participant          | string   | Participant. |
  | ToolGroupState       | string   | Tool group state. |
  | DurationMS           | long     | Duration (ms). |
- Column Explain:
  - ServerTimestamp: Primary server-side time for filtering and binning.
  - ExtensionName/EventName: Scope to migrate-java-to-azure and specific actions (command/tool/invoke/buildfix).
  - Properties: Core of business semantics: command, invokedtoolid, hashedappid/projectid, correlationid, result.
  - DevDeviceId + VSCodeSessionId: Keys for identity (device) and session correlation.
  - ExtensionVersion: Gating features (e.g., Java detection behavior).

---

### Table: RawEventsVSCode — cluster('ddtelvscode.kusto.windows.net').database('VSCode')
- Priority: Normal
- What this table represents: VSCode platform telemetry (fact/logs), e.g., activation events for plugins.
- Freshness expectations: Near-real-time; exact delay unknown.
- When to use / When to avoid:
  - Use for: Activation events (monacoworkbench/activateplugin) and reasons, plugin id filtering.
  - Avoid for: Agent extension’s own events (use RawEventsVSCodeExt).
  - Avoid for: MCP telemetry (use RawEventsTraces).
- Similar tables & how to choose:
  - RawEventsVSCodeExt for extension-emitted events.
  - RawEventsTraces for service-side events.
- Common Filters:
  - Time: ServerUploadTimestamp between (startofday(start) .. startofday(end) -1s)
  - EventName == "monacoworkbench/activateplugin"
  - Properties.id == 'vscjava.migrate-java-to-azure'
  - Properties.reason filters (exclude onStartupFinished/pom.xml/onLanguage:java for engagement)
  - Join fact_user_isinternal for user_source
- Table columns:
  
  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | EventName            | string   | Event name (activation etc.). |
  | ApplicationVersion   | string   | Version. |
  | Attributes           | dynamic  | Additional attributes. |
  | ClientTimestamp      | datetime | Client event time. |
  | CommitHash           | string   | Build commit. |
  | DataHandlingTags     | string   | Data handling. |
  | FirstSessionDate     | datetime | First session. |
  | GeoCity              | string   | City. |
  | GeoCountryRegionIso  | string   | Country ISO. |
  | InstanceId           | string   | Instance id. |
  | IsNewSession         | bool     | New session flag. |
  | LastSessionDate      | datetime | Last session. |
  | Measures             | dynamic  | Numeric measures. |
  | NovaProperties       | dynamic  | Additional metadata. |
  | OSVersion            | string   | OS version. |
  | Platform             | string   | Platform. |
  | Properties           | dynamic  | JSON bag; includes id and reason used for filtering. |
  | RendererVersion      | string   | Renderer version. |
  | Sequence             | long     | Sequence. |
  | ServerUploadTimestamp| datetime | Upload time; primary server-side time. |
  | SessionId            | string   | Session id. |
  | ShellVersion         | string   | Shell version. |
  | Tags                 | dynamic  | Tags. |
  | TimeSinceSessionStart| long     | Time since start. |
  | VirtualMachineHint   | string   | VM hint. |
  | VSCodeMachineId      | string   | Machine id. |
  | WorkloadTags         | string   | Workload tags. |
  | MimeType             | string   | Mime type. |
  | CommonProduct        | string   | Product name. |
  | Ext                  | string   | Extension info. |
  | IdProperty           | string   | Id property. |
  | AbexpAssignmentContext | string | A/B context. |
  | SchemaVersion        | string   | Schema. |
  | SQMMachineId         | string   | SQM id. |
  | DevDeviceId          | string   | Device id for joining to internal status. |
  | IsInternal           | bool     | Internal flag (table-level). |
- Column Explain:
  - ServerUploadTimestamp: Used for time windows and daily bins.
  - Properties.id and Properties.reason: Key filters to identify true activations attributable to extension usage.
  - DevDeviceId: Join key to fact_user_isinternal to compute user_source.

---

### Table: fact_user_isinternal — cluster('ddtelvscode.kusto.windows.net').database('VsCodeInsights')
- Priority: Normal
- What this table represents: Lookup/fact mapping devices (DevDeviceId) to internal status. Zero rows indicates unknown device.
- Freshness expectations: Unknown; typically updated periodically as new devices appear.
- When to use / When to avoid:
  - Use for: Deriving user_source ('internal' vs 'external') via DevDeviceId joins across VSCodeExt, VSCode, and sometimes MCP-derived DevDeviceId.
  - Avoid for: Direct activity counts (use event/aggregate tables).
- Similar tables & how to choose: None direct; sometimes “IsInternal” shows up in event tables, but this lookup is canonical for VSCode device identity.
- Common Filters:
  - Join: join kind=leftouter ... on DevDeviceId
  - Projection: IsInternal as 1/0; convert to bool and map to 'internal'/'external'
- Table columns:
  
  | Column     | Type   | Description or meaning |
  |------------|--------|------------------------|
  | DevDeviceId| string | Device identifier; primary join key. |
  | IsInternal | long   | 1 for internal, 0 for external. |
- Column Explain:
  - DevDeviceId: Key used across all event streams to classify users.
  - IsInternal: Convert with iff(tobool(IsInternal), 'internal', 'external').

---

### Table: RawEventsVSBlessed — cluster('ddtelvsraw.kusto.windows.net').database('VS')
- Priority: Normal
- What this table represents: Visual Studio “blessed” raw events for Product == "appmod"; used to analyze VS extension events (non-VSCode) with whitelist filtering. Zero rows means no VS-side events matched.
- Freshness expectations: Unknown.
- When to use / When to avoid:
  - Use for: VS telemetry with Product == "appmod", extracting Status/ErrorCode/ExtensionVersion/HashedAppSolutionId from Properties and Measures[duration].
  - Avoid for: VSCode/MCP telemetry (use RawEventsVSCode* or RawEventsTraces).
- Similar tables & how to choose: Use RawEventsVSBlessed for Visual Studio; use RawEventsVSCodeExt/VSCode for VSCode; RawEventsTraces for MCP.
- Common Filters:
  - Product == "appmod"
  - UserAlias not in whitelist
  - user_source via IsInternal
- Schema access: get_table_schema failed (Access denied). Columns below are inferred from query usage and likely patterns; verify on cluster.
  
  | Column              | Type     | Description or meaning |
  |---------------------|----------|------------------------|
  | Product             | string   | Filtered to "appmod". |
  | UserAlias           | string   | Used for whitelist exclusions. |
  | IsInternal          | bool     | Internal user flag. |
  | Properties          | dynamic  | status, errorcode, extensionversion, hashedappsolutionid. |
  | Measures            | dynamic  | duration (Measures["duration"]). |
- Column Explain:
  - Properties: Primary source for status/errorcode/version/app solution id.
  - IsInternal → user_source: Map to 'internal'/'external'.

---

### Table: Catalog_Events_IntelliCode_VSConversation — cluster('ddtelinsights.kusto.windows.net').database('DDTelInsights')
- Priority: Normal
- What this table represents: VS IntelliCode Copilot conversation events. Used when client id equals Microsoft.AppModernization and to derive internal/external.
- Freshness expectations: Unknown.
- When to use / When to avoid:
  - Use for: Filtering conversations where Properties["vs.copilot.clientid"] == "Microsoft.AppModernization".
  - Avoid for: VSCode/MCP telemetry streams; use VSCodeExt/RawEventsTraces instead.
- Similar tables & how to choose: Choose this for Visual Studio IntelliCode conversations; VSCodeExt for VSCode Copilot chat panel telemetry.
- Common Filters:
  - Properties["vs.copilot.clientid"] == "Microsoft.AppModernization"
  - UserAlias not in whitelist
  - user_source via IsInternal
- Schema access: get_table_schema failed (Access denied). Columns below are inferred from query usage; verify on cluster.
  
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | Properties | dynamic  | Includes "vs.copilot.clientid". |
  | UserAlias  | string   | Whitelist filtering. |
  | IsInternal | bool     | Internal user classification. |
- Column Explain:
  - Properties["vs.copilot.clientid"] selects App Modernization conversations.
  - IsInternal drives user_source.

---

### Table: mau_total — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- What this table represents: Daily aggregate for monthly active users (MAU) over last 28 days for Java migrate; aggregated (rolling) facts. Zero rows suggests missing aggregation window.
- Freshness expectations: Typically daily aggregates; exact refresh time unknown. Treat current day with caution.
- When to use / When to avoid:
  - Use for: High-level MAU tracking over Date with user_source slice.
  - Avoid for: Per-event detail; use RawEvents*.
- Similar tables & how to choose: Use MEU tables for multi-engagement users; use other users_count_*/sessions_count_* for scoped funnels.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Schema access: get_table_schema failed (Access denied). Columns inferred; verify on cluster.
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Date        | datetime | Daily date key. |
  | user_source | string   | 'internal'/'external'. |
  | Count       | long     | Aggregated users; exact column name may differ. |
- Column Explain:
  - Date and user_source drive time series segmentation.

---

### Table: unique_app_count_28d_total — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- What this table represents: Daily aggregate of distinct apps (modules) over 28d window (total). Aggregate.
- Freshness expectations: Daily; exact refresh unknown.
- When to use / When to avoid:
  - Use for: Unique app/module coverage across all activity.
  - Avoid for: Per-app breakdowns; use helpers to compute unions from raw streams.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Schema access: Access denied; inferred.
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Date        | datetime | Daily date key. |
  | user_source | string   | 'internal'/'external'. |
  | Count       | long     | Distinct apps in 28d; name may differ. |
- Column Explain:
  - Date and user_source are primary filters.

---

### Table: unique_app_count_28d_assessed — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- What this table represents: Daily aggregate of distinct apps assessed over 28d. Aggregate.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use for: Assess coverage.
  - Avoid for: Detailed per-assessment events; use RawEventsTraces/views.
- Common Filters: Date, user_source as above.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Date        | datetime | Daily date key. |
  | user_source | string   | 'internal'/'external'. |
  | Count       | long     | Distinct assessed apps; name may differ. |
- Column Explain: As above.

---

### Table: unique_app_count_28d_migration — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- What this table represents: Daily aggregate distinct apps with code remediation/migration (28d). Aggregate.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use for: Migration coverage trend.
  - Avoid for: Per-tool invocations; use migration_records_* helpers.
- Common Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Date        | datetime | Daily date key. |
  | user_source | string   | 'internal'/'external'. |
  | Count       | long     | Distinct migration apps; name may differ. |

---

### Table: unique_app_count_28d_assessreport — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- What this table represents: Daily aggregate distinct apps with generated assessment report (28d). Aggregate.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use for: Report generation coverage.
- Common Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Date        | datetime | Daily date key. |
  | user_source | string   | 'internal'/'external'. |
  | Count       | long     | Distinct apps with reports; name may differ. |

---

### Table: users_count_28d_assess — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- What this table represents: Daily aggregate user counts engaging in assessment (28d). Aggregate.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use for: Assessment user trend by user_source.
- Common Filters: Date >= startofday(ago(28d)), isnotempty(user_source).
- Schema access: Access denied; inferred.

  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Date        | datetime | Daily date key. |
  | user_source | string   | 'internal'/'external'. |
  | Users       | long     | Count of users; name may differ (e.g., Count). |

---

### Table: users_count_28d_assessreport — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- Represents: Daily aggregate users generating assessment reports (28d). Aggregate.
- Freshness: Daily (unknown exact time).
- Use/Avoid: Use for report-user trend; avoid for raw report correlation (use RawEventsTraces).
- Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily date. |
  | user_source | string   | Segment. |
  | Users       | long     | Count (name may differ). |

---

### Table: users_count_28d_migrationplan — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- Represents: Daily aggregate users creating migration plans (28d). Aggregate.
- Freshness: Daily.
- Use/Avoid: Use for plan creation users; avoid for per-plan detail (use migration_plan_records_helper).
- Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily date. |
  | user_source | string   | Segment. |
  | Users       | long     | Count (name may differ). |

---

### Table: users_count_28d_buildfix — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- Represents: Daily aggregate users starting/passing build fix (28d). Aggregate.
- Freshness: Daily.
- Use/Avoid: Use for buildfix users; avoid for outcome per correlationId (use build_result_records_*).
- Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily date. |
  | user_source | string   | Segment. |
  | Users       | long     | Count (name may differ). |

---

### Table: sessions_count_28d_assess — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- Represents: Daily aggregate sessions starting assessment (28d). Aggregate.
- Freshness: Daily.
- Use/Avoid: Use for session volume; avoid for user-level dedupe (use users_count_*).
- Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily. |
  | user_source | string   | Segment. |
  | Sessions    | long     | Count (name may differ). |

---

### Table: sessions_count_28d_codeRemediation — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- Represents: Daily aggregate sessions with code remediation/migration activity (28d). Aggregate.
- Freshness: Daily.
- Use/Avoid: Use for remediation session trends; avoid for detailed tool outcomes (use RawEventsTraces/VSCodeExt).
- Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily. |
  | user_source | string   | Segment. |
  | Sessions    | long     | Count (name may differ). |

---

### Table: sessions_count_28d_buildfix — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- Represents: Daily aggregate sessions for buildfix (28d). Aggregate.
- Freshness: Daily.
- Use/Avoid: Use for buildfix session trend; avoid for success rate calc details (use build_success_records_helper).
- Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily. |
  | user_source | string   | Segment. |
  | Sessions    | long     | Count (name may differ). |

---

### Table: sessions_count_28d_assessreport — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- Represents: Daily aggregate sessions generating assessment reports (28d). Aggregate.
- Freshness: Daily.
- Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily. |
  | user_source | string   | Segment. |
  | Sessions    | long     | Count (name may differ). |

---

### Table: users_count_28d_migration — cluster('ama4j.westus2.kusto.windows.net').database('bi')
- Priority: Normal
- Represents: Daily aggregate users performing migration/code remediation (28d). Aggregate.
- Freshness: Daily.
- Use/Avoid: Use for migration users trend; avoid for per-app attribution (use migration_records_with_appid_helper).
- Filters: Date, user_source.
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily. |
  | user_source | string   | Segment. |
  | Users       | long     | Count (name may differ). |

---

### Table: users_code_remediation_consolidated_java_upgrade_java_migrate — cluster('ama4j.westus2.kusto.windows.net').database('consolidation')
- Priority: Normal
- What this table represents: Consolidated daily aggregates for “java_upgrade_java_migrate” product (users). Aggregate.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use for: Product-scoped users trend across consolidate sources.
  - Avoid for: Non-consolidated per-source analysis (use bi tables or raw streams).
- Common Filters:
  - isnotempty(user_source)
  - product == 'java_upgrade_java_migrate'
  - Date >= startofday(ago(28d))
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily. |
  | user_source | string   | Segment. |
  | product     | string   | Should equal 'java_upgrade_java_migrate'. |
  | Users       | long     | Aggregated users (name may differ). |

- Column Explain:
  - product enforces product-scope in consolidation.

---

### Table: sessions_code_remediation_consolidated_java_upgrade_java_migrate — cluster('ama4j.westus2.kusto.windows.net').database('consolidation')
- Priority: Normal
- What this table represents: Consolidated daily aggregates for “java_upgrade_java_migrate” product (sessions). Aggregate.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use for: Consolidated session trend for remediation.
- Common Filters:
  - isnotempty(user_source)
  - product == 'java_upgrade_java_migrate'
  - Date >= startofday(ago(28d))
- Schema access: Access denied; inferred.

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Daily. |
  | user_source | string   | Segment. |
  | product     | string   | 'java_upgrade_java_migrate'. |
  | Sessions    | long     | Aggregated sessions (name may differ). |

- Column Explain:
  - product filters to consolidated product scope.

---

If you need exact schemas for the bi/consolidation/VS/Insights clusters listed above, request access and rerun get_table_schema to validate column names and types.