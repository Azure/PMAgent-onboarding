# Java App Modernization - Product and Data Overview Template

## 1. Product Overview

> Draft overview for Java App Modernization based on the provided product name. This document initiates onboarding for PMAgent by defining product metadata and embedding the current Kusto Query Playbook to guide future query authoring once telemetry is connected.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
> Java App Modernization
- **Product Nick Names**: 
> **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
> unknown (not provided)
- **Kusto Database**:
> unknown (not provided)
- **Access Control**:
> **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Java App Modernization - Kusto Query Playbook

## Overview
- Product: Java App Modernization
- Summary: No product summary was provided in the source content. Queries, tables, and views are not yet defined; this playbook documents conventions and reusable templates to help author Kusto queries once telemetry is connected.
- Main cluster: unknown (not provided)
- Main database: unknown (not provided)

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns: none provided. Define a Canonical Time Column for the product (placeholder: <TimeColumn>) and alias other raw time columns to it via project-rename when needed.
- Aliasing example:
  ```kusto
  <Table>
  | project-rename <TimeColumn> = <RawTimeColumn>
  ```
- Typical windows and bin:
  - Default windows: recommend conservative windows such as ago(7d), ago(30d) until ingestion freshness is confirmed.
  - Common bin resolutions: bin(<TimeColumn>, 1d), 1h, 5m depending on volume and need.
- Timezone: unknown. Use UTC by default. Avoid using the current day unless completeness is validated.

### Freshness & Completeness Gates
- Ingestion cadence: unknown.
- Current-day completeness: unknown. Recommend using an effective end time of “yesterday” (startOfDay(now()) - 1d) or the last fully surfaced partition.
- Multi-slice completeness gate pattern (sentinel slices like regions/shards):
  ```kusto
  // Gate to determine the latest complete day based on slice count
  let RequiredSlices = 10; // placeholder
  let LatestCompleteDay =
      <FactTable>
      | where <TimeColumn> < startofday(now()) // exclude today
      | summarize SliceCount = dcount(<SliceKey>) by Day = startofday(<TimeColumn>)
      | where SliceCount >= RequiredSlices
      | top 1 by Day desc
      | project Day;
  ```

### Joins & Alignment
- Frequent keys: placeholders (e.g., <EntityId>, <ResourceId>, <SubscriptionId>, <CustomerId>, <Region>).
- Typical join kinds:
  - inner (to enforce membership)
  - innerunique (to prevent multiplicative joins when keys are duplicated)
  - leftouter (to enrich while preserving base set)
- Post-join hygiene:
  - Resolve duplicate columns with project-rename or coalesce():
    ```kusto
    | project-rename <Field> = <Field1>
    | extend <Field> = coalesce(<Field1>, <Field2>)
    ```
  - Drop unused columns to keep results clean:
    ```kusto
    | project-away <UnneededCol1>, <UnneededCol2>
    ```

### Filters & Idioms
- Text predicates:
  - has: token-based match (fast), case-insensitive.
  - contains: substring match, case-insensitive; use with care on large strings.
  - in: membership filters for cohorts.
- Cohort construction:
  - Build allowlist/denylist as a materialized set first, then join kind=inner or filter via in().
- Default filters: none provided. Use placeholders for internal/test exclusions until defined (e.g., <IsInternalFlag> == false, <Environment> != "Test").

### Cross-cluster/DB & Sharding
- Qualified sources:
  ```kusto
  cluster("<ClusterName>").database("<DatabaseName>").<TableName>
  ```
- Union across shards:
  - Normalize keys/time before summarizing.
  - Order matters: union → normalize → filter → summarize.
  ```kusto
  union isfuzzy=true
      cluster("<ClusterA>").database("<Db>").<FactTable>,
      cluster("<ClusterB>").database("<Db>").<FactTable>
  | project <TimeColumn>, <EntityId>, <Region>, <Metric1>, <Metric2>
  | where <TimeColumn> between (ago(30d) .. startofday(now()) - 1d)
  | summarize Count = count() by bin(<TimeColumn>, 1d), <Region>
  ```

### Table classes
- Fact (events/daily slices): use for behavioral counts, time-series, DAU/MAU, aggregations over time windows.
- Snapshot (latest state or periodic snapshots): use for current configuration/state, joins to enrich facts; avoid counting over time with snapshots unless aligned with snapshot cadence.
- Pre-aggregated (KPI/cached): use for dashboards and quick metrics; avoid for granular investigations; verify pre-agg dimensions and roll-up logic before joining.

### Important Mapping
- No tiles/pages ↔ query mapping provided. As dashboards are added, document mappings from tile/page names to the underlying queries and dimensions (e.g., “Deployments by Region” → group by <Region> over <TimeColumn>).

## Entity & Counting Rules (Core Definitions)
- Entity model: not provided. Define unique keys and tiers once telemetry schemas are known (placeholders: <EntityId>, <ParentId>, <SubscriptionId>, <CustomerId>).
- Counting rules:
  - Use fact tables for event counts; align on Canonical Time Column.
  - De-duplication before counting if multiple events per entity per slice.
  - Snapshot counts represent state at specific points; do not mix with fact events without explicit alignment.

## Views (Reusable Layers)
- No views provided in source content. Create views to encapsulate common filters (e.g., completeness gate, allowlist), time alignment, and joins once tables are known.

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Standardized time window with effective end time set to the latest complete day.
  - Snippet:
    ```kusto
    // Time window with effective end time (exclude current day)
    let StartTime = ago(30d);
    let EndTime = startofday(now()) - 1d;
    <FactTable>
    | where <TimeColumn> between (StartTime .. EndTime)
    | summarize Count = count() by bin(<TimeColumn>, 1d)
    ```

- Join template
  - Description: Enrich facts with snapshot attributes using a safe innerunique join and post-join hygiene.
  - Snippet:
    ```kusto
    let StartTime = ago(30d);
    let EndTime = startofday(now()) - 1d;
    let Facts =
        <FactTable>
        | where <TimeColumn> between (StartTime .. EndTime)
        | project <TimeColumn>, <EntityId>, <Metric>;
    let Snap =
        <SnapshotTable>
        | summarize arg_max(<SnapshotTime>, *) by <EntityId> // latest attributes
        | project <EntityId>, <Region>, <AttributeX>;
    Facts
    | join kind=innerunique Snap on <EntityId>
    | project <TimeColumn>, <EntityId>, <Region>, <Metric>, <AttributeX>
    ```

- De-dup patterns
  - Description: Prevent duplicate counting and ensure clean entity-level aggregates.
  - Snippets:
    ```kusto
    // Latest record per entity per day
    <FactTable>
    | summarize arg_max(<TimeColumn>, *) by <EntityId>, Day = startofday(<TimeColumn>)

    // Distinct entity per time bucket
    <FactTable>
    | summarize Entities = dcount(<EntityId>) by bin(<TimeColumn>, 1d)

    // Row-number de-dup within partitions
    <FactTable>
    | sort by <TimeColumn> desc
    | extend rn = row_number(<EntityId>, startofday(<TimeColumn>))
    | where rn == 1
    ```

- Important filters
  - Description: Reusable filters for internal/test exclusions and allowlists.
  - Snippets:
    ```kusto
    // Exclude internal/test data (placeholders)
    | where coalesce(<IsInternalFlag>, false) == false
    | where <Environment> !in ("Test", "Dev")

    // Allowlist cohort
    let Allowlist = datatable(<EntityId>:string)
    [
        "id1", "id2", "id3" // placeholder IDs
    ];
    <FactTable>
    | join kind=inner Allowlist on <EntityId>

    // Denylist filter
    let Denylist = datatable(<EntityId>:string)
    [
        "idX", "idY"
    ];
    <FactTable>
    | where <EntityId> !in (Denylist)
    ```

- Important Definitions
  - Description: Placeholder definitions to be formalized from product queries.
  - Snippets:
    ```kusto
    // "Active" definition (example placeholder)
    let ActiveWindowDays = 30;
    <FactTable>
    | where <TimeColumn> > ago(ActiveWindowDays)
    | summarize ActiveEntities = dcount(<EntityId>)

    // Success/Failure (placeholder predicates)
    <FactTable>
    | extend IsSuccess = <Status> == "Success" // placeholder
    | summarize SuccessRate = 100.0 * sumif(1, IsSuccess) / count()
    ```

- ID parsing/derivation
  - Description: Generic parsing patterns for extracting keys.
  - Snippets:
    ```kusto
    // Regex extract a component from a composite ID
    <FactTable>
    | extend <SubscriptionId> = extract(@"subscriptions/([0-9a-f\-]+)", 1, <ResourceId>)

    // Split path-like key
    <FactTable>
    | extend parts = split(<ResourceId>, "/")
    | extend <Region> = tostring(parts[<Index>]) // placeholder index

    // parse_json for attributes encoded in a column
    <FactTable>
    | extend j = parse_json(<JsonCol>)
    | extend <AttrX> = tostring(j["attrX"])
    ```

- Sharded union
  - Description: Merge same-schema tables from multiple clusters/databases and normalize keys/time.
  - Snippet:
    ```kusto
    union isfuzzy=true
        cluster("<Cluster1>").database("<Db>").<FactTable>,
        cluster("<Cluster2>").database("<Db>").<FactTable>,
        cluster("<Cluster3>").database("<Db>").<FactTable>
    | project <TimeColumn>, <EntityId>, <Region>, <Metric>
    | extend <Region> = tolower(<Region>) // normalize
    | where <TimeColumn> between (ago(30d) .. startofday(now()) - 1d)
    | summarize Count = count(), Entities = dcount(<EntityId>) by bin(<TimeColumn>, 1d), <Region>
    ```

## Example Queries (with explanations)

1) Daily event counts with effective end time
- Description: Counts events per day over the last 30 days, excluding the current day to avoid incomplete data. Adapt by changing the time window or bin size.
```kusto
let StartTime = ago(30d);
let EndTime = startofday(now()) - 1d;
<FactTable>
| where <TimeColumn> between (StartTime .. EndTime)
| summarize Events = count() by Day = bin(<TimeColumn>, 1d)
| order by Day asc
```

2) Active entities in the last 30 days (deduplicated)
- Description: Measures active entities using distinct entity IDs in the last 30 days; deduplication prevents double counting. Adapt by modifying ActiveWindowDays or grouping dimensions.
```kusto
let ActiveWindowDays = 30;
<FactTable>
| where <TimeColumn> > ago(ActiveWindowDays)
| summarize ActiveEntities = dcount(<EntityId>)
```

3) Enrich facts with latest snapshot attributes
- Description: Joins facts with the latest snapshot attributes per entity, using arg_max to pick the most recent snapshot. Adapt by changing attributes or switch to leftouter to keep unmatched facts.
```kusto
let StartTime = ago(14d);
let EndTime = startofday(now()) - 1d;
let Facts =
    <FactTable>
    | where <TimeColumn> between (StartTime .. EndTime)
    | project <TimeColumn>, <EntityId>, <Metric>;
let LatestSnap =
    <SnapshotTable>
    | summarize arg_max(<SnapshotTime>, *) by <EntityId>
    | project <EntityId>, <Region>, <Tier>;
Facts
| join kind=innerunique LatestSnap on <EntityId>
| summarize Total = sum(<Metric>) by bin(<TimeColumn>, 1d), <Region>, <Tier>
```

4) Cross-cluster union and normalization
- Description: Unions multiple shards across clusters, normalizes the region dimension, and aggregates by day and region. Adapt by adding/removing clusters and adjusting normalization rules.
```kusto
union isfuzzy=true
    cluster("<ClusterA>").database("<Db>").<FactTable>,
    cluster("<ClusterB>").database("<Db>").<FactTable>
| project <TimeColumn>, <EntityId>, <Region>, <Metric>
| extend <Region> = tolower(<Region>)
| where <TimeColumn> between (ago(30d) .. startofday(now()) - 1d)
| summarize Events = count(), Entities = dcount(<EntityId>) by bin(<TimeColumn>, 1d), <Region>
| order by <TimeColumn> asc
```

5) Completeness gate for last fully reported day
- Description: Identifies the most recent day with sufficient slice coverage, then uses that day to compute metrics. Adapt gate thresholds and slice keys for your topology.
```kusto
let RequiredSlices = 10; // placeholder
let LatestCompleteDay =
    <FactTable>
    | where <TimeColumn> < startofday(now())
    | summarize SliceCount = dcount(<SliceKey>) by Day = startofday(<TimeColumn>)
    | where SliceCount >= RequiredSlices
    | top 1 by Day desc
    | project Day;
<FactTable>
| where startofday(<TimeColumn>) == toscalar(LatestCompleteDay)
| summarize Events = count(), Entities = dcount(<EntityId>)
```

6) Allowlist cohort analysis
- Description: Restricts analysis to a defined allowlist of entities, useful for pilot cohorts or strategic customers. Adapt by changing the allowlist source to a table or query.
```kusto
let StartTime = ago(30d);
let EndTime = startofday(now()) - 1d;
let Allowlist = datatable(<EntityId>:string) ["id1","id2","id3"];
<FactTable>
| where <TimeColumn> between (StartTime .. EndTime)
| join kind=inner Allowlist on <EntityId>
| summarize Events = count(), Entities = dcount(<EntityId>) by bin(<TimeColumn>, 1d)
```

7) Denylist filtering with post-join hygiene
- Description: Excludes specific entities (e.g., internal/test) and drops unused columns to keep the result clean. Adapt by sourcing the denylist from a table.
```kusto
let Denylist = datatable(<EntityId>:string) ["idX","idY"];
<FactTable>
| where <EntityId> !in (Denylist)
| project <TimeColumn>, <EntityId>, <Metric>
| project-away <DebugCol>, <TempCol>
```

8) Rolling DAU/MAU ratio (placeholder)
- Description: Computes rolling 7-day DAU and 30-day MAU using distinct counts per entity, then calculates DAU/MAU. Adapt windows and entity keys as needed.
```kusto
let EndTime = startofday(now()) - 1d;
let StartTime = EndTime - 60d;
<FactTable>
| where <TimeColumn> between (StartTime .. EndTime)
| summarize by <TimeColumn>, <EntityId>
| summarize
    DAU = dcountif(<EntityId>, <TimeColumn> > EndTime - 7d),
    MAU = dcountif(<EntityId>, <TimeColumn> > EndTime - 30d)
| extend DAU_MAU_Ratio = 1.0 * DAU / iff(MAU == 0, real(null), MAU)
```

## Reasoning Notes (only if uncertain)
- No product summary, cluster, database, tables, views, or queries were provided. To remain accurate:
  1. Canonical Time Column is marked as <TimeColumn> until schemas are known; UTC assumed to avoid timezone errors.
  2. Completeness gating uses a generic slice-count threshold with <SliceKey> placeholder, since shard topology is unknown.
  3. Keys for joins (<EntityId>, <SubscriptionId>, <Region>) are placeholders commonly used in telemetry; these will be replaced by actual columns once available.
  4. Default exclusions (internal/test) are placeholders (<IsInternalFlag>, <Environment>) to illustrate patterns; real predicates must be sourced from product data.
  5. De-dup patterns (arg_max, dcount, row_number) are standard Kusto practices; selection depends on actual event semantics.
  6. Cross-cluster union examples use placeholder clusters/databases to show qualification and normalization steps.
  7. Snapshot enrichment via arg_max assumes a snapshot time column (<SnapshotTime>); actual snapshot cadence must be validated.
  8. DAU/MAU example uses distinct entity counts; entity definition ("user", "resource", "workspace") will be finalized once telemetry schemas are available.
  9. Current-day data is avoided due to unknown freshness; once SLA is known, effective end time rules can be adjusted.
  10. Views section is empty because no reusable layers were provided; creating views will be beneficial once common filters and joins are identified.

## Canonical Tables

No tables, views, or queries were provided in the onboarding content for “Java App Modernization”.
- Cluster: unknown
- Database: unknown
- Query count: 0
- As a result, no canonical tables can be documented at this time.
- Table access status: not accessible. Schema retrieval via get_table_schema is not possible because no tables are listed and the product’s ADX configuration is unknown.

General guidance once data is available:
- Start with the highest-priority tables referenced by real queries; document them first.
- Use conservative time windows (e.g., last 24–72 hours) until you know table freshness.
- Always include tenant/environment filters if the product is multi-tenant.
- For sharded or similarly named tables, prefer union with clear time filters.
- Be cautious with current-day data if freshness or timezone is unknown; specify UTC unless documented otherwise.

When tables become available, document each as follows:

### Table name: <cluster().database().table> (include cluster/db if cross-source)
- Priority: High/Normal/Low
- What this table represents: fact vs. snapshot vs. aggregate; whether zero rows imply inactivity or deletion
- Freshness expectations: daily/hourly/unknown; recommend safe time window and timezone handling
- When to use / When to avoid:
  - Use cases: 3–6 concrete scenarios the product answers with this table
  - Anti-patterns: joins that don’t scale, missing filters, current-day data issues
- Similar tables & how to choose: list sibling tables and union/selection rules
- Common Filters: time range, tenant/subscription/environment, region/service type, status/result codes
- Table columns:
  - Retrieve via get_table_schema and include all columns in a table:

  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | <column1> | <type1> | What it represents; example values if known |
  | <column2> | <type2> | How it’s used in filters/joins |
  | ... | ... | ... |

- Column Explain:
  - Identify the key columns used most often in queries and explain when to use them (e.g., timestamp for time filters, tenant identifiers for scoping, status/result for success/failure classification).

Next steps to populate this playbook:
- Provide the ADX cluster and database, plus at least one query using product tables.
- List tables (with priority) referenced by those queries.
- Once provided, we will fetch exact schemas with get_table_schema and complete the canonical table sections above.