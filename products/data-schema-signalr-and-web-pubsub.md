# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub are Azure real-time messaging services that enable bi-directional communication between clients and servers at scale. This schema document provides PMAgent with the core product/domain context and the Kusto Query Playbook to interpret product-specific data for analytics, OKR reporting, usage insights, QoS monitoring, and customer segmentation.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
SignalR and Web PubSub
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. For example: ASRS, AWPS, SignalR, WebPubSub, Web PubSub.
- **Kusto Cluster**:
signalrinsights.eastus2
- **Kusto Database**:
SignalRBI
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Kusto Query Playbook — SignalR and Web PubSub

## Overview
- Product: SignalR and Web PubSub
- Summary: Power BI report blocks containing KQL for SignalR and Web PubSub metrics including OKR, usage, subscriptions, features, retention, top customers, QoS, VS integration telemetry, and ARM operations across multiple clusters (primarily signalrinsights.eastus2/SignalRBI).
- Primary cluster/database: signalrinsights.eastus2 / SignalRBI
- Alternate sources observed:
  - ddtelinsights (WebTools client telemetry)
  - armprodgbl.eastus (Unionizer function over ARM logs)

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - Date (dominant, daily grain across most fact tables)
  - env_time (OperationQoS_Daily, ConnectivityQoS_Daily)
  - AdvancedServerTimestampUtc (WebTools_Raw)
  - TIMESTAMP (Unionizer)
  - LastUpdated (RPSettingLatest; snapshot attribute, not used as time series)
- Canonical Time Column: Time
  - Alias patterns:
    - From Date: project-rename Time = Date
    - From env_time: project-rename Time = env_time
    - From AdvancedServerTimestampUtc: extend Time = startofday(AdvancedServerTimestampUtc)
    - From TIMESTAMP: extend Time = startofday(TIMESTAMP)
- Typical windows and binning:
  - Daily: Date >= ago(30d) or ago(60d)
  - Weekly: startofweek(Date), often excluding current partial week
  - Monthly: startofmonth(Date), often excluding current partial month
  - Rolling windows for QoS: last known env_time → rolling 7/28-day windows
- Timezone: Not specified in sources; default to UTC. Avoid using “today” unless ingestion boundaries are known.

### Freshness & Completeness Gates
- Ingestion cadence: Not explicitly stated. Daily facts are queried with 30–60 day lookbacks; current day is treated as potentially incomplete.
- Effective end-time patterns observed:
  - “Current” detection:
    ```kusto
    let Current = toscalar(<FactTable> | top 1 by Date desc | project Date);
    ```
  - Region completeness gate (choose last Date where sentinel regions are both present):
    ```kusto
    let EndDate =
      toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
        | summarize counter = dcount(Region) by Date
        | where counter >= 2
        | top 1 by Date desc
        | project Date
      );
    ```
  - Multi-slice completeness (EU+non-EU):
    ```kusto
    let NonEU = BillingUsage_Daily | where Region == 'australiaeast' | top 1 by Date desc | project Date;
    let EU    = BillingUsage_Daily | where Region == 'westeurope'   | top 1 by Date desc | project Date;
    let Current = toscalar(NonEU | union EU | top 1 by Date asc);
    ```
- Recommendation: Prefer closed periods:
  - Daily: use yesterday
  - Weekly: last full week (end before startofweek(now()))
  - Monthly: last full month (end before startofmonth(now()))

### Joins & Alignment
- Frequent keys:
  - SubscriptionId (GUID)
  - ResourceId (full Azure ResourceId; often normalized with tolower())
  - Region
  - SKU
- Activity gating:
  - Join BillingUsage_Daily to MaxConnectionCount_Daily on Date + Role/resource key (normalized to lower case) to include only active resources.
- Typical join kinds:
  - inner: to enforce activity/completeness (e.g., with MaxConnectionCount_Daily)
  - leftouter: to enrich with SubscriptionMappings and RPSettingLatest
  - fullouter: to merge with inline goal datatables
- Post-join hygiene:
  ```kusto
  | project-rename Time = Date
  | project-away <duplicate_column_list>
  | extend ResourceId = tolower(ResourceId)
  | extend Role = tolower(Role)
  | extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
  | extend ServiceMode = iif(isempty(ServiceMode), 'Default', ServiceMode)
  | extend HasConnection = MaxConnectionCount > 0
  ```

### Filters & Idioms
- Service discriminators:
  - SignalR: ResourceId has 'microsoft.signalrservice/signalr'
  - Web PubSub: ResourceId has 'microsoft.signalrservice/webpubsub'
- Internal exclusion:
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds) or !in (SignalRTeamInternalSubscriptionIds())
- SKU rules:
  - For revenue: exclude 'MessageCount', 'MessageCountPremium'
  - Segmenting: SKU in ('Free','Standard','Premium') for counts/cohorts
- Text matching:
  - has/contains used frequently; both are case-insensitive by default
- EU/global merge:
  - Union non-EU and EU shards of Runtime* and FeatureTrackV2_* for coverage; normalize keys/time before summarizing.

### Cross-cluster/DB & Sharding
- Qualifying external sources (example):
  ```kusto
  cluster('ddtelinsights').database('<DbName>').WebTools_Raw
  cluster('armprodgbl.eastus').database('<DbName>').Unionizer('Requests','HttpIncomingRequests')
  ```
  Replace <DbName> if not pre-bound by functions. In provided queries, Unionizer is invoked as a function without explicit cluster/database qualifiers.
- Sharded union pattern:
  ```kusto
  <Table_Global>
  | where Time > ago(60d) ...
  | union ( <Table_EU> | where Time > ago(60d) ... )
  | project-rename Time = Date
  | summarize ... by Time, <dims>
  ```

### Table classes
- Fact (daily/events): BillingUsage_Daily, MaxConnectionCount_Daily, ResourceMetrics, ConnectionMode_Daily, Runtime* tables, Manage*QoS, FeatureTrack*.
- Snapshot (latest state): RPSettingLatest; various Cached_* snapshots; RetentionSnapshot tables.
- Pre-aggregated (KPI/cached): Cached_* OKR/ARR/Revenue/Subscriptions/ResourceFlow and Top* snapshots; OKRv2021/KPIv2019 series.

## Entity & Counting Rules (Core Definitions)

- Entity model:
  - Resource → Subscription → Customer
  - Keys:
    - Resource: ResourceId (lowercase for joins); optional Role from MaxConnectionCount_Daily
    - Subscription: SubscriptionId
    - Customer: CloudCustomerGuid or P360_ID (via SubscriptionMappings)
- Standard grouping levels:
  - By Date/Week/Month + {SKU, Region, ServiceMode, CustomerType, BillingType, SegmentName}
- Activity definition (“Active”):
  - HasConnection = MaxConnectionCount > 0 (from MaxConnectionCount_Daily or ResourceMetrics)
  - Apply when building subscription/resource cohorts or gating revenue/consumption to “engaged” entities.
- Counting rules:
  - Use dcount(…, precisionBits) with 3–4 bits for stable distincts in dashboards
  - De-dup before counting across periods (distinct ResourceId/SubscriptionId per period grain)
  - Choose snapshot vs fact carefully:
    - For trend computations and custom segmentation, prefer fact tables (BillingUsage_Daily, ResourceMetrics).
    - For KPI displays, cached snapshots are faster but less flexible.

## Canonical Tables
## Canonical Tables

Context
- Product: SignalR and Web PubSub (cluster: signalrinsights.eastus2, database: SignalRBI)
- Queries consistently:
  - Filter time (ago(), startofweek(), startofmonth()) with conservative windows (7–60 days)
  - Exclude internal subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  - Identify service type via ResourceId: has 'microsoft.signalrservice/signalr' (SignalR) or '/webpubsub' (Web PubSub)
  - Enrich via SubscriptionMappings for CustomerType, SegmentName, BillingType
  - Validate “active” with MaxConnectionCount_Daily, often via join on Role/ResourceId
- Freshness and timezone: not specified; treat current day data as potentially incomplete. Prefer closed periods (yesterday, last full week/month).

High Priority

### Table name: BillingUsage_Daily
- Priority: High
- What this table represents: Daily fact table of billing-relevant usage per resource/subscription/region/SKU (unit quantities). Zero rows means no metered usage that day.
- Freshness expectations: Daily updates; common practice is to use ≥ 30–60 day lookbacks; avoid using today until complete.
- When to use / When to avoid:
  - Use: revenue/consumption trends by SKU; customer/subscription/resource counts; segment/billing type breakdown after joining SubscriptionMappings; SignalR vs Web PubSub split by ResourceId.
  - Use: derive revenue with a rate card (e.g., case by SKU) or normalize per-day/month.
  - Avoid: QoS/connection telemetry; active resource detection without joining to MaxConnectionCount_Daily/ResourceMetrics.
- Similar tables & how to choose:
  - ResourceMetrics: operational metrics (connections/messages), not billing quantities.
  - Cached_* snapshots: pre-aggregated KPI outputs; use for OKR tracking, not raw billing computations.
- Common Filters:
  - Date ranges: > ago(30d/60d), startofweek/month windows
  - Exclude internal: SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  - Service discriminator: ResourceId has 'microsoft.signalrservice/signalr' or '/webpubsub'
  - SKU in ('Free','Standard','Premium')
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Usage date (UTC unknown); partition key for daily aggregates |
  | Region        | string   | Azure region of the resource |
  | SubscriptionId| string   | Subscription GUID |
  | ResourceId    | string   | Full Azure resourceId; used to detect service type |
  | SKU           | string   | Pricing tier: Free, Standard, Premium, MessageCount, etc. |
  | Quantity      | real     | Metered usage quantity for the day |
- Column Explain:
  - Date: primary filter and grouping key.
  - ResourceId: categorize by service (SignalR/WebPubSub) and parse subscription/region.
  - SKU: used for segmentation and revenue calculation.
  - Quantity: sum for consumption, multiply by unit price placeholder <UnitPriceX> for revenue.

### Table name: MaxConnectionCount_Daily
- Priority: High
- What this table represents: Daily snapshots of peak connection count per resource (operational activity proxy). Used to validate active resources.
- Freshness expectations: Daily. Paired with BillingUsage_Daily within aligned windows (28–60 days).
- When to use / When to avoid:
  - Use: filter to truly active resources (MaxConnectionCount > 0); join with billing usage on Date and Role/ResourceId to reduce noise.
  - Avoid: fine-grained connection analytics (use ResourceMetrics).
- Similar tables & how to choose:
  - ResourceMetrics: includes daily MaxConnectionCount plus other signals (messages, averages).
- Common Filters:
  - Date >= ago(60d)
  - Join key: Date + Role (lowercased ResourceId from BillingUsage_Daily)
- Table columns:

  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Date              | datetime | Day of measurement |
  | Role              | string   | Resource identifier (often lowercased ResourceId) |
  | SubscriptionId    | string   | Subscription GUID |
  | CustomerType      | string   | From enrichment or source (Internal/External) |
  | Region            | string   | Azure region |
  | MaxConnectionCount| long     | Peak concurrent connections that day |
- Column Explain:
  - Role: join key to BillingUsage_Daily (mapped from ResourceId).
  - MaxConnectionCount: predicate for “active” resource logic.

### Table name: SubscriptionMappings
- Priority: High
- What this table represents: Dimension table mapping SubscriptionId to customer attributes (segment, billing type, etc.). Used across nearly all business segmentation.
- Freshness expectations: Unknown; treat as slowly changing dimensions; join leftouter to avoid loss.
- When to use / When to avoid:
  - Use: enrich usage/QoS data with CustomerType, SegmentName, BillingType.
  - Avoid: counting subscriptions without de-dup; users sometimes union distinct ids across tables then join mapping for segmentation.
- Similar tables & how to choose: N/A (primary dimension).
- Common Filters:
  - Join: on SubscriptionId (leftouter).
- Table columns:

  | Column           | Type   | Description or meaning |
  |------------------|--------|------------------------|
  | P360_ID          | string | Customer id in P360 |
  | CloudCustomerGuid| string | Tenant/customer guid |
  | SubscriptionId   | string | Subscription GUID (join key) |
  | CustomerType     | string | Internal/External/SignalR/WebPubSub classification used in queries |
  | CustomerName     | string | Display name |
  | SegmentName      | string | Segment grouping |
  | OfferType        | string | Offer type |
  | OfferName        | string | Offer name |
  | BillingType      | string | Billing channel/type; used to derive UsageType |
  | WorkloadType     | string | Workload category |
  | S500             | string | Additional code/classification |
- Column Explain:
  - SubscriptionId: essential join key.
  - CustomerType, SegmentName, BillingType: most-used segmentation dimensions.

### Table name: ResourceMetrics
- Priority: High
- What this table represents: Daily resource telemetry aggregates: messages, connection counts, system errors, operations.
- Freshness expectations: Daily; queries roll up to week/month; prefer closed periods.
- When to use / When to avoid:
  - Use: operational activity (Max/Avg connections), traffic (SumMessageCount), build active resource cohorts by week/month.
  - Avoid: billing revenue/quantity (use BillingUsage_Daily).
- Similar tables & how to choose:
  - MaxConnectionCount_Daily: simpler peak-only; use when only “active vs not” needed without messages/averages.
- Common Filters:
  - Date > ago(61d) or bounded month/week windows
  - ResourceId has 'microsoft.signalrservice/signalr'
  - Join with SubscriptionMappings and RPSettingLatest for mode/settings segmentation
- Table columns:

  | Column             | Type     | Description or meaning |
  |--------------------|----------|------------------------|
  | Date               | datetime | Day of telemetry aggregation |
  | Region             | string   | Azure region |
  | ResourceId         | string   | Resource id |
  | SumMessageCount    | real     | Total messages per day |
  | MaxConnectionCount | real     | Peak connection count per day |
  | AvgConnectionCount | real     | Average connection count per day |
  | SumSystemErrors    | real     | Total system errors per day |
  | SumTotalOperations | real     | Total operations per day |
- Column Explain:
  - Max/AvgConnectionCount: used to detect “HasConnection” and activity intensity.
  - SumMessageCount: usage intensity proxy.

### Table name: RPSettingLatest
- Priority: High
- What this table represents: Latest resource-level settings snapshot (SKU/Kind/State/ServiceMode and booleans for feature toggles).
- Freshness expectations: Snapshot; joins use tolower(ResourceId); no time column except LastUpdated.
- When to use / When to avoid:
  - Use: segment metrics by ServiceMode (Default/Serverless/etc.), network/security toggles.
  - Avoid: time-series settings history; this is latest only.
- Similar tables & how to choose: None (settings).
- Common Filters:
  - Join: on tolower(ResourceId); coalesce missing ServiceMode to 'Default'.
- Table columns:

  | Column                   | Type     | Description or meaning |
  |--------------------------|----------|------------------------|
  | ResourceId               | string   | Resource id (join key) |
  | Region                   | string   | Region |
  | SKU                      | string   | Pricing tier |
  | Kind                     | string   | Resource kind |
  | State                    | string   | Provisioning/state |
  | ServiceMode              | string   | Mode (Default/Serverless/Proxy etc.) |
  | IsUpstreamSet            | bool     | Upstream configured |
  | IsEventHandlerSet        | bool     | Event handler configured |
  | EnableTlsClientCert      | bool     | TLS client cert enabled |
  | IsPrivateEndpointSet     | bool     | PE configured |
  | EnablePublicNetworkAccess| bool     | PNA enabled |
  | DisableLocalAuth         | bool     | Local auth disabled |
  | DisableAadAuth           | bool     | AAD auth disabled |
  | IsServerlessTimeoutSet   | bool     | Serverless timeout customized |
  | AllowAnonymousConnect    | bool     | Anonymous allowed |
  | EnableRegionEndpoint     | bool     | Regional endpoint enabled |
  | ResourceStopped          | bool     | Resource stopped |
  | EnableLiveTrace          | bool     | Live trace enabled |
  | EnableResourceLog        | bool     | Resource log enabled |
  | LastUpdated              | datetime | Last settings update time |
  | Extras                   | string   | Additional serialized properties |
- Column Explain:
  - ServiceMode: key segmentation in performance/usage pivots.

### Table name: ConnectionMode_Daily
- Priority: High
- What this table represents: Daily counts of connection types by resource/mode (serverless/proxy).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: split connection volume by ServiceMode; build Resource/Connection counts time-series.
  - Avoid: message counts; use ResourceMetrics.
- Similar tables & how to choose:
  - ResourceMetrics: broader metrics; ConnectionMode_Daily focuses on connection breakdown.
- Common Filters:
  - Date > ago(60d)
  - ResourceId has 'microsoft.signalrservice/signalr'
- Table columns:

  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Date              | datetime | Day |
  | ResourceId        | string   | Resource id |
  | ServerlessConnection| long   | Serverless connections |
  | ProxyConnection   | long     | Proxy connections |
  | ServiceMode       | string   | Mode inferred/recorded |
- Column Explain:
  - ServiceMode and connection columns: used to compute ConnectionCount and resource counts.

### Table name: CustomerModel
- Priority: High
- What this table represents: Customer modeling outputs (not accessible here). Used for advanced segmentation/KPIs in cached tables.
- Freshness expectations: Unknown.
- When to use / When to avoid:
  - Use: when building advanced customer KPIs requiring model outputs.
  - Avoid: basic segmentation; prefer SubscriptionMappings.
- Similar tables & how to choose: SubscriptionMappings for base attributes.
- Common Filters: N/A.
- Table columns:
  - Schema inaccessible in this environment.
- Column Explain:
  - N/A (schema not accessible).

### Table name: RuntimeResourceTags_Daily
- Priority: High
- What this table represents: Daily classification for resources (service type, app hosting flags, success/failure signals).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: classify resources (AppService/StaticApps/Proxy/Sample); detect failures/success.
  - Avoid: detailed runtime request metrics; use RuntimeRequestsGroups_* or RuntimeTransport_*.
- Similar tables & how to choose:
  - ManageResourceTags: management-plane tagging requests, not runtime classification.
- Common Filters:
  - Date windows (e.g., > ago(61d)); join on ResourceId/SubscriptionId.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Day |
  | ResourceId    | string   | Resource id |
  | SubscriptionId| string   | Subscription GUID |
  | ServiceType   | string   | 'SignalR' or 'WebPubSub' |
  | IsAppService  | bool     | Resource linked to App Service |
  | IsStaticApps  | bool     | Linked to Static Web Apps |
  | IsSample      | bool     | Sample/demo resource |
  | IsProxy       | bool     | Proxy mode indicator |
  | HasFailure    | bool     | Observed failure |
  | HasSuccess    | bool     | Observed success |
  | Extra         | string   | Additional info |
- Column Explain:
  - Booleans used to build cohort filters.

### Table name: FeatureTrack_Daily
- Priority: High
- What this table represents: Daily feature usage counts per resource/subscription.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: feature adoption tracking, top features by request count.
  - Avoid: transport/framework split (use RuntimeTransport_*).
- Similar tables & how to choose:
  - FeatureTrackV2_*: enhanced schema with Category/Properties envelope and EU shard; choose V2 for richer metadata or EU partition.
- Common Filters:
  - Date windows, join with SubscriptionMappings, split by Feature.
- Table columns:

  | Column        | Type   | Description or meaning |
  |---------------|--------|------------------------|
  | Date          | datetime | Day |
  | Feature       | string | Feature identifier |
  | ResourceId    | string | Resource id |
  | SubscriptionId| string | Subscription GUID |
  | RequestCount  | long   | Requests attributed to feature |
- Column Explain:
  - Feature, RequestCount: main adoption KPI per day.

### Table name: FeatureTrackV2_Daily
- Priority: High
- What this table represents: V2 feature usage with Category and Properties envelope.
- Freshness expectations: Daily; often summarized weekly/monthly.
- When to use / When to avoid:
  - Use: detailed feature telemetry by Category; property-driven analysis.
  - Avoid: region-partitioned EU data (use V2_EU).
- Similar tables & how to choose:
  - FeatureTrack_Daily (V1) vs V2: pick V2 for richer dims.
  - FeatureTrackV2_EU_Daily: use when examining EU shard.
- Common Filters:
  - Date windows; group by Feature/Category.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Day |
  | Feature       | string   | Feature name/key |
  | Category      | string   | Logical category |
  | ResourceId    | string   | Resource id |
  | SubscriptionId| string   | Subscription GUID |
  | Properties    | string   | JSON/kv metadata |
  | RequestCount  | long     | Requests count |
- Column Explain:
  - Category/Feature: primary pivots; Properties for deeper drill.

### Table name: FeatureTrackV2_EU_Daily
- Priority: High
- What this table represents: EU-partitioned V2 feature usage (regionized shard).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: EU-specific reporting/compliance.
  - Avoid: non-EU global aggregations (union with non-EU where needed).
- Similar tables & how to choose:
  - FeatureTrackV2_Daily: union both for global view.
- Common Filters:
  - Date windows; EU-specific joins/filters.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Day |
  | Region        | string   | Region (EU) |
  | ResourceId    | string   | Resource id |
  | SubscriptionId| string   | Subscription GUID |
  | RequestCount  | long     | Requests count |
- Column Explain:
  - Region used to ensure EU scope.

### Table name: FeatureTrack_AutoScale_Daily
- Priority: High
- What this table represents: Daily activity related to autoscale features.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: autoscale adoption/activity trends.
  - Avoid: general runtime requests; use RuntimeRequestsGroups_*.
- Similar tables & how to choose: other FeatureTrack tables for different feature sets.
- Common Filters: Date windows; joins for segmentation.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Week          | datetime | Week (snapshot uses weekly in cached outputs) |
  | SKU           | string   | SKU |
  | CustomerType  | string   | Customer type |
  | SegmentName   | string   | Segment |
  | Service       | string   | Service label in prepared snapshots |
  | SubscriptionCnt| int     | Subscription counts for cohorts |
- Column Explain:
  - SubscriptionCnt: counts of subscriptions hitting autoscale-related signals (from cached outputs).

### Table name: Cached_ZnOKRARR_Snapshot
- Priority: High
- What this table represents: Pre-aggregated OKR monthly ARR snapshot (SignalR/WebPubSub) with optional goal joins in queries.
- Freshness expectations: Snapshot table; updated periodically; often augmented with inline datatable goals.
- When to use / When to avoid:
  - Use: KPI/OKR reporting for ARR.
  - Avoid: raw revenue computation—use BillingUsage_Daily.
- Similar tables & how to choose:
  - Cached_DtOKRARR_Snapshot: different cohort/scope (“Dt” vs “Zn”)—choose the required lens.
- Common Filters:
  - TimeStamp >= historical windows (e.g., startofmonth(now(), -35))
- Table columns:

  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | TimeStamp  | datetime | Month end/start stamp |
  | SignalR    | real     | ARR for SignalR |
  | WebPubSub  | real     | ARR for Web PubSub |
- Column Explain:
  - TimeStamp main axis; SignalR/WebPubSub values used for split reporting.

### Table name: Cached_ZnOKREstRevenueWeekly_Snapshot
- Priority: High
- What this table represents: Precomputed weekly estimated revenue by SKU and segmentation (Zn scope).
- Freshness expectations: Weekly snapshot.
- When to use / When to avoid:
  - Use: weekly revenue reporting w/o recomputing joins.
  - Avoid: custom SKU pricing—recompute from BillingUsage_Daily if needed.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueMonthly_Snapshot: monthly version.
- Common Filters:
  - Week window; SKU segmentation; Service split.
- Table columns:

  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Week        | datetime | Week |
  | SKU         | string   | SKU |
  | CustomerType| string   | Customer type |
  | SegmentName | string   | Segment |
  | Service     | string   | 'SignalR'/'WebPubSub' or ' JOIN(OR)' label in generated outputs |
  | Income      | real     | Estimated revenue |
- Column Explain:
  - Income directly chartable; Service label may encode unions from query materialization.

### Table name: Cached_ZnOKREstRevenueMonthly_Snapshot
- Priority: High
- What this table represents: Monthly estimated revenue pre-aggregation (Zn scope).
- Freshness expectations: Monthly.
- When to use / When to avoid: Same as weekly; use for month-level reporting.
- Similar tables & how to choose: Weekly counterpart for weekly trend lines.
- Common Filters: Month, SKU, CustomerType, SegmentName.
- Table columns:

  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Month       | datetime | Month |
  | SKU         | string   | SKU |
  | CustomerType| string   | Customer type |
  | SegmentName | string   | Segment |
  | Service     | string   | Service label |
  | Income      | real     | Estimated revenue |
- Column Explain:
  - Income used for KPI charts.

### Table name: Cached_ZnOKRSubs_Snapshot
- Priority: High
- What this table represents: Monthly subscription counts snapshot for OKR (Zn scope), often joined with goals in queries.
- Freshness expectations: Monthly snapshot.
- When to use / When to avoid:
  - Use: OKR subscription totals and splits (SignalR/WebPubSub additions).
  - Avoid: raw distinct subscription counting (recompute from BillingUsage_Daily + MaxConnectionCount_Daily).
- Similar tables & how to choose:
  - Cached_DtOKRSubsWeekly_Snapshot/Monthly_Snapshot for alternate cohort.
- Common Filters: TimeStamp windows, inline goals join.
- Table columns:

  | Column    | Type   | Description or meaning |
  |-----------|--------|------------------------|
  | TimeStamp | datetime | Month timestamp |
  | SignalR   | long   | Subscription counts (SignalR) |
  | WebPubSub | long   | Subscription counts (Web PubSub) |
- Column Explain:
  - Used to compare against goal trajectories.

### Table name: OKRv2021
- Priority: High
- What this table represents: OKR metric series by Date/Category/Value; often pivoted across categories in queries.
- Freshness expectations: Historical series; update cadence unknown.
- When to use / When to avoid:
  - Use: pivoted KPIs across categories for dashboards.
  - Avoid: raw computation; rely on source tables for accuracy checks.
- Similar tables & how to choose: KPIv2019 provides older KPI set.
- Common Filters: Date >= specific baseline.
- Table columns:

  | Column  | Type     | Description or meaning |
  |---------|----------|------------------------|
  | Date    | datetime | Date |
  | Category| string   | KPI category key |
  | Value   | real     | KPI value |
- Column Explain:
  - Category is pivot dimension; Value aggregated per category.

### Table name: Cached_CuOKRConsumption_Snapshot
- Priority: High
- What this table represents: Pre-aggregated consumption KPIs (SignalR/WebPubSub and total).
- Freshness expectations: Snapshot; period unspecified.
- When to use / When to avoid:
  - Use: OKR consumption trends; union with goal lines.
  - Avoid: per-resource/per-subscription consumption; compute from BillingUsage_Daily (Quantity*24 patterns observed).
- Similar tables & how to choose: Weekly/Monthly variants exist.
- Common Filters: TimeStamp windows.
- Table columns:

  | Column    | Type   | Description or meaning |
  |-----------|--------|------------------------|
  | TimeStamp | datetime | Period |
  | Consumption| real  | Total consumption |
  | SignalR   | real   | SignalR portion |
  | WebPubSub | real   | Web PubSub portion |
- Column Explain:
  - Values used directly for OKR displays.

### Table name: Cached_DtOKRARR_Snapshot
- Priority: High
- What this table represents: ARR snapshot (Dt scope) with optional goal overlays; often filtered to last 35 months.
- Freshness expectations: Snapshot monthly.
- When to use / When to avoid: As per Zn ARR snapshot but for Dt cohort.
- Similar tables & how to choose: Choose Dt vs Zn per program definition.
- Common Filters: TimeStamp >= startofmonth(now(), -35)
- Table columns:

  | Column     | Type   | Description or meaning |
  |------------|--------|------------------------|
  | TimeStamp  | datetime | Month |
  | Total      | real   | Total ARR (observed as total column in schema response) |
- Column Explain:
  - Use for total ARR trend lines.

### Table name: Cached_DtOKREstRevenueWeekly_Snapshot
- Priority: High
- What this table represents: Weekly estimated revenue (Dt scope).
- Freshness expectations: Weekly.
- When to use / When to avoid: Week-level OKR displays.
- Similar tables & how to choose: Monthly variant for month trends.
- Common Filters: Week, SKU, UsageType, SegmentName.
- Table columns:

  | Column   | Type     | Description or meaning |
  |----------|----------|------------------------|
  | Week     | datetime | Week |
  | SKU      | string   | SKU |
  | UsageType| string   | Internal vs BillingType |
  | SegmentName| string | Segment |
  | Service  | string   | Service label |
  | Income   | real     | Estimated revenue |
- Column Explain:
  - Income per SKU/segment for OKR.

### Table name: Cached_DtOKREstRevenueMonthly_Snapshot
- Priority: High
- What this table represents: Monthly estimated revenue (Dt scope).
- Freshness expectations: Monthly.
- When to use / When to avoid: Month-level OKR displays.
- Similar tables & how to choose: Weekly variant for weekly reporting.
- Common Filters: Month + dims.
- Table columns:

  | Column   | Type     | Description or meaning |
  |----------|----------|------------------------|
  | Month    | datetime | Month |
  | SKU      | string   | SKU |
  | UsageType| string   | Usage type |
  | SegmentName| string | Segment |
  | Service  | string   | Service label |
  | Income   | real     | Estimated revenue |
- Column Explain:
  - As above.

### Table name: Cached_DtOKRSubsWeekly_Snapshot
- Priority: High
- What this table represents: Weekly subscription counts (Dt scope).
- Freshness expectations: Weekly.
- When to use / When to avoid: Weekly OKR subscriber counts.
- Similar tables & how to choose: Monthly variant or Zn scope for alternative cohort.
- Common Filters: Week/dims.
- Table columns:

  | Column        | Type   | Description or meaning |
  |---------------|--------|------------------------|
  | Week          | datetime | Week |
  | SKU           | string | SKU |
  | UsageType     | string | Usage type |
  | Service       | string | Service label |
  | SubscriptionCnt| int   | Distinct subscription count |
  | SegmentName   | string | Segment |
- Column Explain:
  - SubscriptionCnt used for count charts.

### Table name: Cached_DtOKRSubsMonthly_Snapshot
- Priority: High
- What this table represents: Monthly subscription counts (Dt scope).
- Freshness expectations: Monthly.
- When to use / When to avoid: Monthly OKR counts.
- Similar tables & how to choose: Weekly variant.
- Common Filters: Month/dims.
- Table columns:

  | Column        | Type   | Description or meaning |
  |---------------|--------|------------------------|
  | Month         | datetime | Month |
  | SKU           | string | SKU |
  | UsageType     | string | Usage type |
  | SegmentName   | string | Segment |
  | Service       | string | Service label |
  | SubscriptionCnt| int   | Distinct subscription count |
- Column Explain:
  - As above.

### Table name: Cached_SubsTotalWeekly_Snapshot
- Priority: High
- What this table represents: Weekly total subscription KPIs (schema not retrieved; similar to other Subs snapshots).
- Freshness expectations: Weekly.
- When to use / When to avoid: Weekly totals for OKR dashboards.
- Similar tables & how to choose: Other Subs snapshots for monthly/scope variants.
- Common Filters: Week windows.
- Table columns:
  - Schema not available here (expected similar dims and counts).
- Column Explain: N/A.

### Table name: Cached_SubsTotalMonthly_Snapshot
- Priority: High
- What this table represents: Monthly total subscription KPIs (schema not retrieved).
- Freshness expectations: Monthly.
- When to use / When to avoid: Monthly totals for OKR dashboards.
- Similar tables & how to choose: Weekly counterpart.
- Common Filters: Month windows.
- Table columns: Not available here.
- Column Explain: N/A.

### Table name: OKRv2021_AWPS
- Priority: High
- What this table represents: OKR series for Web PubSub (AWPS) analogous to OKRv2021.
- Freshness expectations: Historical; cadence unknown.
- When to use / When to avoid: Use for AWPS KPI pivots; avoid for raw counts.
- Similar tables & how to choose: OKRv2021 for SignalR combined KPIs.
- Common Filters: Date windows.
- Table columns:

  | Column  | Type     | Description or meaning |
  |---------|----------|------------------------|
  | Date    | datetime | Date |
  | Category| string   | KPI category |
  | Value   | real     | KPI value |
- Column Explain:
  - Use pivot/evaluate pivot in queries.

### Table name: OKR_AWPS_SocketIO
- Priority: High
- What this table represents: AWPS Socket.IO specific KPI outputs.
- Freshness expectations: Unknown.
- When to use / When to avoid: Socket.IO OKR slices.
- Similar tables & how to choose: KPI_SocketIO for broader KPIs.
- Common Filters: Date windows.
- Table columns:
  - Schema not accessible here.
- Column Explain: N/A.

### Table name: Cached_Asrs_TopCustomersWoW_v2_Snapshot
- Priority: High
- What this table represents: Top customers week-over-week for SignalR (ASRS) with ranking and values.
- Freshness expectations: Weekly updates.
- When to use / When to avoid:
  - Use: identify top customers with revenue/connection/message metrics and deltas.
  - Avoid: comprehensive customer list; this is top-k.
- Similar tables & how to choose:
  - Cached_Awps_TopCustomersWoW_v2_Snapshot for AWPS.
- Common Filters: N/A (snapshot).
- Table columns:

  | Column                  | Type     | Description or meaning |
  |-------------------------|----------|------------------------|
  | P360_ID                 | string   | Customer id |
  | P360_CustomerDisplayName| string   | Name |
  | SKU                     | string   | SKU |
  | CustomerType            | string   | Type |
  | BillingType             | string   | Billing channel |
  | Category                | string   | Metric category |
  | CurrentValue            | real     | Current value |
  | P360Url                 | string   | Link |
  | LastDay                 | datetime | Reference day |
  | UsageType               | string   | Usage type |
  | CurrentValue1           | real     | Secondary value |
  | PrevValue               | real     | Previous period |
  | W3Value                 | real     | Value 3 weeks ago |
  | DeltaValue              | real     | Change |
  | Rank                    | long     | Rank |
  | W1Rank                  | long     | 1-week rank |
  | W3Rank                  | long     | 3-week rank |
- Column Explain:
  - Rank/DeltaValue: used to show momentum.

### Table name: Cached_Awps_TopCustomersWoW_v2_Snapshot
- Priority: High
- What this table represents: Same as above for Web PubSub.
- Freshness expectations: Weekly.
- When to use / When to avoid: As above.
- Similar tables & how to choose: ASRS vs AWPS.
- Common Filters: N/A.
- Table columns: Same schema as ASRS variant.
- Column Explain: As above.

### Table name: Cached_TopSubscriptions_Snapshot
- Priority: High
- What this table represents: Top subscriptions over a period by revenue/connection/messages with rates.
- Freshness expectations: Snapshot.
- When to use / When to avoid:
  - Use: highlight top subs with metrics across services.
  - Avoid: exhaustive subscription list.
- Similar tables & how to choose: TopCustomers snapshots for customer lens.
- Common Filters: N/A.
- Table columns:

  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | SubscriptionId | string   | Subscription GUID |
  | Revenue        | real     | Revenue for period |
  | MaxConnection  | long     | Peak connections |
  | MessageCount   | long     | Messages |
  | StartDate      | datetime | Start |
  | EndDate        | datetime | End |
  | TopRevenue     | real     | Top revenue metric |
  | TopConnection  | long     | Top connections metric |
  | TopMessageCount| long     | Top message metric |
  | Rate           | real     | Rate (ratio/percent) |
  | Service        | string   | Service label |
- Column Explain:
  - Rate/Top* fields for ranking context.

Normal Priority

### Table name: ManageResourceTags
- Priority: Normal
- What this table represents: Management-plane operations affecting resource tags, by request name and tags.
- Freshness expectations: Daily event counts.
- When to use / When to avoid:
  - Use: trend of tagging operations, per request method/tags; join to SubscriptionMappings for customer segmentation.
  - Avoid: runtime behavior (use runtime tables).
- Similar tables & how to choose:
  - RuntimeResourceTags_Daily classifies runtime-level features, not mgmt-plane.
- Common Filters:
  - Date > ago(30d), exclude Microsoft.Authorization noise, RequestName != 'Other'
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Day |
  | SubscriptionId| string   | Subscription GUID |
  | ResourceId    | string   | Resource id |
  | RequestName   | string   | Operation (e.g., Add/Set/Delete) |
  | Tags          | string   | Tag payload/kv |
  | Count         | long     | Operation count |
- Column Explain:
  - RequestName/Tags: primary grouping for reporting.

### Table name: KPIv2019
- Priority: Normal
- What this table represents: Historical KPI set by Date/Category/Value (older version).
- Freshness expectations: Historical; cadence unknown.
- When to use / When to avoid:
  - Use: legacy KPI comparisons to OKRv2021.
  - Avoid: current OKR unless required.
- Similar tables & how to choose: OKRv2021 for newer KPIs.
- Common Filters: Date >= 20190101.
- Table columns:

  | Column          | Type     | Description or meaning |
  |-----------------|----------|------------------------|
  | Date            | datetime | Date |
  | SubscriptionCount| long    | Subscriptions |
  | ResourceCount   | long     | Resources |
- Column Explain:
  - Used for macro trends.

### Table name: ChurnCustomers_Monthly
- Priority: Normal
- What this table represents: Monthly churn cohort metrics for SignalR (Total, Churn, Standard, StandardChurn).
- Freshness expectations: Monthly; multiple runs per month (use latest per Month via rank pattern).
- When to use / When to avoid:
  - Use: churn rate charts per month.
  - Avoid: customer-level churn (table is aggregated).
- Similar tables & how to choose: SubscriptionRetentionSnapshot for retention perspective.
- Common Filters: ServiceType == 'SignalR'; rank to latest run.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Month         | datetime | Month |
  | ServiceType   | string   | Service |
  | Total         | long     | Total customers |
  | Churn         | long     | Churned |
  | Standard      | long     | Standard tier count |
  | StandardChurn | long     | Churned in Standard |
  | RunDay        | datetime | Run timestamp |
- Column Explain:
  - Derived rates: StandardChurnRate, OverallChurnRate.

### Table name: ConvertCustomer_Weekly
- Priority: Normal
- What this table represents: Weekly conversion flows (Free→Paid/Standard/Premium, Standard→Premium) with totals and run times.
- Freshness expectations: Weekly; latest run per week.
- When to use / When to avoid:
  - Use: conversion funnels by week.
  - Avoid: daily granularity.
- Similar tables & how to choose: KPI series for broader trends.
- Common Filters: ServiceType == 'SignalR'; startofweek windows.
- Table columns:

  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Week              | datetime | Week |
  | ServiceType       | string   | Service |
  | FreeToStandard    | long     | Count |
  | TotalCustomers    | long     | Count |
  | StandardCustomers | long     | Count |
  | RunDay            | datetime | Run timestamp |
  | FreeToPaid        | long     | Count (sometimes derived) |
  | StandardToPremium | long     | Count |
  | FreeToPremium     | long     | Count |
  | PremiumCustomers  | long     | Count |
- Column Explain:
  - Convert rates often normalized in visuals.

### Table name: ResourceFlow_Weekly
- Priority: Normal
- What this table represents: Weekly resource flow (adds, removes, net) for SignalR; used with cached variants.
- Freshness expectations: Weekly.
- When to use / When to avoid: Use for flow visuals; avoid for raw per-resource lists.
- Similar tables & how to choose: Cached_ResourceFlow_Snapshot (prepped slice).
- Common Filters: Partition 'Week' in cached resources; service type filters.
- Table columns:
  - Not explicitly retrieved; use cached snapshot for reporting shapes.
- Column Explain: N/A.

### Table name: ResourceFlow_Monthly
- Priority: Normal
- What this table represents: Monthly resource flow; similar to weekly at month grain.
- Freshness expectations: Monthly.
- When to use / When to avoid: Month-level flow.
- Table columns: Not retrieved here.
- Column Explain: N/A.

### Table name: SubscriptionRetentionSnapshot
- Priority: Normal
- What this table represents: Subscription retention windows (StartDate, EndDate per SubscriptionId) to compute retention curves.
- Freshness expectations: Snapshot refreshed periodically.
- When to use / When to avoid:
  - Use: build retention matrices across months (see queries with join to synthetic month ranges).
  - Avoid: customer-level churn (use churn tables).
- Similar tables & how to choose: CustomerRetentionSnapshot/ResourceRetentionSnapshot for other entities.
- Common Filters: generate month cohorts using datetime_add and startofmonth.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | SubscriptionId| string   | Subscription GUID |
  | StartDate     | datetime | Start of active window |
  | EndDate       | datetime | End of active window |
- Column Explain:
  - Used to derive Retain/Total/Ratio matrices.

### Table name: CustomerRetentionSnapshot
- Priority: Normal
- What this table represents: Customer-level retention snapshot (not retrieved here).
- Freshness expectations: Periodic.
- When to use / When to avoid: Retention by customer entity vs subscription.
- Table columns: Not available in current environment.
- Column Explain: N/A.

### Table name: ResourceRetentionSnapshot
- Priority: Normal
- What this table represents: Resource-level retention snapshot (not retrieved).
- Freshness expectations: Periodic.
- When to use / When to avoid: Resource retention curves.
- Table columns: Not available.
- Column Explain: N/A.

### Table name: DeleteSurvey
- Priority: Normal
- What this table represents: Deletion survey responses for SignalR/WebPubSub resources.
- Freshness expectations: Survey events as they occur; cadence unknown.
- When to use / When to avoid:
  - Use: understand reasons for deletion, feedback analysis.
  - Avoid: usage metrics.
- Similar tables & how to choose: FeedbackSurvey, DeleteSurveyWebPubSub for broader survey coverage.
- Common Filters: None shown.
- Table columns (from usage in queries):

  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | TIMESTAMP  | datetime | Event time |
  | Deployment | string   | Deployment/env |
  | resourceId | string   | Resource id |
  | reason     | string   | Stated reason |
  | feedback   | string   | Free-text feedback |
- Column Explain:
  - reason/feedback for qualitative insights.

### Table name: FeedbackSurvey
- Priority: Normal
- What this table represents: General feedback survey (not retrieved; used analogously to DeleteSurvey).
- Freshness expectations: Event-driven.
- When to use / When to avoid: Feedback mining.
- Table columns: Not available here.
- Column Explain: N/A.

### Table name: KPI_AWPS
- Priority: Normal
- What this table represents: KPI series for AWPS (not retrieved here).
- Freshness expectations: Unknown.
- When to use / When to avoid: AWPS KPI dashboards.
- Table columns: Not available here.
- Column Explain: N/A.

### Table name: KPI_SocketIO
- Priority: Normal
- What this table represents: KPI series for Socket.IO (not retrieved here).
- Freshness expectations: Unknown.
- When to use / When to avoid: Socket.IO KPI dashboards.
- Table columns: Not available here.
- Column Explain: N/A.

### Table name: DeleteSurveyWebPubSub
- Priority: Normal
- What this table represents: AWPS delete survey responses (not retrieved).
- Freshness expectations: Event-driven.
- Table columns: Not available here.
- Column Explain: N/A.

### Table name: AwpsRetention_SubscriptionSnapshot
- Priority: Normal
- What this table represents: AWPS subscription retention snapshot (not retrieved).
- Freshness expectations: Periodic.
- Table columns: Not available here.

### Table name: AwpsRetention_CustomerSnapshot
- Priority: Normal
- What this table represents: AWPS customer retention snapshot (not retrieved).
- Freshness expectations: Periodic.
- Table columns: Not available here.

### Table name: AwpsRetention_ResourceSnapshot
- Priority: Normal
- What this table represents: AWPS resource retention snapshot (not retrieved).
- Freshness expectations: Periodic.
- Table columns: Not available here.

### Table name: Cached_ResourceFlow_Snapshot
- Priority: Normal
- What this table represents: Prepared resource flow snapshot by Partition ('Week'/'Month') for SignalR.
- Freshness expectations: Periodic.
- When to use / When to avoid:
  - Use: quickly render weekly/monthly resource flow visuals.
  - Avoid: recompute flows; use underlying flow tables if custom logic required.
- Common Filters: ServiceType == 'SignalR', Partition == 'Week' (see query).
- Table columns:

  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Category     | string   | Flow category |
  | Region       | string   | Region |
  | SKU          | string   | SKU |
  | HasConnection| bool     | Active flag |
  | LiveRatio    | string   | Activity label (Swift/Occasional/...) |
  | ResourceCnt  | long     | Count |
  | Date         | datetime | Period |
  | ServiceType  | string   | 'SignalR' |
  | Partition    | string   | 'Week'/'Month' |
- Column Explain:
  - ResourceCnt is the primary measure by categories.

Low Priority

### Table name: OperationQoS_Daily
- Priority: Low
- What this table represents: Daily QoS uptime for operations per region/resource.
- Freshness expectations: Daily; “rolling” windows computed via latest env_time.
- When to use / When to avoid:
  - Use: regional QoS, SLA attainment, rolling 7/28 day QoS.
  - Avoid: connectivity QoS (use ConnectivityQoS_Daily).
- Similar tables & how to choose: ConnectivityQoS_Daily for connectivity layer.
- Common Filters:
  - resourceId has 'microsoft.signalrservice/signalr'
  - Windowing via env_time joins
- Table columns:

  | Column                 | Type     | Description or meaning |
  |------------------------|----------|------------------------|
  | env_name               | string   | Environment name |
  | env_time               | datetime | Day |
  | resourceId             | string   | Resource id |
  | env_cloud_role         | string   | Role |
  | env_cloud_roleInstance | string   | Role instance |
  | env_cloud_environment  | string   | Cloud env |
  | env_cloud_location     | string   | Region |
  | env_cloud_deploymentUnit| string  | DU |
  | totalUpTimeSec         | long     | Uptime seconds |
  | totalTimeSec           | long     | Total seconds |
- Column Explain:
  - QoS = sum(UpTime)/sum(TotalTime).

### Table name: ConnectivityQoS_Daily
- Priority: Low
- What this table represents: Daily connectivity QoS (separate SLA thresholds).
- Freshness expectations: Daily; rolling calculations similar to Operation QoS.
- When to use / When to avoid:
  - Use: connectivity SLA attainment (often 0.995 threshold).
  - Avoid: operation QoS.
- Similar tables & how to choose: OperationQoS_Daily.
- Common Filters: resourceId has 'microsoft.signalrservice/signalr'
- Table columns: Same schema as OperationQoS_Daily.
- Column Explain: Same QoS math.

### Table name: ManageRPQosDaily
- Priority: Low
- What this table represents: Management-plane API QoS by Date/ApiName/Region/Result with counts.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: API QoS rollups, rolling windows, weekly/monthly breakdowns; focus on CustomerType in ('SignalR','').
  - Avoid: runtime QoS (use Operation/Connectivity).
- Similar tables & how to choose: N/A.
- Common Filters:
  - Filter ApiName set (exclude 'UNCATEGORY', internal ACIS/ACS, other exclusions as in queries).
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Day |
  | ApiName       | string   | API name |
  | SubscriptionId| string   | Subscription GUID |
  | CustomerType  | string   | Segmentation |
  | Region        | string   | Region |
  | Result        | string   | Success/Timeout/CustomerError/… |
  | Count         | long     | Count of calls |
- Column Explain:
  - QoS computed as sum(success-like)/sum(total).

### Table name: RuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: Daily grouped runtime request metrics by Category/Metrics with ResourceCount and RequestCount.
- Freshness expectations: Daily; often filtered by thresholds (ResourceCount > 10, RequestCount > 200).
- When to use / When to avoid:
  - Use: scenario-level metrics; combine with EU table for full coverage.
  - Avoid: transport specifics (use RuntimeTransport_*).
- Similar tables & how to choose:
  - RuntimeRequestsGroups_EU_Daily for EU; union them.
- Common Filters:
  - Category != 'Transport'
- Table columns:

  | Column       | Type   | Description or meaning |
  |--------------|--------|------------------------|
  | Date         | datetime | Day |
  | Category     | string | Grouping category (e.g., RestApiScenario) |
  | Metrics      | string | Metric name/key |
  | ResourceCount| long   | Distinct resources |
  | RequestCount | long   | Requests |
- Column Explain:
  - Metrics normalized (e.g., 'v1' to 'v1-HubProxy') in queries.

### Table name: RuntimeRequestsGroups_EU_Daily
- Priority: Low
- What this table represents: EU shard of runtime requests groups.
- Freshness expectations: Daily.
- When to use / When to avoid: Union with non-EU for global.
- Table columns: Same as non-EU variant.
- Column Explain: N/A.

### Table name: RuntimeTransport_Daily
- Priority: Low
- What this table represents: Daily runtime transport/framework usage per resource/subscription.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: understand transport mix by framework; merge with EU table.
  - Avoid: high-level scenario category (use RuntimeRequestsGroups_*).
- Similar tables & how to choose:
  - RuntimeTransport_EU_Daily for EU shard.
- Common Filters:
  - Date > ago(60d)
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Day |
  | Feature       | string   | Feature key |
  | Transport     | string   | WebSockets/LongPolling/etc. |
  | Framework     | string   | Framework id |
  | ResourceId    | string   | Resource id |
  | SubscriptionId| string   | Subscription GUID |
  | RequestCount  | long     | Requests count |
- Column Explain:
  - Transport/Framework combined into metrics in queries.

### Table name: RuntimeTransport_EU_Daily
- Priority: Low
- What this table represents: EU shard for transport metrics.
- Freshness expectations: Daily.
- When to use / When to avoid: Union with non-EU for coverage.
- Table columns: Same as non-EU.
- Column Explain: N/A.

### Table name: AwpsRuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: AWPS-specific runtime request grouping table (not directly queried in provided set).
- Freshness expectations: Daily.
- When to use / When to avoid: AWPS runtime scenarios.
- Table columns: Not available here.

### Table name: WebTools_Raw (cluster: ddtelinsights, database: unknown)
- Priority: Low
- What this table represents: VS WebTools telemetry raw events used to derive dev detection/provisioning/SignalR-related adoption.
- Freshness expectations: Near real-time to daily; use 30-day windows in queries.
- When to use / When to avoid:
  - Use: dev counts (dcount MacAddressHash), event-specific slices (service dependencies, provisioning, publish).
  - Avoid: service-side metrics; this is client tooling telemetry.
- Similar tables & how to choose: None in this product DB.
- Common Filters:
  - AdvancedServerTimestampUtc >= ago(30d)
  - EventName subsets; Properties/Measures contains 'SignalR'
- Table columns (from usage):
  - AdvancedServerTimestampUtc (datetime), EventName (string), Properties (dynamic-like string), Measures (dynamic-like), ExeVersion (string), MacAddressHash (string), ActiveProjectId (string)
- Column Explain:
  - EventName/Properties/Measures drive categorization; Date = startofday(AdvancedServerTimestampUtc).

### Table name: Unionizer (cluster: armprodgbl.eastus, database: unknown; function-style)
- Priority: Low
- What this table represents: Cross-subscription ARM action logs unioned by type; used to detect Event Grid filter operations for SignalR.
- Freshness expectations: Query-time function over ARM logs; 30-day windows shown.
- When to use / When to avoid:
  - Use: management-plane activities for specific resource provider/type/actions.
  - Avoid: service runtime or billing metrics.
- Common Filters:
  - TIMESTAMP > ago(30d), targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE', httpMethod in ('PUT','DELETE'), targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'
- Output columns (from usage):
  - TIMESTAMP, targetResourceProvider, httpMethod, targetResourceType, subscriptionId, targetUri, SourceNamespace (+ computed: ResourceId, action, Date, Location)
- Column Explain:
  - action derived from httpMethod (AddEventGrid/DeleteEventGrid).

Guidance patterns to reuse
- Time filters: prefer closed periods
  - Daily: Date >= ago(30d/60d)
  - Weekly: startofweek(Date) windows; ensure current partial week excluded
  - Monthly: startofmonth windows; normalize by day counts when comparing growth
- Service split:
  - isSignalR = ResourceId has 'microsoft.signalrservice/signalr'
  - isWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
- Exclude internal:
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
- Activity validation:
  - Inner join with MaxConnectionCount_Daily or ResourceMetrics to include only active resources
- Segmentation:
  - Join SubscriptionMappings; derive UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
- Pricing:
  - Use placeholder rates per SKU: case(SKU == 'Free', 0.0, SKU == 'Standard', <UnitPriceStandard>, SKU == 'Premium', <UnitPricePremium>, <UnitPriceDefault>) * Quantity
- EU/global coverage:
  - Union EU and non-EU shards for Runtime* and FeatureTrackV2_* when building global views

Notes
- Freshness/timezone are not explicitly documented. Avoid using “today” unless last ingestion boundary is known.
- For tables whose schemas weren’t accessible here (e.g., CustomerModel, various KPI/AWPS/retention variants), consult your ADX database for exact columns; the usage patterns above reflect how queries expect to consume them.

## Query Building Blocks (Copy-paste snippets)

- Time window template (daily/weekly/monthly + effective end time)
  ```kusto
  // Daily with completeness gate
  let EndDate =
    toscalar(
      BillingUsage_Daily
      | where Date > ago(10d) and Region in ('australiaeast','westeurope')
      | summarize counter = dcount(Region) by Date
      | where counter >= 2
      | top 1 by Date desc
      | project Date
    );
  <Table>
  | where Date > ago(60d) and Date <= EndDate
  | summarize ... by Date

  // Weekly closed period
  <Table>
  | where Date >= startofweek(now(), -N) and Date < startofweek(now())
  | summarize ... by Week = startofweek(Date)

  // Monthly closed period
  <Table>
  | where Date >= startofmonth(now(), -M) and Date < startofmonth(now())
  | summarize ... by Month = startofmonth(Date)
  ```

- Canonical time aliasing
  ```kusto
  <Table> | project-rename Time = Date
  OperationQoS_Daily | project-rename Time = env_time
  WebTools_Raw | extend Time = startofday(AdvancedServerTimestampUtc)
  Unionizer('Requests','HttpIncomingRequests') | extend Time = startofday(TIMESTAMP)
  ```

- Join template (activity gating + enrichment)
  ```kusto
  let Base =
    BillingUsage_Daily
    | where Date >= ago(60d)
      and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    | extend Role = tolower(ResourceId);
  Base
  | join kind=inner (
      MaxConnectionCount_Daily
      | where Date >= ago(60d)
      | project Date, Role = tolower(Role)
    ) on Date, Role
  | join kind=leftouter SubscriptionMappings on SubscriptionId
  | project-away Role1
  ```

- Revenue/consumption derivation (use placeholders)
  ```kusto
  // Replace <UnitPrice...> with correct rates
  | extend Revenue = case(
      SKU == 'Free', 0.0,
      SKU == 'Standard', <UnitPriceStandard>,
      SKU == 'Premium', <UnitPricePremium>,
      <UnitPriceDefault>
    ) * Quantity
  | extend Consumption = Quantity * 24.0 // if the metric expects hour-normalized consumption
  ```

- De-dup pattern
  ```kusto
  // Keep latest row per key on time
  <Table>
  | summarize arg_max(Time, *) by <Key>

  // De-dup per period grain
  <Table>
  | summarize any(<col>) by Period = startofweek(Date), <Key>
  | distinct Period, <Key>
  ```

- Important filters
  ```kusto
  // Internal exclusion
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  // Service split
  | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
           IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
  // SKU scope
  | where SKU in ('Free','Standard','Premium')
  ```

- ID parsing/derivation
  ```kusto
  // SubscriptionId from ResourceId
  | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
  // Or split
  | extend SubscriptionId = tostring(split(ResourceId, '/')[2])
  // Normalize ResourceId (remove /replicas/<n> tail if present)
  | extend ResourceId = iif(ResourceId has 'replicas',
                            tolower(substring(ResourceId, 0, indexof(ResourceId, '/replicas/'))),
                            tolower(ResourceId))
  ```

- Sharded union (EU + global)
  ```kusto
  RuntimeRequestsGroups_Daily
  | where Date > ago(60d) and Category != 'Transport'
  | union (RuntimeRequestsGroups_EU_Daily | where Date > ago(60d) and Category != 'Transport')
  | summarize ResourceCount = dcount(ResourceId), RequestCount = sum(RequestCount) by Date, Category, Metrics
  ```

- Rolling QoS windows (align to latest slice)
  ```kusto
  let dateFilter = OperationQoS_Daily | top 1 by env_time desc | project env_time, k=1;
  OperationQoS_Daily
  | where resourceId has 'microsoft.signalrservice/signalr'
  | extend k=1
  | join kind=inner dateFilter on k
  | where env_time > env_time1 - 7d
  | summarize Qos = iif(sum(totalTimeSec)==0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date=env_time1, Type='Rolling7'
  ```

## Example Queries (with explanations)

1) Estimated revenue by service and SKU (daily), gated by activity and segmented
- Description: Computes per-day Income from BillingUsage_Daily, gates to active resources by joining MaxConnectionCount_Daily on Date+Role (lowercased ResourceId), segments by SubscriptionMappings, and expands to SignalR/WebPubSub splits using a packed structure. Replace hardcoded rates with your own if needed; adjust Date window or SKUs.
```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount', 'MessageCountPremium') and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) 
| project Date, Role = tolower(Role)) on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr', isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
Income = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0)*Quantity
| summarize Income = sum(Income) by Date, SKU, SubscriptionId, isAsrs, isAwps
| join kind = leftouter SubscriptionMappings on SubscriptionId;
raw
| summarize Total = sum(Income), Asrs = sumif(Income, isAsrs), Awps = sumif(Income, isAwps) by Date, SKU, CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Income = toreal(Temp[1])
| union (raw
| summarize Total = sum(Income), Asrs = sumif(Income, isAsrs), Awps = sumif(Income, isAwps) by Date, SKU = ' JOIN(OR)', CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Income = toreal(Temp[1]))
```

2) Subscription counts with goals (completeness windows + monthly)
- Description: Combines a near-term 56-day daily window (aligned to Current) and historical monthly bins, gates with MaxConnectionCount_Daily, splits by IsSignalR/IsWebPubSub, and joins to an inline datatable of monthly goals. Adapt the ResourceId filters and goal rows as needed.
```kusto
let Current = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
BillingUsage_Daily
| where Date > ago(60d)
| extend FakeKey = 1, IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
| summarize count() by Date, SubscriptionId, Current, IsSignalR,IsWebPubSub
| join kind = inner (MaxConnectionCount_Daily | where Date > ago(60d) | summarize count() by Date, SubscriptionId) on Date, SubscriptionId
| where datetime_diff('day', Current, Date) < 56
| extend TimeStamp = iif(datetime_diff('day', Current, Date) < 28, Current, Current - 1h)
| summarize count() by TimeStamp, SubscriptionId, IsSignalR, IsWebPubSub
| union (BillingUsage_Daily
| where Date >= datetime(20201201) and Date < startofmonth(Current)
| extend TimeStamp = startofday(endofmonth(Date)), IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
| summarize count() by TimeStamp, SubscriptionId, IsSignalR, IsWebPubSub
| join kind = inner (MaxConnectionCount_Daily 
| where Date >= datetime(20201201) and Date < startofmonth(Current)
| summarize count() by TimeStamp = startofday(endofmonth(Date)), SubscriptionId) on TimeStamp, SubscriptionId)
| summarize SubscriptionCnt = dcount(SubscriptionId, 4), SignalR = dcountif(SubscriptionId, IsSignalR, 4), WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by TimeStamp
| join kind = fullouter (datatable(TimeStamp: datetime, SubscriptionGoal: real, GrowthGoal: real, SignalRGoal: real, SignalRGrowthGoal: real, WebPubSubGoal: real, WebPubSubGrowthGoal: real)[
datetime(2022-02-28), 24558, 0.038400, 23167, 0.037614, 1390, 0.162995,
datetime(2022-03-31), 25655, 0.039000, 24038, 0.037614, 1617, 0.162995,
datetime(2022-04-30), 26823, 0.039600, 24943, 0.037614, 1880, 0.162995,
datetime(2022-05-31), 28067, 0.040200, 25881, 0.037614, 2186, 0.162995,
datetime(2022-06-30), 29397, 0.041000, 26854, 0.037614, 2543, 0.162995,
datetime(2022-07-31), 30822, 0.041700, 27864, 0.037614, 2957, 0.162995,
datetime(2022-08-31), 32352, 0.042600, 28912, 0.037614, 3439, 0.162995,
datetime(2022-09-30), 34000, 0.043500, 30000, 0.037614, 4000, 0.162995]) on TimeStamp
| extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
| project-away TimeStamp1
```

3) Consumption (Quantity*24) by service and SKU with segmentation
- Description: Mirrors the revenue pattern but computes Consumption as Quantity*24, then splits into SignalR/WebPubSub and expands via pack. Adjust Date window and exclusions as needed.
```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount', 'MessageCountPremium') and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) 
| project Date, Role = tolower(Role)) on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr', isAwps = ResourceId has 'microsoft.signalrservice/webpubsub'
| summarize Consumption = sum(Quantity) * 24 by Date, SKU, SubscriptionId, isAsrs, isAwps
| join kind = leftouter SubscriptionMappings on SubscriptionId;
raw
| summarize Total = sum(Consumption), Asrs = sumif(Consumption, isAsrs), Awps = sumif(Consumption, isAwps) by Date, SKU, CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Consumption = toreal(Temp[1])
| union (raw
| summarize Total = sum(Consumption), Asrs = sumif(Consumption, isAsrs), Awps = sumif(Consumption, isAwps) by Date, SKU = ' JOIN(OR)', CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Consumption = toreal(Temp[1]))
```

4) Operation QoS rolling 7/28-day windows aligned to latest slice
- Description: Aligns computation to the latest env_time, then computes QoS over the trailing 7 and 28 days. Use resourceId has 'microsoft.signalrservice/signalr' filter; adjust the base window and threshold as needed.
```kusto
let dateFilter = OperationQoS_Daily
| top 1 by env_time desc
| project env_time, fakeKey = 1;
OperationQoS_Daily
| where env_time > ago(10d) and resourceId has 'microsoft.signalrservice/signalr'
| extend fakeKey = 1
| join kind = inner dateFilter on fakeKey
| where env_time > env_time1 - 7d
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date = env_time1, Type = 'Rolling7'
| union (
OperationQoS_Daily
| where env_time > ago(30d) and resourceId contains 'microsoft.signalrservice/signalr'
| extend fakeKey = 1
| join kind = inner dateFilter on fakeKey
| where env_time > env_time1 - 28d
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date = env_time1, Type = 'Rolling28')
```

5) Manage RP QoS weekly (API filter normalization + Overall)
- Description: Filters ManageRPQosDaily to valid customer/API set, then computes weekly QoS by Region and Overall. The inner join with a distinct ApiName list ensures consistent API cohorts. Adapt API allow/deny lists per your scope.
```kusto
ManageRPQosDaily
| where Date >= startofweek(now(), -8)
| join kind = inner (ManageRPQosDaily
| where Date > ago(30d) and ApiName !in ('INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription') and ApiName !contains 'acs' and ApiName !contains'acis'
| where CustomerType in ('SignalR', '') and ApiName !in ('Internal-ACIS', 'UNCATEGORY')
| distinct ApiName) on ApiName
| summarize QoS = 1.0*sumif(Count, Result in ('Success', 'Timeout', 'CustomerError'))/sum(Count), TotalRequest=sum(Count) by WeekStart = startofweek(Date), Region
| union (ManageRPQosDaily
| where Date >= startofweek(now(), -8)
| join kind = inner (ManageRPQosDaily
| where Date > ago(30d) and ApiName !in ('INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription') and ApiName !contains 'acs' and ApiName !contains'acis'
| where CustomerType in ('SignalR', '') and ApiName !in ('Internal-ACIS', 'UNCATEGORY')
| distinct ApiName) on ApiName
| summarize QoS = 1.0*sumif(Count, Result in ('Success', 'Timeout', 'CustomerError'))/sum(Count), TotalRequest=sum(Count) by WeekStart = startofweek(Date), Region='Overall')
```

6) Runtime scenario metrics with EU union and Transport view
- Description: Aggregates RuntimeRequestsGroups for non-Transport categories (with EU union) and merges in RuntimeTransport broken down by Framework-Transport. Useful to build a unified scenario metrics panel; adjust thresholds and window as needed.
```kusto
RuntimeRequestsGroups_Daily
| where Date > ago(60d) and ResourceCount > 10 and RequestCount > 200 and Category != 'Transport'
| union (RuntimeRequestsGroups_EU_Daily | where Date > ago(60d) and ResourceCount > 10 and RequestCount > 200 and Category != 'Transport')
| extend Metrics = iif(Category == 'RestApiScenario' and (Metrics startswith 'v1' and Metrics !contains 'HubProxy'), replace_string(Metrics, 'v1', 'v1-HubProxy'), Metrics)
| union (RuntimeTransport_Daily
| union RuntimeTransport_EU_Daily
| where Date > ago(60d)
| extend Metrics = strcat(Framework, '-', Transport)
| summarize ResourceCount = dcount(ResourceId), RequestCount = sum(RequestCount) by Date, Category = 'Transport', Metrics)
```

7) Weekly resource activity classification (LiveRatio)
- Description: Builds weekly cohorts by joining BillingUsage_Daily with ResourceMetrics, deriving ActiveDays and LiveRatio labels. Adjust active-day thresholds to tune Swift/Occasional/Dedicate categories.
```kusto
BillingUsage_Daily 
| where Date >= startofweek(now(), -8) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) and ResourceId has 'microsoft.signalrservice/signalr'
| join kind = inner ResourceMetrics on ResourceId, Date
| summarize Conn = max(MaxConnectionCount), SKU = max(SKU), Region = max(Region), ActiveDays = dcount(Date) by Week=startofweek(Date), ResourceId
| project Week, ResourceId, Category = 'Total', Region, SKU, HasConnection = Conn > 0, LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
| summarize ResourceCnt = dcount(ResourceId, 3) by Week, Category, Region, SKU, HasConnection, LiveRatio
```

8) EndDate slicing by sentinel regions and revenue/quantity split
- Description: Ensures daily slice completeness by requiring both Australia East and West Europe to have data for the day, then computes Total Quantity and Revenue per Date/SKU/CustomerType. Replace rates as needed or expand Region list for your sentinel set.
```kusto
let EndDate = toscalar(BillingUsage_Daily | where Date > ago(10d) and Region in ('australiaeast', 'westeurope') 
| summarize counter = dcount(Region) by Date | where counter >= 2 | top 1 by Date desc | project Date);
BillingUsage_Daily
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and Date >= ago(60d) and ResourceId has '/signalr/' and Date <= EndDate
| extend Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0)*Quantity
| join kind = leftouter SubscriptionMappings on SubscriptionId
| summarize Total = sum(Quantity), Revenue = sum(Revenue) by Date, SKU, CustomerType
```

## Reasoning Notes (only if uncertain)
- Timezone of Date/env_time is not documented; we assume UTC to avoid drift across shards.
- Internal subscription set is referenced as both a function and a static list; we assume a database function exists and prefer SignalRTeamInternalSubscriptionIds() where available.
- Revenue rates (1.61, 2.0) appear inline; for production use, we recommend externalizing to a rate card or parameterized let bindings (<UnitPriceStandard>/<UnitPricePremium>), as rates may vary by region/offer.
- Activity definition uses MaxConnectionCount > 0; some analyses could prefer thresholds on AvgConnectionCount or message volume; we adopt MaxConnectionCount > 0 per prevalent queries.
- EU sharding is explicit for Runtime* and FeatureTrackV2_*; other tables might have regional ingestion variance; we do not union EU for BillingUsage_Daily as it appears global.
- Completeness gates use a two-region intersection; a stricter approach could require all prod regions or a quorum; we adopt the two-region pattern seen in queries.
- Consumption normalization uses Quantity*24 in examples; we assume Quantity is hourly-rate-based when normalized—if Quantity already reflects day totals, skip the multiplier.
- Role vs ResourceId alignment: some MaxConnectionCount_Daily joins use Role; we standardize by tolower(ResourceId)→Role. If Role schema deviates, coalesce(Role, tolower(ResourceId)).
- LiveRatio classifications (Swift/Occasional/Dedicate) use day-count thresholds from examples; tune thresholds per business definition.
