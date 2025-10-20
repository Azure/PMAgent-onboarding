# Application Modernization for Java and .NET - Product and Data Overview Template

## 1. Product Overview

The Application Modernization for Java and .NET product provides top-level metrics built from aggregated telemetry. Aggregations are derived from raw telemetry via pre-defined Kusto functions and daily rolling windows. This schema enables PMAgent to understand cohorting by UserSource, multi-stage funnels (assess, assessreport, buildfix, migrationplan, adoption, execute), and consistent time handling anchored to completed days.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
Application Modernization for Java and .NET
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
https://appmod.westus2.kusto.windows.net/
- **Kusto Database**:
Consolidation
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Application Modernization for Java and .NET - Kusto Query Playbook

## Overview
- Product summary: The dashboard of Application Modernization is the top level metrics for the product built on aggregated telemetries. The aggregated telemetries comes from raw telemetries by pre-defined Kusto functions.
- Main cluster: https://appmod.westus2.kusto.windows.net/
- Main database: Consolidation
- Note: Queries also reference alternate sources on https://ama4j.westus2.kusto.windows.net/ (databases consolidation and bi) for specific helper computations.

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - Date: the primary time column used for filtering and joins.
  - DataIngestTimestamp: used only in arg_max() to select the latest aggregated value per day.
- Canonical Time Column: Date
  - Alignment pattern:
    - Standardize to a single alias when mixing sources with different cases:
      - project-rename Time = Date
    - If sources use different casings for cohort (“UserSource” vs “user_source”), normalize early:
      - project-rename UserSource = user_source
- Typical windows and resolution:
  - Rolling 28 days: Date >= startofday(ago(28d))
  - Some percentile tiles use 29-day filters (e.g., startofday(ago(29d)))
  - Daily granularity via startofday(Date) in summarization
- Timezone:
  - Not specified; assume UTC. Be cautious with “today” until ingestion freshness is confirmed.

### Freshness & Completeness Gates
- Ingestion cadence is not provided. Several helper queries explicitly set an end anchor at startofday(now()) to avoid partial current-day data.
- Recommended effective end-time strategy:
  - Use end = startofday(now()) and compute windows relative to that end.
  - Prefer last fully completed day or previous complete week for reporting windows where completeness is critical.
- Multi-slice completeness gate (recommended pattern when unknown):
  - Identify latest day where ≥N sentinel cohorts (e.g., user_source slices) have non-empty data.
  - Select that day as effective end and compute rolling windows backward from it.

### Joins & Alignment
- Frequent keys:
  - Date, UserSource (sometimes lowercase user_source)
- Typical join kinds:
  - inner (to ensure both slices exist)
- Post-join hygiene:
  - Normalize column case first (project-rename).
  - Drop duplicate columns after join (project-away Count1, etc.).
  - Use coalesce() when reconciling differing cohort column names.

### Filters & Idioms
- Common predicates:
  - isnotempty(UserSource) or isnotempty(user_source) used as a default cohort gate.
  - Date >= startofday(ago(28d)) used widely for rolling windows.
- Cohort case normalization:
  - project-rename UserSource = user_source
- Allowlist/Denylist cohorts (recommended placeholders):
  - Build allowed cohorts first, then inner join to facts.
  - Maintain placeholder lists for internal/test exclusions (e.g., <TestUserSourceList>).

### Cross-cluster/DB & Sharding
- Qualification:
  - Use cluster('https://...').database('db') to target alternate sources.
- Sharded union pattern (same-schema across databases):
  - union → normalize keys/time → summarize
  - Always align Date to startofday and normalize UserSource casing before aggregates.

### Table classes
- Pre-aggregated rolling tables:
  - Examples: users_count_28d_*, sessions_count_28d_*, unique_app_count_28d_*
  - Already computed counts (often need arg_max(DataIngestTimestamp, …) to pick latest per day).
- Pre-aggregated function outputs:
  - Get28DayRollingAggregation(language, modernizationType, name) returns (Date, UserSource, Count) style rolling aggregates.
- Helper functions (aggregated/fact-derived):
  - avg_users_per_app_helper, project_size_new_helper, project_size_helper, modules_per_project_helper, lines_of_code_java_upgrade_helper
  - These accept explicit start/end and compute metrics from raw/fact sources.

### Important Mapping
- Tile/page title to query intent (examples):
  - 'java_migrate_meu_total' → Get28DayRollingAggregation('Java', 'migrate', 'Users_MEU')
  - 'java_migrate_unique_app_28d_assessed' → unique_app_count_28d_assessed with arg_max per day
  - 'dotnet_migrate_apps_28d_AverageUsers' → ratio of Users_MAU to Apps_All by Date, UserSource
  - 'java_consolidated_lines_of_code_per_project' → cross-db union of lines_of_code helpers with percentiles

## Entity & Counting Rules (Core Definitions)
- Entity model and keys (as observed):
  - Cohort: UserSource (sometimes user_source)
  - Applications: AppId (used in dcount_AppId aggregations)
  - Users/Devices: DevDeviceId (used in dcount_DevDeviceId aggregations)
  - Projects: projectId appears in helper function outputs
- Standard grouping:
  - Date (daily) and UserSource are the primary grouping dimensions across queries.
- Business definitions (names imply intent but exact conditions are defined by functions):
  - Users_MAU/MEU: monthly/engaged users metrics produced by Get28DayRollingAggregation
  - Apps_* (e.g., All, AssessmentStarted, BuildStarted): app-level stage counts
  - Sessions_* (e.g., BuildStarted, CodeRemediationStarted): session-stage counts
  - Execute/Plan/ValidationPassed: stage-specific metrics for “migrate” and “upgrade”
- Counting do/don’t:
  - Do use arg_max(DataIngestTimestamp, <metric>) to select the latest daily aggregate when the source provides multiple rows per day.
  - Don’t mix UserSource vs user_source without normalization.
  - Do avoid current-day partial data by using startofday(now()) as end in helper functions.

## Views (Reusable Layers)


## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Standardize rolling windows, avoid partial current-day data, and anchor queries to day boundaries.
  - Snippet:
    ```kusto
    // Use UTC by default; anchor to completed days
    let endTime = startofday(now());
    let startTime = startofday(ago(28d));
    // Example: filter a pre-aggregated function output
    Get28DayRollingAggregation('Java', 'migrate', 'Users_MEU')
    | where Date >= startTime and Date < endTime
    | where isnotempty(UserSource) // normalize to use one casing
    ```

- Join template
  - Description: Combine multiple rolling aggregates by Date and UserSource; ensure cohesive cohorts.
  - Snippet:
    ```kusto
    // Normalize casing first if needed
    let A = Get28DayRollingAggregation('C#', 'migrate', 'Users_MAU')
            | project Date, UserSource, CountA = Count;
    let B = Get28DayRollingAggregation('C#', 'migrate', 'Apps_All')
            | project Date, UserSource, CountB = Count;
    A
    | join kind=inner B on Date, UserSource
    | project Date, UserSource, AvgUsersPerApp = iff(CountB == 0, 0.0, toreal(CountA) / CountB)
    ```

- De-dup pattern
  - Description: Resolve multiple daily rows in pre-aggregated tables; pick the latest ingestion slice.
  - Snippets:
    ```kusto
    // Unique app counts (latest per day)
    unique_app_count_28d_assessed
    | where isnotempty(user_source)
    | where Date >= startofday(ago(28d))
    | summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, day = startofday(Date)
    ```

    ```kusto
    // Sessions daily counts (latest per day)
    sessions_count_28d_assess
    | where isnotempty(user_source)
    | where Date >= startofday(ago(28d))
    | summarize arg_max(DataIngestTimestamp, count_) by user_source, day = startofday(Date)
    ```

- Important filters
  - Description: Cohort sanity, default exclusions, and normalization. Use placeholders for internal/test lists.
  - Snippet:
    ```kusto
    // Normalize cohort column and exclude internal/test cohorts via a maintained list
    let ExcludedSources = dynamic(["<TestSource1>", "<InternalSourceA>", "<BotSourceX>"]);
    Get28DayRollingAggregation('Java', 'migrate', 'Users_MAU')
    | project-rename UserSource = UserSource // or project-rename UserSource = user_source
    | where isnotempty(UserSource)
    | where UserSource !in (ExcludedSources)
    | where Date >= startofday(ago(28d))
    ```

- Important Definitions
  - Description: Use the Get28DayRollingAggregation name parameter to select metric families without redefining business logic.
  - Snippet:
    ```kusto
    // Example metric families (do not override definitions; use names as-is)
    Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_MAU')
    Get28DayRollingAggregation('Java', 'migrate', 'Apps_ValidationPassed')
    Get28DayRollingAggregation('C#', 'migrate', 'Sessions_BuildStarted')
    ```

- ID parsing/derivation
  - Description: When helper outputs include raw IDs (AppId, DevDeviceId, projectId), use them directly; parsing is not shown in provided queries.
  - Snippet:
    ```kusto
    // Placeholder: if an ID needs parsing, adapt as needed
    // Example path parse (replace with real field names as available)
    // | extend SubscriptionId = extract(@"subscriptions/([^/]+)", 1, ResourceId)
    ```

- Sharded union
  - Description: Merge same-schema helpers across databases; normalize cohorts and summarize percentiles.
  - Snippet:
    ```kusto
    let start = startofday(ago(28d));
    let end = startofday(now());
    let raw =
        union
        cluster('https://ama4j.westus2.kusto.windows.net/').database('consolidation').lines_of_code_java_upgrade_helper(start, end),
        cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').lines_of_code_helper(start, end);
    raw
    | summarize percentiles(lines, 95, 90, 75)
    | extend user_source = "total"
    | union (
        raw
        | summarize percentiles(lines, 95, 90, 75) by user_source
    )
    ```

## Example Queries (with explanations)

1) Java migrate MEU total
- Description: Retrieves 28-day rolling engaged users for Java migrate. Applies cohort presence gate and 28-day window.
```kusto
Get28DayRollingAggregation('Java', 'migrate', 'Users_MEU')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))
```

2) Java migrate unique apps assessed (latest per day)
- Description: Selects latest daily unique app count (by AppId) for assessed state using arg_max on DataIngestTimestamp.
```kusto
unique_app_count_28d_assessed
| where isnotempty(user_source)
| where Date >= startofday(ago(28d))
| summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, day = startofday(Date)
```

3) .NET migrate average users per app (ratio join)
- Description: Joins Users_MAU and Apps_All by Date and UserSource, computes ratio; adapt windows by changing ago() or anchoring end times.
```kusto
Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Users_MAU")
| join kind=inner Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Apps_All") on Date, UserSource
| project Date, UserSource, Count = iff(Count1 == 0, 0.0, toreal(Count) / Count1)
| where Date >= ago(28d)
```

4) .NET migrate sessions: Assessment + Copilot sums
- Description: Sums two session event families with an inner join on Date and UserSource; useful for combined activity tracking.
```kusto
Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Sessions_AssessmentStarted")
| join kind=inner Get28DayRollingAggregation(language="C#", modernizationType="migrate", name="Sessions_CopilotConversationStarted") on Date, UserSource
| project Date, UserSource, Count = Count + Count1
| where Date >= ago(28d)
```

5) Java consolidated lines of code per project (cross-db union + percentiles)
- Description: Merges lines-of-code computations from two databases on the ama4j cluster; computes 95/90/75 percentiles overall and per user_source; anchors end at startofday(now()).
```kusto
let start = startofday(ago(28d));
let end = startofday(now());
let raw =
union
cluster('https://ama4j.westus2.kusto.windows.net/').database('consolidation').lines_of_code_java_upgrade_helper(start, end),
cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').lines_of_code_helper(start, end);
raw
| summarize percentiles(lines, 95,90,75)
| extend user_source = "total"
| union (
    raw
    | summarize percentiles(lines, 95,90,75) by user_source
)
```

6) Java migrate sessions assessed (latest per day)
- Description: Uses arg_max(DataIngestTimestamp, count_) to pick the latest daily sessions count for assessed reports.
```kusto
sessions_count_28d_assess
| where isnotempty(user_source)
| where Date >= startofday(ago(28d))
| summarize arg_max(DataIngestTimestamp, count_) by user_source, day = startofday(Date)
```

7) Java consolidated module per project P90
- Description: Retrieves the P90 of apps/modules per project over a 29-day window; adapt window and percentile by changing name or ago().
```kusto
Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Apps_P90PerProject')
| where Date >= startofday(ago(29d))
```

8) Java upgrade MEU and MAU (cohorted)
- Description: 28-day rolling monthly/engaged users for Java upgrade cohorts; ensures cohort presence.
```kusto
Get28DayRollingAggregation('Java', 'upgrade', 'Users_MEU')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))

Get28DayRollingAggregation('Java', 'upgrade', 'Users_MAU')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))
```

9) Java migrate modules per project (helper + percentile)
- Description: Computes per-project module counts using a helper over an explicit start/end window; aggregates to P90 by cohort.
```kusto
let start = startofday(ago(28d));
let end = startofday(now());
modules_per_project_helper(start, end)
| summarize percentile(ModuleCount, 90) by user_source
```

10) Java consolidated users category metrics (plan/execute/security/quality)
- Description: Uses unified “migrate/upgrade” scope across user activity families; default cohort gate and rolling window.
```kusto
Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_Plan')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))

Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_Execute')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))

Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_SecurityExecute')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))

Get28DayRollingAggregation('Java', 'migrate/upgrade', 'Users_QualityExecute')
| where isnotempty(UserSource)
| where Date >= startofday(ago(28d))
```

## Reasoning Notes (only if uncertain)
- Get28DayRollingAggregation outputs:
  - Interpretation: returns pre-aggregated (Date, UserSource, Count) for a specific language, modernizationType, and named metric. Adopted because nearly all queries treat its output like a daily rolling fact with those columns.
- Timezone:
  - Unknown; adopt UTC as conservative default since queries use startofday/ago patterns without timezone hints.
- Cohort casing:
  - Both UserSource and user_source appear; adopt normalization via project-rename to avoid join/filter mismatch.
- Current-day completeness:
  - Some helpers explicitly use startofday(now()) as end; adopt practice to avoid partial current-day data.
- Table/function classes:
  - users_count_28d_* and sessions_count_28d_* appear to be pre-aggregated daily summaries requiring arg_max to choose the latest valid slice; adopt arg_max(DataIngestTimestamp, <metric>) for daily rollups.
- Cross-cluster sources:
  - The main product cluster is appmod.westus2; lines-of-code computations reference ama4j.westus2 across consolidation and bi DBs; adopt explicit qualification with cluster()/database() and union followed by normalization.

## Canonical Tables

The product’s main cluster/database is appmod.westus2.kusto.windows.net/Consolidation, but these canonical tables are sourced cross-cluster from ama4j.westus2.kusto.windows.net/bi. All are daily aggregates over rolling 28-day windows. Freshness and timezone are not documented; treat current-day data conservatively (use startofday and arg_max by day).

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').unique_app_count_28d_vscode
- Priority: Normal
- What this table represents: Daily snapshot of distinct application counts attributed to the VS Code source over a rolling 28-day window.
  - Aggregated (not raw events). Zero rows for a date imply no data ingested/attributed for that day.
- Freshness expectations: Daily materialization; queries often use Date >= startofday(ago(28d)). Ingestion timing is not included (no DataIngestTimestamp in this table).
- When to use:
  - Trend VS Code-attributed distinct app counts over the last 28 days.
  - Break down volume by user_source when comparing channels.
  - Join with other 28-day aggregates on Date for multi-metric dashboards.
- When to avoid:
  - Per-session or per-user analysis (it’s aggregate-only).
  - Interpreting Date as precise event time; use it as an aggregation bucket.
  - Mixing this VS Code-specific table with CLI/total tables without normalizing user_source.
- Similar tables & how to choose:
  - unique_app_count_28d_cli, unique_app_count_28d_total: choose based on channel scope (CLI vs VSCode vs total).
  - unique_app_count_28d_assessed/assessreport: use those for specific funnel stages.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column          | Type     | Description or meaning |
  |-----------------|----------|------------------------|
  | dcount_AppId    | long     | Distinct app IDs counted for the day over a rolling 28-day window (VS Code channel). |
  | Date            | datetime | Aggregation day bucket; use startofday filters for rolling windows. |
  | user_source     | string   | Attribution channel (e.g., 'vscode'); queries filter isnotempty(user_source). |

- Column Explain:
  - Date: primary time bucket for trending; filter with startofday(ago(28d)).
  - user_source: use in where/isnotempty and to produce per-channel breakdowns.
  - dcount_AppId: main metric to visualize distinct app volume.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').unique_app_count_28d_vscode
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize sum(dcount_AppId) by startofday(Date), user_source
  | order by startofday_Date asc
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').unique_app_count_28d_assessed
- Priority: Normal
- What this table represents: Daily snapshot of distinct apps that have entered “assessed” stage over a rolling 28-day window.
  - Aggregate; a row per day/user_source. Use DataIngestTimestamp to select the latest snapshot for the day.
- Freshness expectations: Daily; includes DataIngestTimestamp to support arg_max.
- When to use:
  - Count assessed apps by day/channel.
  - Select latest per-day value using arg_max(DataIngestTimestamp, dcount_AppId).
- When to avoid:
  - Using raw counts without arg_max when multiple ingests per day exist.
- Similar tables & how to choose:
  - unique_app_count_28d_assessreport: assessed report completion stage.
  - unique_app_count_28d_vscode/cli/total: channel-level vs stage specificity.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
  - Use arg_max by startofday(Date), user_source
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_AppId         | long     | Distinct app count in assessed stage for that day. |
  | Date                 | datetime | Aggregation day bucket. |
  | user_source          | string   | Attribution channel of assessed activity. |
  | DataIngestTimestamp  | datetime | Ingestion time; use arg_max to select latest per day. |

- Column Explain:
  - DataIngestTimestamp: critical for resolving multiple ingests per day via arg_max.
  - dcount_AppId: stage-specific app volume metric.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').unique_app_count_28d_assessed
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').unique_app_count_28d_assessreport
- Priority: Normal
- What this table represents: Daily snapshot of distinct apps reaching “assessment report” stage over a rolling 28-day window.
- Freshness expectations: Daily; supports arg_max via DataIngestTimestamp.
- When to use:
  - Track assessed report completions by day/channel.
  - Plot funnel progression from assessed to assessreport.
- When to avoid:
  - Inferring raw event timing; this is an aggregate snapshot.
- Similar tables & how to choose:
  - unique_app_count_28d_assessed: earlier stage.
  - unique_app_count_28d_vscode/total: non-stage-specific counts.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_AppId         | long     | Distinct apps with assessment reports for the day. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |
  | DataIngestTimestamp  | datetime | Ingestion time; choose latest via arg_max. |

- Column Explain:
  - Use arg_max(DataIngestTimestamp, dcount_AppId) to get the latest daily value.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').unique_app_count_28d_assessreport
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, dcount_AppId) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_assess
- Priority: Normal
- What this table represents: Daily snapshot of distinct users/devices participating in “assess” stage over a rolling 28-day window.
- Freshness expectations: Daily; includes DataIngestTimestamp.
- When to use:
  - Measure assess-stage adoption by users/devices.
  - Use arg_max per day to avoid multiple ingests.
- When to avoid:
  - Treating dcount_DevDeviceId as unique human users without validation; it’s device-based.
- Similar tables & how to choose:
  - users_count_28d_assessreport: later stage.
  - users_count_28d_migrationplan/buildfix/adoption: different activities.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct developer device IDs for the day. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |
  | DataIngestTimestamp  | datetime | Ingestion time; select latest via arg_max. |

- Column Explain:
  - dcount_DevDeviceId: proxy for user engagement; device-level uniqueness may overcount users with multiple devices.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_assess
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, dcount_DevDeviceId) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_assessreport
- Priority: Normal
- What this table represents:
  - Distinct users/devices who completed assessment reports, per day, 28-day rolling window.
  - Distinct users/devices completing assessment reports per day, 28-day window.
- Freshness expectations: Daily; includes DataIngestTimestamp.
- When to use:
  - Later-stage user adoption tracking.
  - Funnel conversion analysis from assess to assessreport.
  - Report-completion engagement tracking and funnel conversion.
- When to avoid:
  - Assuming human-user granularity; it is device-based.
  - Inferring human-unique users from device-based counts.
- Similar tables & how to choose:
  - users_count_28d_assess for earlier stage.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct devices completing assessment reports. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |
  | DataIngestTimestamp  | datetime | Ingestion time; use arg_max per day. |

- Column Explain:
  - Use arg_max on DataIngestTimestamp to ensure the latest daily value is selected.
  - dcount_DevDeviceId: distinct device count for report completion.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_assessreport
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, dcount_DevDeviceId) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_migrationplan
- Priority: Normal
- What this table represents: Distinct users/devices associated with migration plan activities, daily, 28-day window.
- Freshness expectations: Daily; no DataIngestTimestamp column in schema. Use Date as canonical bucket.
- When to use:
  - Track planning-stage engagement by channel.
  - Join with buildfix/migration execution counts for funnel analytics.
- When to avoid:
  - Attempting arg_max on ingestion (timestamp not present).
- Similar tables & how to choose:
  - users_count_28d_buildfix (build activity), users_count_28d_migration (execution activity).
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct device IDs engaged in planning. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |

- Column Explain:
  - dcount_DevDeviceId: main metric; use startofday(Date) for windows.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_migrationplan
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize sum(dcount_DevDeviceId) by day = startofday(Date), user_source
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_buildfix
- Priority: Normal
- What this table represents: Distinct users/devices performing build-fix activities, daily, 28-day window.
- Freshness expectations: Daily; no ingest timestamp. Use Date bucket directly.
- When to use:
  - Track build-fix adoption over time by channel.
- When to avoid:
  - Assuming raw event granularity; this is aggregated.
- Similar tables & how to choose:
  - users_count_28d_migrationplan (planning), sessions_count_28d_buildfix (sessions rather than distinct users).
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct devices engaged in build-fix. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution (e.g., 'vscode', 'cli'). |

- Column Explain:
  - dcount_DevDeviceId: user engagement count; pair with sessions table for activity intensity.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_buildfix
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize sum(dcount_DevDeviceId) by day = startofday(Date), user_source
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').sessions_count_28d_assessreport
- Priority: Normal
- What this table represents: Total sessions for the assessment report stage per day, 28-day window.
- Freshness expectations: Daily; includes DataIngestTimestamp for snapshot disambiguation.
- When to use:
  - Quantify activity intensity (sessions) for assess report stage.
  - Combine with users_count to derive sessions-per-user ratios.
- When to avoid:
  - Using sessions as a proxy for distinct users.
- Similar tables & how to choose:
  - sessions_count_28d_assess (earlier stage), sessions_count_28d_buildfix/codeRemediation for other activities.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | count_               | long     | Session count for the stage/day. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Attribution channel. |
  | DataIngestTimestamp  | datetime | Ingestion time; use arg_max for latest daily snapshot. |

- Column Explain:
  - count_: intensity metric; pair with distinct user/device counts to avoid misinterpretation.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').sessions_count_28d_assessreport
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTimestamp, count_) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').sessions_count_28d_assess
- Priority: Normal
- What this table represents: Total sessions for the assess stage per day, 28-day window.
- Freshness expectations: Daily; includes two ingestion timestamp variants (DataIngestTimestamp and DataIngestTimeStamp). Prefer a coalesce to handle both.
- When to use:
  - Assess-stage session intensity trends by channel.
- When to avoid:
  - Assuming only one ingestion timestamp field—handle both cases safely.
- Similar tables & how to choose:
  - sessions_count_28d_assessreport (later stage), sessions_count_28d_buildfix/codeRemediation for other activities.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | count_               | long     | Session count for the stage/day. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Attribution channel. |
  | DataIngestTimestamp  | datetime | Ingestion timestamp (variant 1). |
  | DataIngestTimeStamp  | datetime | Ingestion timestamp (variant 2, casing difference). |

- Column Explain:
  - Use coalesce(DataIngestTimestamp, DataIngestTimeStamp) in arg_max to get robust latest snapshot.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').sessions_count_28d_assess
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(coalesce(DataIngestTimestamp, DataIngestTimeStamp), count_) by user_source, day = startofday(Date)
  ```

---

### Table name: cluster('https://ama4j.westus2.kusto.windows.net/').database('bi').users_count_28d_adoption
- Priority: Normal
- What this table represents: Distinct users/devices demonstrating “adoption” activity per day, 28-day window.
- Freshness expectations: Daily; includes DataIngestTime (note the name; different from DataIngestTimestamp).
- When to use:
  - Adoption-focused usage tracking in the migration funnel.
- When to avoid:
  - Assuming DataIngestTime equals event time; treat as ingestion timestamp.
- Similar tables & how to choose:
  - users_count_28d_migration/execute/buildfix when focusing on other funnel steps.
- Common Filters:
  - Date >= startofday(ago(28d))
  - isnotempty(user_source)
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | dcount_DevDeviceId   | long     | Distinct devices exhibiting adoption behavior. |
  | Date                 | datetime | Aggregation day. |
  | user_source          | string   | Channel attribution. |
  | DataIngestTime       | datetime | Ingestion timestamp field for daily snapshot. |

- Column Explain:
  - DataIngestTime: use in arg_max per day if multiple ingests occur.

- Example usage:
  ```kusto
  cluster('https://ama4j.westus2.kusto.windows.net/')
  .database('bi').users_count_28d_adoption
  | where isnotempty(user_source)
  | where Date >= startofday(ago(28d))
  | summarize arg_max(DataIngestTime, dcount_DevDeviceId) by user_source, day = startofday(Date)
  ```

---

## Notes and patterns for all tables above
- All tables are aggregate snapshots keyed by Date and user_source; do not treat them as raw events.
- Time handling:
  - Use Date >= startofday(ago(28d)) for 28-day window queries.
  - When tables have an ingest timestamp column, select latest daily snapshot via arg_max.
  - Timezone/freshness is undocumented; avoid using current-day partial data for critical reporting.
- Channel attribution:
  - user_source distinguishes the channel (e.g., 'vscode', 'cli'); always filter isnotempty(user_source) when needed.
- Joining and comparisons:
  - Join on Date and user_source to combine metrics (e.g., users and sessions).
  - Normalize by channel before comparing metrics across different activity tables.
- Anti-patterns:
  - Summing snapshots from different channels without user_source alignment.
  - Using device-based distinct counts as exact human user counts without caveats.
  - Ignoring ingest timestamp fields when multiple daily snapshots can exist.