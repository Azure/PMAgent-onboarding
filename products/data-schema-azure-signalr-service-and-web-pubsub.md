# Azure SignalR Service and Web PubSub - Product and Data Overview Template

## 1. Product Overview

Azure SignalR Service (ASRS) and Azure Web PubSub (AWPS) are managed real-time messaging services for building WebSocket-based and publish/subscribe applications. This schema enables PMAgent to interpret and query product-specific data for OKR, ARR/revenue proxies, usage (connections/messages), service-type growth, feature tracking, subscription/customer counts, retention, QoS, and top customers across both SignalR and Web PubSub.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
Azure SignalR Service and Web PubSub
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples might include: ASRS, SignalR, Web PubSub, AWPS.
- **Kusto Cluster**:
signalrinsights.eastus2
- **Kusto Database**:
SignalRBI
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

## Overview
Product: Azure SignalR Service and Web PubSub

Power BI (Power Query M) blocks querying Azure Data Explorer (Kusto) for OKR, ARR/revenue, usage (connections/messages), service-type growth, feature tracking, subscription/customer counts, retention, QoS, and top customers across SignalR and Web PubSub.

Primary cluster/database:
- Cluster: signalrinsights.eastus2
- Database: SignalRBI

Alternate sources referenced: armprodgbl.eastus (Requests, HttpIncomingRequests) and ddtelinsights (WebTools_Raw).



## Conventions & Assumptions

### Time semantics
- Observed time columns:
  - Date: primary time column in daily fact tables (e.g., BillingUsage_Daily, FeatureTrack*_Daily, Runtime*Daily).
  - TimeStamp: primary time column in snapshot/pre-aggregated tables (e.g., Cached_*_Snapshot, OKR tables).
- Canonical Time Column
  - Use TimeCol throughout, and alias at source:
    ```kusto
    // Daily facts
    BillingUsage_Daily
    | project-rename TimeCol = Date
    ```
    ```kusto
    // Snapshots/pre-aggregates
    Cached_ZnOKRARR_Snapshot
    | project-rename TimeCol = TimeStamp
    ```
- Typical windows and binning
  - Daily facts: where Date between startofday(ago(30d)) .. startofday(ago(1d))
  - Snapshots: where TimeStamp between startofday(ago(180d)) .. startofday(ago(1d))
  - Bins: bin(TimeCol, 1d), bin(TimeCol, 7d), bin(TimeCol, 1mo)
- Timezone
  - Not specified; assume UTC. If local-time alignment is required, convert explicitly with datetime_add() or startof{day|week|month}(TimeCol, 1h).

### Freshness & Completeness Gates
- Ingestion cadence is largely batch (daily/weekly/monthly). Lag is unknown (plan for 24–48h).
- Do not rely on today’s partial data. Prefer an effective end time of startofday(ago(1d)).
- Multi-slice completeness gate (example: require both global and EU shards present):
  ```kusto
  let last_complete_day = 
    union withsource="Shard" FeatureTrackV2_Daily, FeatureTrackV2_EU_Daily
    | summarize Rows=dcount(ResourceId) by Shard, Date
    | summarize ShardsWithData=dcountif(Shard, Rows > 0) by Date
    | where ShardsWithData >= 2  // require both shards
    | summarize gate = max(Date)
    | project gate;
  // Apply gate to any downstream daily facts:
  FeatureTrackV2_Daily
  | join kind=inner (last_complete_day) on $left.Date <= $right.gate
  ```
- When unknown, use last complete week/month:
  - Week: where TimeStamp <= startofweek(ago(1w))
  - Month: where TimeStamp <= startofmonth(ago(1mo))

### Joins & Alignment
- Frequent keys
  - SubscriptionId (primary subscription join key)
  - ResourceId (ARM resource path; used to classify service type)
  - Date/TimeStamp (time alignment)
  - SKU (pricing tier in billing facts)
- Typical join kinds
  - inner for restricting to a cohort/index
  - leftouter to enrich facts with dimensions (SubscriptionMappings)
  - fullouter used when joining to a goal datatable to preserve both series
- Post-join hygiene
  - Resolve duplicates and standardize columns:
    ```kusto
    T1
    | join kind=leftouter T2 on SubscriptionId
    | project-away SubscriptionId1
    | project-rename CustomerType = CustomerType1, SegmentName = SegmentName1
    ```
  - Prefer coalesce() when multiple potential sources for a field exist.

### Filters & Idioms
- Common predicates
  - Exact set filters: in()/!in()
  - Service classification by substring: has/contains on ResourceId
- Cohort construction
  - Build allow/deny lists, then inner join:
    ```kusto
    let AllowedSubs = datatable(SubscriptionId:string)[ /* ...ids... */ ];
    BillingUsage_Daily
    | join kind=inner AllowedSubs on SubscriptionId
    ```
- Default exclusions
  - Internal subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  - Message-count SKUs (when focusing on service-level revenue): SKU !in ('MessageCount', 'MessageCountPremium')

### Cross-cluster/DB & Sharding
- Qualification pattern:
  ```kusto
  cluster("signalrinsights.eastus2").database("SignalRBI").BillingUsage_Daily
  ```
- Same-schema shards (e.g., FeatureTrackV2_Daily and FeatureTrackV2_EU_Daily)
  - union → normalize keys/time → dedupe → summarize (in this order)
  ```kusto
  union FeatureTrackV2_Daily, FeatureTrackV2_EU_Daily
  | project-rename TimeCol = Date
  | summarize arg_max(TimeCol, *) by ResourceId, TimeCol
  | summarize DistinctResources=dcount(ResourceId) by TimeCol
  ```

### Table classes
- Fact: Event/daily facts (BillingUsage_Daily, FeatureTrack*_Daily, Runtime*Daily)
  - Use for bottom-up aggregations, revenue proxy, fine-grained slicing.
- Snapshot: Latest state (RPSettingLatest) or time-stamped snapshots (OKR, retention snapshots)
  - Use for current config or KPI points; avoid mixing with facts unless you align granularity.
- Pre-aggregated/Cached: KPI/OKR rollups (Cached_*_Snapshot)
  - Use for OKR dashboards and fast trend charts; do not down-grain.



## Entity & Counting Rules (Core Definitions)

- Entity model
  - Resource (ResourceId) → Subscription (SubscriptionId) → Customer/Segment (via SubscriptionMappings)
- Keys
  - Resource: ResourceId
  - Subscription: SubscriptionId
  - Customer/Segment: derived by joining to SubscriptionMappings (CustomerType, SegmentName)
- Service-type classification
  - isAsrs = ResourceId has 'microsoft.signalrservice/signalr'
  - isAwps = ResourceId has 'microsoft.signalrservice/webpubsub'
- Revenue proxy (from BillingUsage_Daily)
  - Use placeholders for unit prices. Example:
    ```kusto
    extend IncomePerUnit = case(
      SKU == 'Free', 0.0,
      SKU == 'Standard', <UnitPrice_Standard>,
      SKU == 'Premium', <UnitPrice_Premium>,
      <UnitPrice_Default>)
    | extend Income = IncomePerUnit * Quantity
    ```
- Counting Do/Don’t
  - Do aggregate facts to the target grain before joining to snapshots.
  - Don’t mix daily facts with weekly/monthly snapshots without resampling (bin to 7d/1mo).
  - Do exclude internal/test subscriptions by default for ARR/OKR reporting.



## Canonical Tables
Scope
- Cluster: cluster("signalrinsights.eastus2"), Database: database("SignalRBI") unless otherwise noted.
- Many tables are “Daily” rollups or “Snapshot” aggregates used by Power BI. Timezone and exact refresh cadence are unknown; expect daily/weekly/monthly pipelines with possible 24–48h delay. Avoid relying on today() data; default to ago(2d) or last complete period.
- Internal subscriptions are commonly excluded via a function/constant like SignalRTeamInternalSubscriptionIds. Join to SubscriptionMappings to enrich CustomerType/SegmentName.

Schema note
- Full schemas could not be programmatically retrieved here. Use the following in Kusto to inspect any table before writing queries:
  - <cluster("signalrinsights.eastus2").database("SignalRBI").TableName> | getschema

---

### BillingUsage_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Daily billing and usage facts at resource/subscription level. Fact table; zero rows for a day usually means no billable usage for that slice (or data not refreshed).
- Freshness expectations: Daily batch. Use date windows on completed days (e.g., where Date <= startofday(ago(1d))).
- When to use / When to avoid:
  - Use for revenue/ARR proxy, usage-based income estimates, SKU mix (Free/Standard/Premium), subscription-level aggregation.
  - Use to separate SignalR vs Web PubSub by inspecting ResourceId path.
  - Avoid for near real-time metrics (use ResourceMetrics or runtime tables).
  - Avoid mixing with snapshot OKR tables without aligning time grain and definitions.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueWeekly/Monthly_Snapshot: pre-aggregated revenue estimates; use for OKR dashboards when you need weekly/monthly rollups.
  - ResourceMetrics: runtime metrics (connections/messages), not a billing fact.
- Common Filters:
  - Date: where Date between startofday(ago(Nd)) .. startofday(ago(1d))
  - SKU: filter out message-count SKUs when focusing on service-level revenue (SKU !in ('MessageCount','MessageCountPremium') in example usage).
  - SubscriptionId: exclude internal via SignalRTeamInternalSubscriptionIds; join to SubscriptionMappings.
  - ResourceId: to classify service type (SignalR vs Web PubSub).
- Table columns:
  | Column        | Type      | Description or meaning |
  |---------------|-----------|------------------------|
  | Date          | datetime  | Usage day (reporting date) |
  | SKU           | string    | Pricing tier (e.g., Free, Standard, Premium, MessageCount, MessageCountPremium) |
  | SubscriptionId| string    | Azure subscription identifier; used for joins and internal-exclusion filters |
  | ResourceId    | string    | ARM resource ID; used to infer service type (SignalR vs Web PubSub) |
  | Quantity      | real      | Usage/billable quantity for the SKU on that day |
- Column Explain:
  - Date: primary time filter for daily rollups.
  - SKU: used to compute income multipliers; common case mapping Free→0; Standard/Premium→per-unit rates.
  - SubscriptionId: join key to SubscriptionMappings; use to group by customer/segment.
  - ResourceId: detect isAsrs/isAwps via string contains of provider path.
  - Quantity: base measure for revenue/consumption calculations.

---

### ResourceMetrics (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Runtime metrics facts (e.g., connection counts, message counts) by resource/role/time. Fact table; zero rows might indicate no activity or missing pipeline for that interval.
- Freshness expectations: Unknown; treat as batch-updated. Prefer complete intervals (hour/day) depending on its grain.
- When to use / When to avoid:
  - Use for connection/message trends and operational usage KPIs.
  - Use to identify top customers by runtime usage (after join to SubscriptionMappings).
  - Avoid for billing/ARR; use BillingUsage_Daily.
- Similar tables & how to choose:
  - RuntimeTransport_*/RuntimeRequestsGroups_*: deeper runtime breakdowns; choose those for transport/request-level analyses.
- Common Filters:
  - Time column (often Date/TimeStamp); Role/ResourceId; SubscriptionId via join; service type via ResourceId parsing.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Schema not retrieved here; expect time, resource/role keys, metric name/value columns |
- Column Explain:
  - Use time and role/resource keys to group/summarize; join to SubscriptionMappings for customer context.

---

### SubscriptionMappings (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Lookup/dimension mapping subscriptions to customer metadata for business reporting.
- Freshness expectations: Unknown; snapshot/slow-changing.
- When to use / When to avoid:
  - Use to enrich facts (BillingUsage_Daily, ResourceMetrics) with CustomerType and SegmentName.
  - Use to filter external/billable vs internal/test.
  - Avoid standalone usage for counts; always join to facts for time series.
- Similar tables & how to choose:
  - CustomerModel: broader customer attributes; use it if you need customer-level modeling beyond subscriptions.
- Common Filters:
  - SubscriptionId equality joins; CustomerType, SegmentName group-bys.
- Table columns:
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | SubscriptionId | string   | Join key to facts |
  | CustomerType   | string   | Customer classification (e.g., External/Billable vs Internal) |
  | SegmentName    | string   | Business segment name for reporting |
- Column Explain:
  - SubscriptionId: mandatory join key.
  - CustomerType/SegmentName: primary slice dimensions for OKR/ARR reporting.

---

### Cached_TopSubscriptions_Snapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Cached snapshot of “top” subscriptions by a metric (revenue/usage). Aggregate snapshot.
- Freshness expectations: Unknown; likely daily/weekly refresh.
- When to use / When to avoid:
  - Use for Top N customer reports without recomputing heavy joins.
  - Avoid if you need custom ranking logic; compute from BillingUsage_Daily/ResourceMetrics.
- Similar tables & how to choose:
  - Cached_SubsTotalWeekly/Monthly_Snapshot: use those for period totals instead of top lists.
- Common Filters:
  - TimeStamp/Date (if present), limit to recent period; filter by service type if available.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Snapshot schema not retrieved here |
- Column Explain:
  - Expect subscription keys and ranking metrics; verify with getschema before use.

---

### FeatureTrack_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Daily feature adoption facts (e.g., replicas, auto-scale, blazor-server).
- Freshness expectations: Daily rollup; lag unknown.
- When to use / When to avoid:
  - Use to track daily adoption of specific features across resources.
  - Avoid for EU-only coverage; consider FeatureTrackV2_EU_Daily.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily: newer schema; prefer v2 when both exist.
  - FeatureTrackV2_EU_Daily: EU shard; union with v2 for global view.
  - FeatureTrack_AutoScale_Daily: specific to autoscale tracking.
- Common Filters:
  - Date, ResourceId/Role, Feature flags, SubscriptionId via join.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Expect Date plus feature indicator columns |
- Column Explain:
  - Use Date + feature columns to compute adoption trends; join to SubscriptionMappings for segmentation.

---

### FeatureTrackV2_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Improved daily feature tracking (superset/cleaned schema vs v1).
- Freshness expectations: Daily; lag unknown.
- When to use / When to avoid:
  - Use preferentially over v1 to leverage stable schema and EU sharding alignment.
- Similar tables & how to choose:
  - Union with FeatureTrackV2_EU_Daily for full coverage.
- Common Filters:
  - Date, ResourceId/Role, feature columns; join to SubscriptionMappings.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Use getschema; expect Date, ResourceId, feature columns |
- Column Explain:
  - Date and feature columns drive adoption counts; ResourceId distinguishes ASRS vs AWPS.

---

### FeatureTrackV2_EU_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: EU subset/shard of FeatureTrackV2_Daily.
- Freshness expectations: Daily; lag unknown.
- When to use / When to avoid:
  - Use when EU compliance/coverage is required.
  - Avoid double counting; union with non-EU v2 only after dedupe keys.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily: non-EU or global shard.
- Common Filters:
  - Date, regional filters (if present), ResourceId/Role.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | EU shard schema |
- Column Explain:
  - Ensure union keys align with v2 global.

---

### FeatureTrack_AutoScale_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Daily autoscale-related feature usage facts.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use for autoscale adoption and trends.
  - Avoid for non-autoscale features (use FeatureTrackV2*).
- Similar tables & how to choose:
  - FeatureTrack_Daily/FeatureTrackV2_Daily for broader features.
- Common Filters:
  - Date, ResourceId, autoscale indicators.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Autoscale-specific columns |
- Column Explain:
  - Use indicator columns to compute adoption rate by segment.

---

### RPSettingLatest (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Latest resource provider settings snapshot per resource.
- Freshness expectations: Snapshot, updated on change/batch; exact cadence unknown.
- When to use / When to avoid:
  - Use to understand current configuration state by resource.
  - Avoid for historical trends (use daily feature tracks).
- Similar tables & how to choose:
  - FeatureTrack* for historical enablement states.
- Common Filters:
  - ResourceId; SubscriptionId; configuration flags.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Latest settings per resource |
- Column Explain:
  - Join to facts for “config vs usage” analyses.

---

### ConnectionMode_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Daily rollup of connection modes (e.g., service/client modes, transport mix).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to analyze connection mode trends, e.g., WebSockets vs fallback.
  - Avoid for per-request deep breakdown (use RuntimeTransport_*).
- Similar tables & how to choose:
  - RuntimeTransport_* for transport-level request analytics.
- Common Filters:
  - Date, ResourceId/Role, Mode/Transport columns.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Expect Date + mode/transport fields |
- Column Explain:
  - Mode fields define the slice; use with Date grouping.

---

### CustomerModel (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Customer classification/enrichment model (billable/external, AI customers, etc.).
- Freshness expectations: Snapshot/batch; cadence unknown.
- When to use / When to avoid:
  - Use to identify External/Billable, AI customer growth segments.
  - Avoid as a fact; use to enrich other tables.
- Similar tables & how to choose:
  - SubscriptionMappings: subscription-focused; CustomerModel may be customer/tenant-level.
- Common Filters:
  - Customer identifiers; segment labels.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Customer-level attributes |
- Column Explain:
  - Use to filter to billable/AI cohorts in OKR analyses.

---

### RuntimeResourceTags_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Daily snapshot of resource tags for runtime reporting.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to segment resources by tags (environment, owner) in usage/revenue analysis.
  - Avoid for current-only config (use RPSettingLatest).
- Similar tables & how to choose:
  - RPSettingLatest: config; this one is tags.
- Common Filters:
  - Date, ResourceId; specific tag keys (dynamic).
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Expect Date, ResourceId, Tags (dynamic) |
- Column Explain:
  - Use bag_unpack on Tags to materialize keys for filtering.

---

### Cached_SubsTotalWeekly_Snapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Weekly pre-aggregated subscription totals (counts/revenue proxies) for OKR dashboards.
- Freshness expectations: Weekly; exact roll day unknown.
- When to use / When to avoid:
  - Use for weekly OKR trend lines without heavy aggregation.
  - Avoid mixing with daily facts without aligning grain.
- Similar tables & how to choose:
  - Cached_SubsTotalMonthly_Snapshot for monthly view.
- Common Filters:
  - Week ending TimeStamp; segment filters via joined dims.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Weekly snapshot fields |
- Column Explain:
  - TimeStamp is key for weekly series.

---

### Cached_SubsTotalMonthly_Snapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: High
- What this table represents: Monthly pre-aggregated subscription totals.
- Freshness expectations: Monthly; lag unknown.
- When to use / When to avoid:
  - Use for monthly OKR/KPI.
  - Avoid for daily analyses.
- Similar tables & how to choose:
  - Weekly snapshot for weekly cadence.
- Common Filters:
  - Month TimeStamp; segment filters.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Monthly snapshot fields |
- Column Explain:
  - Use start/end of month alignment when joining.

---

### Cached_ZnOKRARR_Snapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Cached OKR ARR snapshot; joined with a goal datatable in PBI snippets.
- Freshness expectations: Snapshot; cadence unknown.
- When to use / When to avoid:
  - Use for ARR OKR charting against goals.
  - Avoid for raw revenue computation; use BillingUsage_Daily.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueWeekly/Monthly_Snapshot for periodized revenue estimates.
- Common Filters:
  - TimeStamp.
- Table columns:
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | TimeStamp  | datetime | Snapshot time key |
  | (others)   |          | Inspect with getschema |
- Column Explain:
  - TimeStamp to align with goal series.

---

### Cached_ZnOKREstRevenueWeekly_Snapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Weekly estimated revenue snapshot for OKR.
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use for weekly revenue trends.
  - Avoid mixing with daily BillingUsage_Daily without resampling.
- Common Filters: TimeStamp/week.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | TimeStamp | datetime | Week key |
  | (others) | | Inspect with getschema |
- Column Explain:
  - Often used directly in PBI as a source.

---

### Cached_ZnOKREstRevenueMonthly_Snapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Monthly estimated revenue snapshot.
- Freshness expectations: Monthly.
- When to use / When to avoid:
  - Use for monthly OKR revenue.
- Common Filters: Month TimeStamp.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | TimeStamp | datetime | Month key |
  | (others) | | Inspect with getschema |

---

### Cached_ZnOKRSubs_Snapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: OKR subscription counts snapshot; often compared to goal series in PBI.
- Freshness expectations: Snapshot.
- When to use / When to avoid:
  - Use for subscription OKR against goals.
- Common Filters: TimeStamp.
- Table columns:
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Snapshot time |
  | (others)  |          | Inspect with getschema |

---

### OKRv2021 (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Historical OKR dataset for 2021 variant.
- Freshness expectations: Historical/static.
- When to use / When to avoid:
  - Use for back-compat trending.
  - Avoid for current OKRs; use current cached snapshots.
- Table columns:
  | Column | Type | Description or meaning |
  |--------|------|------------------------|
  | (inspect with getschema) | | Historical OKR fields |

---

### Cached_CuOKRConsumption_Snapshot / Weekly / Monthly (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: Cached consumption OKR snapshots at different grains (daily snapshot, weekly, monthly).
- Freshness expectations: As per suffix.
- When to use / When to avoid:
  - Use for OKR consumption reporting without heavy joins.
  - Avoid mixing grains.
- Common Filters: TimeStamp.
- Table columns: Inspect with getschema.

---

### Cached_ZnOKRSubsWeekly_Snapshot / Monthly (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: Weekly/Monthly subscription OKR snapshots.
- Freshness expectations: As per suffix.
- Common Filters: TimeStamp.
- Table columns: Inspect with getschema.

---

### KPIv2019 (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Legacy KPI dataset.
- Freshness expectations: Historical/static.
- When to use: Legacy comparisons; avoid for current KPI.

- Table columns: Inspect with getschema.

---

### ChurnCustomers_Monthly (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Monthly churn metrics at customer/subscription level.
- Freshness expectations: Monthly.
- When to use: Churn trend, retention analysis.
- Table columns: Inspect with getschema.

---

### ConvertCustomer_Weekly (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Weekly conversion metrics (e.g., free→paid).
- Freshness expectations: Weekly.
- Table columns: Inspect with getschema.

---

### FeedbackSurvey / DeleteSurvey (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: Survey response datasets (general and delete reasons).
- Freshness expectations: Batch-loaded; cadence unknown.
- When to use: Qualitative analysis; correlate with usage.
- Table columns: Inspect with getschema.

---

### SubscriptionRetentionSnapshot / CustomerRetentionSnapshot / ResourceRetentionSnapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: Retention snapshots at different entities.
- Freshness expectations: Periodic snapshots.
- When to use: Cohort/retention analyses.
- Table columns: Inspect with getschema.

---

### Cached_ResourceFlow_Snapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Cached resource flow (e.g., lifecycle transitions).
- Freshness expectations: Snapshot.
- When to use: Resource lifecycle trend.
- Table columns: Inspect with getschema.

---

### OKRv2021_AWPS / OKRv2021_SocketIO (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: OKR datasets specific to Web PubSub (AWPS) and SocketIO variants.
- Freshness expectations: Historical/static or batch.
- When to use: Product-specific OKR tracking.
- Table columns: Inspect with getschema.

---

### KPI_AWPS / KPI_SocketIO (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: KPIs for AWPS and SocketIO.
- Freshness expectations: Batch.
- Table columns: Inspect with getschema.

---

### DeleteSurveyWebPubSub (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What this table represents: Deletion survey specific to Web PubSub.
- Freshness expectations: Batch.
- Table columns: Inspect with getschema.

---

### AwpsRetention_SubscriptionSnapshot / CustomerSnapshot / ResourceSnapshot (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: AWPS-specific retention snapshots by entity.
- Freshness expectations: Periodic.
- Table columns: Inspect with getschema.

---

### SubscriptionFlow_Weekly / Monthly (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: Subscription flows (e.g., new, churn) aggregated weekly/monthly.
- Freshness expectations: As named.
- Table columns: Inspect with getschema.

---

### CustomerFlow_Weekly / Monthly (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Normal
- What these tables represent: Customer flow metrics weekly/monthly.
- Freshness expectations: As named.
- Table columns: Inspect with getschema.

---

### OperationQoS_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Low
- What this table represents: Daily operational QoS metrics.
- Freshness expectations: Daily.
- When to use: Operational health.
- Table columns: Inspect with getschema.

---

### ConnectivityQoS_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Low
- What this table represents: Daily connectivity QoS metrics.
- Freshness expectations: Daily.
- Table columns: Inspect with getschema.

---

### ManageRPQosDaily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Low
- What this table represents: Management plane RP QoS metrics daily.
- Freshness expectations: Daily.
- Table columns: Inspect with getschema.

---

### RuntimeRequestsGroups_Daily / RuntimeRequestsGroups_EU_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Low
- What these tables represent: Daily request metrics at group granularity; EU shard available.
- Freshness expectations: Daily.
- When to use: Group-level request analytics; pick EU for EU-only scope or union with dedupe across shards.
- Table columns: Inspect with getschema.

---

### RuntimeTransport_Daily / RuntimeTransport_EU_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Low
- What these tables represent: Daily transport-level runtime analytics (e.g., WebSocket vs fallback), with EU shard.
- Freshness expectations: Daily.
- When to use: Transport distribution; connection mode analysis.
- Table columns: Inspect with getschema.

---

### AwpsRuntimeRequestsGroups_Daily (cluster("signalrinsights.eastus2")/database("SignalRBI"))
- Priority: Low
- What this table represents: AWPS-specific runtime request group metrics.
- Freshness expectations: Daily.
- Table columns: Inspect with getschema.

---

### WebTools_Raw (cluster("ddtelinsights")/database(unknown))
- Priority: Low
- What this table represents: External telemetry/logs for web tools; cross-cluster source.
- Freshness expectations: Unknown.
- When to use: Ancillary analyses (low priority).
- Common Filters: Time filters; source filters.
- Table columns: Inspect with getschema on the hosting database.

---

### Requests (cluster("armprodgbl.eastus")/database(unknown))
- Priority: Normal
- What this table represents: ARM request logs; cross-cluster source.
- Freshness expectations: Platform-dependent; typically near real-time to daily.
- When to use: Correlate provisioning/management requests with service metrics.
- Common Filters: Time, SubscriptionId, ResourceId, OperationName.
- Table columns: Inspect with getschema on the hosting database.

---

### HttpIncomingRequests (cluster("armprodgbl.eastus")/database(unknown))
- Priority: Normal
- What this table represents: HTTP incoming request telemetry; cross-cluster source.
- Freshness expectations: Platform-dependent.
- When to use: Request patterns, latency, failure rates.
- Common Filters: Time, ResultCode, OperationName.
- Table columns: Inspect with getschema on the hosting database.

---

Guidance and patterns
- Service type classification:
  - isAsrs = ResourceId has 'microsoft.signalrservice/signalr'
  - isAwps = ResourceId has 'microsoft.signalrservice/webpubsub'
- Revenue proxy from BillingUsage_Daily:
  - Map SKU to unit price multipliers (use placeholders like <UnitPrice_Standard>, <UnitPrice_Premium>); Free = 0.
  - Income = case(SKU == 'Free', 0.0, SKU == 'Standard', <UnitPrice_Standard>, SKU == 'Premium', <UnitPrice_Premium>, <UnitPrice_Default>) * Quantity
- Internal exclusion:
  - Filter SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
- Enrichment:
  - Join facts to SubscriptionMappings on SubscriptionId to get CustomerType, SegmentName
- Sharded/region variants:
  - For V2/EU tables, union with dedupe when building global views; standardize keys (Date/ResourceId/Role).
- Conservative defaults:
  - Time windows: last 30 days for daily tables; last 12 weeks/months for weekly/monthly snapshots.
  - Top N: when ranking customers, start with top 50/100 to keep costs predictable.



## Views (Reusable Layers)
No views were provided.



## Query Building Blocks (Copy-paste snippets, with descriptions)

- Time window template
  - Description: Safely bound queries to complete historical data; avoid partial current day.
  - Snippet:
    ```kusto
    // Parameterized window; prefer complete days
    let startDate = startofday(ago(30d));
    let endDate = startofday(ago(1d)); // effective end time (last full day)
    BillingUsage_Daily
    | where Date between (startDate .. endDate)
    ```

- Join template (enrich facts with subscription metadata)
  - Description: Standard enrichment of facts with CustomerType and SegmentName; exclude internal subs.
  - Snippet:
    ```kusto
    let InternalSubs = SignalRTeamInternalSubscriptionIds;
    BillingUsage_Daily
    | where Date between (startofday(ago(30d)) .. startofday(ago(1d)))
    | where SubscriptionId !in (InternalSubs)
    | join kind=leftouter SubscriptionMappings on SubscriptionId
    | project-away SubscriptionId1
    ```

- De-dup pattern
  - Description: Keep the latest record per key/time, or collapse shard duplicates after union.
  - Snippet:
    ```kusto
    union FeatureTrackV2_Daily, FeatureTrackV2_EU_Daily
    | project-rename TimeCol = Date
    | summarize arg_max(TimeCol, *) by ResourceId, TimeCol
    ```

- Important filters
  - Description: Default exclusions and service-type slicing.
  - Snippet:
    ```kusto
    // Exclude message-count SKUs when focusing on service-level income proxy
    | where SKU !in ('MessageCount','MessageCountPremium')

    // Service-type flags (ASRS vs AWPS)
    | extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr',
             isAwps = ResourceId has 'microsoft.signalrservice/webpubsub'
    ```

- Important definitions: Revenue proxy
  - Description: Convert usage Quantity to income proxy by SKU using placeholders for unit prices.
  - Snippet:
    ```kusto
    | extend UnitPrice = case(
        SKU == 'Free', 0.0,
        SKU == 'Standard', <UnitPrice_Standard>,
        SKU == 'Premium', <UnitPrice_Premium>,
        <UnitPrice_Default>)
    | extend Income = UnitPrice * Quantity
    ```

- ID parsing/derivation
  - Description: Parse identifiers from ARM ResourceId; robust for cohorting when explicit columns are missing.
  - Snippet:
    ```kusto
    // Parse SubscriptionId and Provider/ResourceType from the ARM path
    | parse ResourceId with "/subscriptions/" SubscriptionId:string "/resourceGroups/" ResourceGroup:string "/providers/" Provider:string "/" ResourceType:string "/" ResourceName:string *
    | extend isAsrs = tolower(Provider) has "microsoft.signalrservice" and tolower(ResourceType) == "signalr",
             isAwps = tolower(Provider) has "microsoft.signalrservice" and tolower(ResourceType) == "webpubsub"
    ```

- Sharded union (EU + Global)
  - Description: Merge same-schema regional shards; standardize time and keys; dedupe before summarize.
  - Snippet:
    ```kusto
    let startDate = startofday(ago(30d));
    let endDate = startofday(ago(1d));
    union FeatureTrackV2_Daily, FeatureTrackV2_EU_Daily
    | where Date between (startDate .. endDate)
    | project-rename TimeCol = Date
    | summarize arg_max(TimeCol, *) by ResourceId, TimeCol
    | summarize DistinctResources=dcount(ResourceId) by TimeCol
    ```

- Completeness gate (multi-slice)
  - Description: Identify the last day all shards (or sentinel groups) reported; restrict analysis to that date or earlier.
  - Snippet:
    ```kusto
    let gate =
      union withsource="Shard" FeatureTrackV2_Daily, FeatureTrackV2_EU_Daily
      | summarize Rows=dcount(ResourceId) by Shard, Date
      | summarize ShardsWithData=dcountif(Shard, Rows > 0) by Date
      | where ShardsWithData >= 2
      | summarize gate = max(Date);
    BillingUsage_Daily
    | where Date <= toscalar(gate)
    ```

- Cross-cluster qualification
  - Description: Reference external clusters/databases explicitly when needed.
  - Snippet:
    ```kusto
    cluster("signalrinsights.eastus2").database("SignalRBI").Cached_ZnOKREstRevenueWeekly_Snapshot
    | where TimeStamp between (startofweek(ago(12w)) .. startofweek(ago(1w)))
    ```



## Example Queries (with explanations)

1) Daily revenue proxy by service type (safe window, internal exclusion)
- Description: Computes a daily income proxy from BillingUsage_Daily using SKU-based unit prices (placeholders), excludes internal subscriptions, and splits into ASRS vs AWPS using ResourceId. Adapt by changing startDate/endDate or adding SegmentName group-bys.
```kusto
let startDate = startofday(ago(30d));
let endDate = startofday(ago(1d)); // last full day
let InternalSubs = SignalRTeamInternalSubscriptionIds;
cluster("signalrinsights.eastus2").database("SignalRBI").BillingUsage_Daily
| where Date between (startDate .. endDate)
| where SubscriptionId !in (InternalSubs)
| where SKU !in ('MessageCount','MessageCountPremium')
| extend UnitPrice = case(
    SKU == 'Free', 0.0,
    SKU == 'Standard', <UnitPrice_Standard>,
    SKU == 'Premium', <UnitPrice_Premium>,
    <UnitPrice_Default>)
| extend Income = UnitPrice * Quantity
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr',
         isAwps = ResourceId has 'microsoft.signalrservice/webpubsub'
| summarize Income_Total = sum(Income),
            Income_Asrs = sumif(Income, isAsrs),
            Income_Awps = sumif(Income, isAwps)
  by Date
| order by Date asc
```

2) Monthly revenue proxy trend (resample to month)
- Description: Aggregates BillingUsage_Daily to monthly income proxy. Use bin(Date, 1mo) and the same exclusions. Adapt by extending to SKU splits or joining dims.
```kusto
let startMonth = startofmonth(ago(12mo));
let endMonth = startofmonth(ago(1mo));
let InternalSubs = SignalRTeamInternalSubscriptionIds;
BillingUsage_Daily
| where Date between (startMonth .. endMonth)
| where SubscriptionId !in (InternalSubs)
| where SKU !in ('MessageCount','MessageCountPremium')
| extend UnitPrice = case(
    SKU == 'Free', 0.0,
    SKU == 'Standard', <UnitPrice_Standard>,
    SKU == 'Premium', <UnitPrice_Premium>,
    <UnitPrice_Default>)
| extend Income = UnitPrice * Quantity
| summarize Income_Month = sum(Income) by Month = bin(Date, 1mo)
| order by Month asc
```

3) Top 50 subscriptions by revenue proxy (last 30 days), with customer segmentation
- Description: Calculates income per subscription and brings in CustomerType and SegmentName. Adapt by changing Top N or adding filters for ASRS/AWPS.
```kusto
let startDate = startofday(ago(30d));
let endDate = startofday(ago(1d));
let InternalSubs = SignalRTeamInternalSubscriptionIds;
BillingUsage_Daily
| where Date between (startDate .. endDate)
| where SubscriptionId !in (InternalSubs)
| where SKU !in ('MessageCount','MessageCountPremium')
| extend UnitPrice = case(
    SKU == 'Free', 0.0,
    SKU == 'Standard', <UnitPrice_Standard>,
    SKU == 'Premium', <UnitPrice_Premium>,
    <UnitPrice_Default>)
| extend Income = UnitPrice * Quantity
| summarize Income_Sub = sum(Income) by SubscriptionId
| top 50 by Income_Sub desc
| join kind=leftouter SubscriptionMappings on SubscriptionId
| project SubscriptionId, Income_Sub, CustomerType, SegmentName
| order by Income_Sub desc
```

4) ARR snapshot with monthly goals (OKR-style fullouter with datatable)
- Description: Mirrors the Power BI pattern joining Cached_ZnOKRARR_Snapshot to an in-query goal series. Adapt by editing datatable values or replacing with another goal source.
```kusto
let Goals = datatable(TimeStamp: datetime, SignalRGoal: real, SignalRGrowthGoal: real) [
  datetime(2023-09-30), 22939552, 0.03085,
  datetime(2023-10-31), 23647313, 0.03085,
  datetime(2023-11-30), 24376911, 0.03085,
  datetime(2023-12-31), 25129020, 0.03085,
  datetime(2024-01-31), 25904333, 0.03085,
  datetime(2024-02-29), 26703568, 0.03085,
  datetime(2024-03-31), 27527462, 0.03085
];
Cached_ZnOKRARR_Snapshot
| join kind=fullouter Goals on TimeStamp
| extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
| project-away TimeStamp1
| order by TimeStamp asc
```

5) Subscription OKR snapshot with goals
- Description: Joins cached subscription counts to monthly goal points via fullouter. Adapt by modifying the goal datatable or restricting the window.
```kusto
let Goals = datatable(TimeStamp: datetime, WebPubSubGoal: real, WebPubSubGrowthGoal: real) [
  datetime(2023-09-30), 3305, 0.10449383,
  datetime(2023-10-31), 3650, 0.10449383,
  datetime(2023-11-30), 4031, 0.10449383,
  datetime(2023-12-31), 4453, 0.10449383,
  datetime(2024-01-31), 4918, 0.10449383,
  datetime(2024-02-29), 5432, 0.10449383,
  datetime(2024-03-31), 6000, 0.10449383
];
Cached_ZnOKRSubs_Snapshot
| join kind=fullouter Goals on TimeStamp
| extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
| project-away TimeStamp1
| order by TimeStamp asc
```

6) Global feature adoption: union V2 + EU shards and count distinct resources per day
- Description: Produces a global daily count of distinct resources with any feature-tracked presence by deduping across shards. Adapt by adding feature-specific filters if known.
```kusto
let startDate = startofday(ago(30d));
let endDate = startofday(ago(1d));
union FeatureTrackV2_Daily, FeatureTrackV2_EU_Daily
| where Date between (startDate .. endDate)
| project-rename TimeCol = Date
| summarize arg_max(TimeCol, *) by ResourceId, TimeCol
| summarize ResourcesWithFeatures = dcount(ResourceId) by TimeCol
| order by TimeCol asc
```

7) Tag-based cohorting from RuntimeResourceTags_Daily (environment = prod)
- Description: Materializes dynamic Tags to columns and filters to a specific environment tag. Adapt by changing the tag key/value or joining to BillingUsage_Daily to evaluate revenue by tag.
```kusto
let startDate = startofday(ago(30d));
let endDate = startofday(ago(1d));
RuntimeResourceTags_Daily
| where Date between (startDate .. endDate)
| extend TagsObj = todynamic(Tags)
| evaluate bag_unpack(TagsObj)
| where tostring(Env) == "prod" // replace Env with your tag key if different
| summarize DistinctResources = dcount(ResourceId) by Date
| order by Date asc
```

8) Weekly and monthly revenue snapshots (fast OKR sources)
- Description: Reads pre-aggregated revenue estimates at weekly and monthly grains. Adapt by adding segment joins or restricting ranges.
```kusto
// Weekly
Cached_ZnOKREstRevenueWeekly_Snapshot
| where TimeStamp between (startofweek(ago(12w)) .. startofweek(ago(1w)))
| order by TimeStamp asc
```
```kusto
// Monthly
Cached_ZnOKREstRevenueMonthly_Snapshot
| where TimeStamp between (startofmonth(ago(12mo)) .. startofmonth(ago(1mo)))
| order by TimeStamp asc
```



## Reasoning Notes (only if uncertain)
- Freshness lag is not documented; we assume 24–48h and exclude current day via startofday(ago(1d)).
- ResourceMetrics schema is not provided; we avoided examples that rely on unknown column names.
- FeatureTrack*_Daily column details are not provided; we used union/dedup and counting patterns without asserting specific feature columns. Users should add feature filters after inspecting schema.
- Internal subscription list is referenced as SignalRTeamInternalSubscriptionIds; we treat it as a function/constant available in the database.
- Income unit prices in Power BI snippet included specific numbers; per guidance, we replaced with placeholders (<UnitPrice_Standard>, etc.) to avoid hardcoding and enable reuse.
- Cross-cluster tables (Requests, HttpIncomingRequests, WebTools_Raw) lack schema; we did not include them in examples beyond noting how to qualify clusters.
- Counting rules assume entity hierarchy resource → subscription → customer. If CustomerModel provides non-subscription entities (tenant/customer), prefer joining facts on the best available key (often SubscriptionId) then mapping to customer segments.